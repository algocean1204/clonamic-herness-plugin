#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[2]
STAGER = Path(__file__).with_name("stage-host-marketplace.py")
STATE_SCHEMA = "clonamic-cursor-install"
CURSOR_RULE = "clonamic-operating-contract.mdc"


class InstallError(RuntimeError):
    pass


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("clonamic_cursor_stager", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise InstallError(f"cannot load stager: {path}")
    spec.loader.exec_module(module)
    return module


def load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstallError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise InstallError(f"expected object: {path}")
    return value


def save_object(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise InstallError(f"plugin is not a regular directory: {root}")
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        if path.is_symlink():
            raise InstallError(f"plugin contains a symlink: {path}")
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise InstallError(f"managed file is not regular: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_toggles(config_paths: list[Path], optional_names: set[str]) -> dict[str, bool]:
    toggles = {name: False for name in optional_names}
    for index, path in enumerate(config_paths):
        payload = load_object(path)
        allowed = {"$schema", "schema_version", "plugins"}
        if set(payload) - allowed:
            raise InstallError(f"unknown config fields: {path}")
        version = payload.get("schema_version")
        if version is not None and version != 1:
            raise InstallError(f"unsupported config version: {path}")
        plugins = payload.get("plugins")
        if not isinstance(plugins, dict):
            raise InstallError(f"plugins must be an object: {path}")
        unknown = set(plugins) - optional_names
        if unknown:
            raise InstallError(f"unknown plugins in {path}: {sorted(unknown)}")
        if index == 0 and set(plugins) != optional_names:
            raise InstallError("the base config must declare every optional plugin")
        if not all(isinstance(value, bool) for value in plugins.values()):
            raise InstallError(f"plugin toggles must be booleans: {path}")
        toggles.update(plugins)
    return toggles


def load_state(path: Path, target: Path) -> dict:
    if not path.exists():
        return {
            "schema": STATE_SCHEMA,
            "target": str(target),
            "plugins": {},
            "provider_plugins": [],
            "rule": None,
        }
    state = load_object(path)
    if set(state) == {"schema", "target", "plugins"}:
        state = {**state, "provider_plugins": [], "rule": None}
    if set(state) != {"schema", "target", "plugins", "provider_plugins", "rule"}:
        raise InstallError("install state fields are invalid")
    if state["schema"] != STATE_SCHEMA or state["target"] != str(target):
        raise InstallError("install state does not match this target")
    if not isinstance(state["plugins"], dict):
        raise InstallError("install state plugins are invalid")
    if not isinstance(state["provider_plugins"], list) or not all(
        isinstance(name, str) for name in state["provider_plugins"]
    ):
        raise InstallError("install state provider plugins are invalid")
    return state


def validate_managed(state: dict, target: Path) -> None:
    for name, row in state["plugins"].items():
        if not isinstance(row, dict) or set(row) != {"digest", "preimage"}:
            raise InstallError(f"invalid install state for {name}")
        current = target / name
        if not current.is_dir():
            raise InstallError(f"managed plugin is missing: {name}")
        if tree_digest(current) != row["digest"]:
            raise InstallError(f"managed plugin was modified outside the installer: {name}")
        preimage = row["preimage"]
        if preimage is not None and not Path(preimage).is_dir():
            raise InstallError(f"pre-install backup is missing: {name}")
    rule = state["rule"]
    if rule is not None:
        if not isinstance(rule, dict) or set(rule) != {"path", "digest", "preimage"}:
            raise InstallError("install state rule is invalid")
        current = Path(rule["path"])
        if file_digest(current) != rule["digest"]:
            raise InstallError("managed Cursor rule was modified outside the installer")
        if rule["preimage"] is not None and not Path(rule["preimage"]).is_file():
            raise InstallError("pre-install Cursor rule backup is missing")


def copy_directory(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise InstallError(f"destination already exists: {destination}")
    shutil.copytree(source, destination, symlinks=False)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def snapshot(
    paths: set[str], target: Path, state_path: Path, transaction: Path, rule_path: Path
) -> None:
    current = transaction / "current"
    current.mkdir(parents=True)
    for name in sorted(paths):
        source = target / name
        if source.exists() or source.is_symlink():
            copy_directory(source, current / name)
    if state_path.is_file():
        shutil.copy2(state_path, transaction / "state.json")
    if rule_path.is_symlink():
        raise InstallError(f"Cursor rule target is a symlink: {rule_path}")
    if rule_path.is_file() and not rule_path.is_symlink():
        shutil.copy2(rule_path, transaction / "rule.mdc")


def rollback(
    paths: set[str], target: Path, state_path: Path, transaction: Path, rule_path: Path
) -> None:
    for name in sorted(paths):
        remove_path(target / name)
        saved = transaction / "current" / name
        if saved.is_dir():
            copy_directory(saved, target / name)
    saved_state = transaction / "state.json"
    if saved_state.is_file():
        state_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved_state, state_path)
    else:
        state_path.unlink(missing_ok=True)
    remove_path(rule_path)
    saved_rule = transaction / "rule.mdc"
    if saved_rule.is_file():
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved_rule, rule_path)


def claude_provided_plugins(registry_path: Path, settings_path: Path) -> set[str]:
    if not registry_path.is_file() or not settings_path.is_file():
        return set()
    registry = load_object(registry_path)
    settings = load_object(settings_path)
    rows = registry.get("plugins")
    enabled = settings.get("enabledPlugins")
    if not isinstance(rows, dict) or not isinstance(enabled, dict):
        return set()
    provided = set()
    for key, installations in rows.items():
        if not isinstance(key, str) or not key.endswith("@clonamic") or enabled.get(key) is not True:
            continue
        if not isinstance(installations, list):
            continue
        if any(
            isinstance(row, dict)
            and isinstance(row.get("installPath"), str)
            and Path(row["installPath"]).is_dir()
            for row in installations
        ):
            provided.add(key.rsplit("@", 1)[0])
    return provided


def staged_packages(stage: Path) -> dict[str, Path]:
    packages = {}
    for path in sorted((stage / "plugins").iterdir()):
        manifest = load_object(path / ".cursor-plugin" / "plugin.json")
        name = manifest.get("name")
        if not isinstance(name, str) or name != path.name:
            raise InstallError(f"staged package name mismatch: {path}")
        packages[name] = path
    if "clonamic-herness-plugin" not in packages:
        raise InstallError("staged Core package is missing")
    return packages


def stage_marketplace(destination: Path) -> dict[str, Path]:
    stager = load_module(STAGER)
    count = stager.materialize("cursor", destination)
    packages = staged_packages(destination)
    if count != len(packages):
        raise InstallError("staged package count mismatch")
    return packages


def install(
    target: Path,
    state_path: Path,
    config_paths: list[Path],
    claude_registry: Optional[Path] = None,
    claude_settings: Optional[Path] = None,
    rule_path: Optional[Path] = None,
) -> dict:
    claude_registry = claude_registry or Path.home() / ".claude/plugins/installed_plugins.json"
    claude_settings = claude_settings or Path.home() / ".claude/settings.json"
    rule_path = rule_path or Path.home() / ".cursor/rules" / CURSOR_RULE
    target.mkdir(parents=True, exist_ok=True)
    state = load_state(state_path, target)
    validate_managed(state, target)
    if state["rule"] is not None and Path(state["rule"]["path"]) != rule_path:
        raise InstallError("Cursor rule target does not match the managed installation")
    with tempfile.TemporaryDirectory(prefix="clonamic-cursor-stage-") as temporary:
        stage = Path(temporary) / "marketplace"
        packages = stage_marketplace(stage)
        optional = set(packages) - {"clonamic-herness-plugin"}
        toggles = load_toggles(config_paths, optional)
        desired = {"clonamic-herness-plugin", *(name for name, enabled in toggles.items() if enabled)}
        provided = claude_provided_plugins(claude_registry, claude_settings) & desired
        local_desired = desired - provided
        touched = set(state["plugins"]) | local_desired
        transaction = state_path.parent / "transactions" / uuid.uuid4().hex
        transaction.mkdir(parents=True)
        snapshot(touched, target, state_path, transaction, rule_path)
        preimage_root = state_path.parent / "preimages" / uuid.uuid4().hex
        new_state = {
            "schema": STATE_SCHEMA,
            "target": str(target),
            "plugins": {},
            "provider_plugins": sorted(provided),
            "rule": None,
        }
        try:
            for name in sorted(local_desired):
                current = target / name
                previous = state["plugins"].get(name)
                preimage = previous["preimage"] if previous else None
                if previous is None and (current.exists() or current.is_symlink()):
                    preimage_root.mkdir(parents=True, exist_ok=True)
                    copy_directory(current, preimage_root / name)
                    preimage = str(preimage_root / name)
                remove_path(current)
                copy_directory(packages[name], current)
                new_state["plugins"][name] = {
                    "digest": tree_digest(current),
                    "preimage": preimage,
                }
            for name, row in state["plugins"].items():
                if name in local_desired:
                    continue
                current = target / name
                remove_path(current)
                if row["preimage"] is not None:
                    copy_directory(Path(row["preimage"]), current)
            if "clonamic-herness-plugin" in provided:
                prior_rule = state["rule"]
                preimage = prior_rule["preimage"] if prior_rule else None
                if prior_rule is None and (rule_path.exists() or rule_path.is_symlink()):
                    if rule_path.is_symlink() or not rule_path.is_file():
                        raise InstallError(f"Cursor rule target is not a regular file: {rule_path}")
                    preimage_root.mkdir(parents=True, exist_ok=True)
                    saved = preimage_root / CURSOR_RULE
                    shutil.copy2(rule_path, saved)
                    preimage = str(saved)
                remove_path(rule_path)
                rule_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    packages["clonamic-herness-plugin"] / "rules" / CURSOR_RULE,
                    rule_path,
                )
                new_state["rule"] = {
                    "path": str(rule_path),
                    "digest": file_digest(rule_path),
                    "preimage": preimage,
                }
            elif state["rule"] is not None:
                remove_path(rule_path)
                if state["rule"]["preimage"] is not None:
                    rule_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(Path(state["rule"]["preimage"]), rule_path)
            save_object(state_path, new_state)
            validate_managed(new_state, target)
        except BaseException:
            rollback(touched, target, state_path, transaction, rule_path)
            raise
        finally:
            shutil.rmtree(transaction, ignore_errors=True)
    return {
        "action": "installed",
        "plugins": sorted(local_desired),
        "provider_plugins": sorted(provided),
        "rule": str(rule_path) if new_state["rule"] else None,
        "target": str(target),
    }


def uninstall(target: Path, state_path: Path, rule_path: Optional[Path] = None) -> dict:
    if not state_path.is_file():
        raise InstallError("Cursor installation state is missing")
    state = load_state(state_path, target)
    rule_path = rule_path or (
        Path(state["rule"]["path"])
        if state["rule"] is not None
        else Path.home() / ".cursor/rules" / CURSOR_RULE
    )
    if state["rule"] is not None and Path(state["rule"]["path"]) != rule_path:
        raise InstallError("Cursor rule target does not match the managed installation")
    validate_managed(state, target)
    touched = set(state["plugins"])
    transaction = state_path.parent / "transactions" / uuid.uuid4().hex
    transaction.mkdir(parents=True)
    snapshot(touched, target, state_path, transaction, rule_path)
    try:
        for name, row in state["plugins"].items():
            current = target / name
            remove_path(current)
            if row["preimage"] is not None:
                copy_directory(Path(row["preimage"]), current)
        if state["rule"] is not None:
            remove_path(rule_path)
            if state["rule"]["preimage"] is not None:
                rule_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(state["rule"]["preimage"]), rule_path)
        state_path.unlink()
    except BaseException:
        rollback(touched, target, state_path, transaction, rule_path)
        raise
    finally:
        shutil.rmtree(transaction, ignore_errors=True)
    return {
        "action": "uninstalled",
        "plugins": sorted(touched),
        "provider_plugins": state["provider_plugins"],
        "target": str(target),
    }


def doctor(
    target: Path,
    state_path: Path,
    claude_registry: Optional[Path] = None,
    claude_settings: Optional[Path] = None,
) -> dict:
    state = load_state(state_path, target)
    if not state["plugins"] and not state["provider_plugins"]:
        raise InstallError("no managed Cursor plugins are installed")
    validate_managed(state, target)
    if state["provider_plugins"]:
        claude_registry = claude_registry or Path.home() / ".claude/plugins/installed_plugins.json"
        claude_settings = claude_settings or Path.home() / ".claude/settings.json"
        current = claude_provided_plugins(claude_registry, claude_settings)
        missing = set(state["provider_plugins"]) - current
        if missing:
            raise InstallError(f"Claude-provided Cursor plugins are unavailable: {sorted(missing)}")
    return {
        "action": "verified",
        "plugins": sorted(state["plugins"]),
        "provider_plugins": state["provider_plugins"],
        "target": str(target),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Clonamic plugins into Cursor safely.")
    parser.add_argument("action", choices=("install", "uninstall", "doctor"))
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".cursor" / "plugins" / "local",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path.home() / ".cursor" / "clonamic" / "install-state.json",
    )
    parser.add_argument("--config", type=Path, action="append", default=[])
    parser.add_argument("--claude-registry", type=Path)
    parser.add_argument("--claude-settings", type=Path)
    parser.add_argument("--rule-target", type=Path)
    args = parser.parse_args()
    target = args.target.expanduser().resolve()
    state_path = args.state.expanduser().resolve()
    claude_registry = args.claude_registry.expanduser().resolve() if args.claude_registry else None
    claude_settings = args.claude_settings.expanduser().resolve() if args.claude_settings else None
    rule_path = args.rule_target.expanduser().resolve() if args.rule_target else None
    configs = [ROOT / "clonamic.json", *(path.expanduser().resolve() for path in args.config)]
    try:
        if args.action == "install":
            result = install(
                target, state_path, configs, claude_registry, claude_settings, rule_path
            )
        elif args.action == "uninstall":
            result = uninstall(target, state_path, rule_path)
        else:
            result = doctor(target, state_path, claude_registry, claude_settings)
    except (InstallError, OSError, ValueError) as error:
        print(f"cursor-install: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
