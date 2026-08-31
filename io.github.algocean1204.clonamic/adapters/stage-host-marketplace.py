#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = "io.github.algocean1204.clonamic"
PLATFORM_LAYOUT = {
    "codex": (Path(".agents/plugins/marketplace.json"), ".codex-plugin"),
    "claude": (Path(".claude-plugin/marketplace.json"), ".claude-plugin"),
    "grok": (Path(".grok-plugin/marketplace.json"), ".grok-plugin"),
}
ROOT_FILES = (
    "plugin.json",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "clonamic-herness-plugin.md",
    "clonamic.json",
)
ROOT_DIRECTORIES = ("skills", "catalog", "schemas")
PRIVATE_FILENAMES = {
    ".env",
    ".git-credentials",
    ".netrc",
    ".npmrc",
    "auth.json",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
PRIVATE_TEXT = re.compile(
    r"(?:/Users/(?!(?i:user(?:name)?|data|example)/)[^/]+/"
    r"|/home/(?!(?i:user(?:name)?|data|example)/)[^/]+/"
    r"|[A-Za-z]:[\\/](?i:Users)[\\/](?!(?i:user(?:name)?|data|example)[\\/])[^\\/]+[\\/]"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bAKIA[0-9A-Z]{16}\b|\bgh[oprsu]_[A-Za-z0-9]{20,}\b"
    r"|\bxox[baprs]-[A-Za-z0-9-]{20,}\b|\bsk-[A-Za-z0-9_-]{20,}\b)"
    ,
)


class StageError(RuntimeError):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StageError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise StageError(f"expected object: {path}")
    return value


def package_root(manifest: str) -> Path:
    relative = PurePosixPath(manifest)
    if relative.is_absolute() or ".." in relative.parts:
        raise StageError(f"manifest escapes repository: {manifest}")
    path = (ROOT / Path(*relative.parts)).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise StageError(f"missing contained manifest: {manifest}")
    return path.parent


def tracked_inventory() -> dict[Path, tuple[str, str]]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-s", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise StageError("a Git checkout with a readable tracked-file inventory is required")
    inventory: dict[Path, tuple[str, str]] = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        metadata, separator, encoded_path = raw.partition(b"\t")
        if not separator:
            raise StageError("invalid Git tracked-file inventory")
        fields = metadata.decode("ascii").split()
        if len(fields) < 2:
            raise StageError("invalid Git tracked-file metadata")
        mode, object_id = fields[0], fields[1]
        relative = Path(encoded_path.decode("utf-8", "strict"))
        if relative.is_absolute() or ".." in relative.parts:
            raise StageError(f"tracked path escapes repository: {relative}")
        if mode in {"120000", "160000"}:
            raise StageError(f"tracked symlink or submodule is not stageable: {relative}")
        inventory[relative] = (mode, object_id)
    return inventory


def copy_tracked_file(
    source: Path,
    destination: Path,
    inventory: dict[Path, tuple[str, str]],
) -> None:
    relative = source.relative_to(ROOT)
    if relative not in inventory:
        raise StageError(f"required file is not tracked: {relative}")
    for ancestor in (source, *source.parents):
        if ancestor == ROOT:
            break
        if ancestor.is_symlink():
            raise StageError(f"tracked source has a symlink ancestor: {relative}")
    if source.is_symlink() or not source.is_file():
        raise StageError(f"tracked source is not a regular file: {relative}")
    if not source.resolve().is_relative_to(ROOT.resolve()):
        raise StageError(f"tracked source resolves outside repository: {relative}")
    mode, object_id = inventory[relative]
    blob = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "blob", object_id],
        capture_output=True,
        check=False,
    )
    if blob.returncode != 0:
        raise StageError(f"cannot read indexed blob: {relative}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(blob.stdout)
    destination.chmod(0o755 if mode == "100755" else 0o644)


def copy_tree(
    source: Path,
    destination: Path,
    inventory: dict[Path, tuple[str, str]],
) -> None:
    relative_root = source.relative_to(ROOT)
    selected = sorted(
        relative
        for relative in inventory
        if relative != relative_root and relative.is_relative_to(relative_root)
    )
    if not selected:
        raise StageError(f"tracked package tree is empty: {relative_root}")
    for relative in selected:
        source_file = ROOT / relative
        target = destination / relative.relative_to(relative_root)
        copy_tracked_file(source_file, target, inventory)


def scan_private_payload(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise StageError(f"staged payload contains a symlink: {path.relative_to(root)}")
        if not path.is_file():
            continue
        if path.name in PRIVATE_FILENAMES or path.suffix.casefold() in PRIVATE_SUFFIXES:
            raise StageError(f"staged payload contains a private filename: {path.relative_to(root)}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PRIVATE_TEXT.search(text):
            raise StageError(f"staged payload contains a private path or key: {path.relative_to(root)}")


def materialize(platform: str, destination: Path) -> int:
    marketplace_relative, native_directory = PLATFORM_LAYOUT[platform]
    catalog = load_json(ROOT / "catalog/plugins.json")
    entries = catalog.get("plugins")
    if not isinstance(entries, list):
        raise StageError("catalog plugins must be an array")

    inventory = tracked_inventory()
    destination.mkdir(parents=True)
    for name in ROOT_FILES:
        source = ROOT / name
        if source.is_file():
            copy_tracked_file(source, destination / name, inventory)
    for name in ROOT_DIRECTORIES:
        copy_tree(ROOT / name, destination / name, inventory)

    staged = 0
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("manifest"), str):
            raise StageError("catalog entry is invalid")
        if platform not in entry.get("platforms", []):
            continue
        source_package = package_root(entry["manifest"])
        relative_package = source_package.relative_to(ROOT)
        staged_package = destination if relative_package == Path(".") else destination / relative_package
        if relative_package != Path("."):
            copy_tree(source_package, staged_package, inventory)
        native = source_package / NAMESPACE / platform / "plugin.json"
        if not native.is_file():
            raise StageError(f"missing generated {platform} manifest: {native}")
        native_target = staged_package / native_directory / "plugin.json"
        native_target.parent.mkdir(parents=True, exist_ok=True)
        copy_tracked_file(native, native_target, inventory)
        if not (staged_package / "skills").is_dir():
            raise StageError(f"staged skills missing: {staged_package}")
        staged += 1

    marketplace = ROOT / NAMESPACE / "marketplaces" / f"{platform}.json"
    if not marketplace.is_file():
        raise StageError(f"missing generated marketplace: {marketplace}")
    marketplace_target = destination / marketplace_relative
    marketplace_target.parent.mkdir(parents=True, exist_ok=True)
    copy_tracked_file(marketplace, marketplace_target, inventory)
    scan_private_payload(destination)
    return staged


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize one host-native marketplace without changing canonical packages."
    )
    parser.add_argument("platform", choices=sorted(PLATFORM_LAYOUT))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    if output.is_relative_to(ROOT.resolve()):
        print(f"output must stay outside the source repository: {output}", file=sys.stderr)
        return 2
    if output.exists():
        print(f"output already exists: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.tmp-{uuid.uuid4().hex}"
    try:
        count = materialize(args.platform, temporary)
        os.replace(temporary, output)
    except Exception as error:
        shutil.rmtree(temporary, ignore_errors=True)
        print(f"staging failed: {error}", file=sys.stderr)
        return 1
    print(f"staged {args.platform} marketplace: {count} packages -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
