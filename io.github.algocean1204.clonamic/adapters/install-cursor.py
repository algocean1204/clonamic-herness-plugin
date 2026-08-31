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


ROOT = Path(__file__).resolve().parents[2]
STAGER = Path(__file__).with_name("stage-host-marketplace.py")
STATE_SCHEMA = "clonamic-cursor-install"


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
        return {"schema": STATE_SCHEMA, "target": str(target), "plugins": {}}
    state = load_object(path)
    if set(state) != {"schema", "target", "plugins"}:
        raise InstallError("install state fields are invalid")
    if state["schema"] != STATE_SCHEMA or state["target"] != str(target):
        raise InstallError("install state does not match this target")
    if not isinstance(state["plugins"], dict):
        raise InstallError("install state plugins are invalid")
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


def copy_directory(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise InstallError(f"destination already exists: {destination}")
    shutil.copytree(source, destination, symlinks=False)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def snapshot(paths: set[str], target: Path, state_path: Path, transaction: Path) -> None:
    current = transaction / "current"
    current.mkdir(parents=True)
    for name in sorted(paths):
        source = target / name
        if source.exists() or source.is_symlink():
            copy_directory(source, current / name)
    if state_path.is_file():
        shutil.copy2(state_path, transaction / "state.json")


def rollback(paths: set[str], target: Path, state_path: Path, transaction: Path) -> None:
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


def install(target: Path, state_path: Path, config_paths: list[Path]) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    state = load_state(state_path, target)
    validate_managed(state, target)
    with tempfile.TemporaryDirectory(prefix="clonamic-cursor-stage-") as temporary:
        stage = Path(temporary) / "marketplace"
        packages = stage_marketplace(stage)
        optional = set(packages) - {"clonamic-herness-plugin"}
        toggles = load_toggles(config_paths, optional)
        desired = {"clonamic-herness-plugin", *(name for name, enabled in toggles.items() if enabled)}
        touched = set(state["plugins"]) | desired
        transaction = state_path.parent / "transactions" / uuid.uuid4().hex
        transaction.mkdir(parents=True)
        snapshot(touched, target, state_path, transaction)
        preimage_root = state_path.parent / "preimages" / uuid.uuid4().hex
        new_state = {"schema": STATE_SCHEMA, "target": str(target), "plugins": {}}
        try:
            for name in sorted(desired):
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
                if name in desired:
                    continue
                current = target / name
                remove_path(current)
                if row["preimage"] is not None:
                    copy_directory(Path(row["preimage"]), current)
            save_object(state_path, new_state)
            validate_managed(new_state, target)
        except BaseException:
            rollback(touched, target, state_path, transaction)
            raise
        finally:
            shutil.rmtree(transaction, ignore_errors=True)
    return {"action": "installed", "plugins": sorted(desired), "target": str(target)}


def uninstall(target: Path, state_path: Path) -> dict:
    if not state_path.is_file():
        raise InstallError("Cursor installation state is missing")
    state = load_state(state_path, target)
    validate_managed(state, target)
    touched = set(state["plugins"])
    transaction = state_path.parent / "transactions" / uuid.uuid4().hex
    transaction.mkdir(parents=True)
    snapshot(touched, target, state_path, transaction)
    try:
        for name, row in state["plugins"].items():
            current = target / name
            remove_path(current)
            if row["preimage"] is not None:
                copy_directory(Path(row["preimage"]), current)
        state_path.unlink()
    except BaseException:
        rollback(touched, target, state_path, transaction)
        raise
    finally:
        shutil.rmtree(transaction, ignore_errors=True)
    return {"action": "uninstalled", "plugins": sorted(touched), "target": str(target)}


def doctor(target: Path, state_path: Path) -> dict:
    state = load_state(state_path, target)
    if not state["plugins"]:
        raise InstallError("no managed Cursor plugins are installed")
    validate_managed(state, target)
    return {"action": "verified", "plugins": sorted(state["plugins"]), "target": str(target)}


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
    args = parser.parse_args()
    target = args.target.expanduser().resolve()
    state_path = args.state.expanduser().resolve()
    configs = [ROOT / "clonamic.json", *(path.expanduser().resolve() for path in args.config)]
    try:
        if args.action == "install":
            result = install(target, state_path, configs)
        elif args.action == "uninstall":
            result = uninstall(target, state_path)
        else:
            result = doctor(target, state_path)
    except (InstallError, OSError, ValueError) as error:
        print(f"cursor-install: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
