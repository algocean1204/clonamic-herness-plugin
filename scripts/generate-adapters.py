#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "plugins.json"
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
NAMESPACE = "io.github.algocean1204.clonamic"
PLATFORMS = ("codex", "claude", "grok", "hermes")
CATALOG_PLATFORMS = {*PLATFORMS, "agent-plugins"}
MANIFEST_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
MARKETPLACE_PATHS = {
    "codex": ROOT / ".agents" / "plugins" / "marketplace.json",
    "claude": ROOT / ".claude-plugin" / "marketplace.json",
    "grok": ROOT / ".grok-plugin" / "marketplace.json",
}
DESCRIPTOR_ROOT = ROOT / NAMESPACE
NATIVE_DIRS = {
    "codex": ".codex-plugin",
    "claude": ".claude-plugin",
    "grok": ".grok-plugin",
}
NATIVE_METADATA_FIELDS = (
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
)
EXECUTOR_TEMPLATE = ROOT / "scripts" / "executor_call_template.py"
EXECUTOR_PROVIDERS = {
    "clonamic-gpt": {
        "executor": "clonamic-gpt",
        "executable": "codex",
        "prompt_transport": "stdin",
        "arguments": ["exec", "--ephemeral", "--sandbox", "read-only", "{cli_args}", "-"],
    },
    "clonamic-grok": {
        "executor": "clonamic-grok",
        "executable": "grok",
        "prompt_transport": "file",
        "arguments": [
            "--permission-mode", "plan", "--disable-web-search", "--no-subagents",
            "--tools", "", "{cli_args}", "--prompt-file", "{prompt_file}",
        ],
    },
    "clonamic-claude": {
        "executor": "clonamic-claude",
        "executable": "claude",
        "prompt_transport": "stdin",
        "arguments": [
            "-p", "--no-session-persistence", "--permission-mode", "plan", "--tools", "",
            "{cli_args}",
        ],
    },
    "clonamic-hermes": {
        "executor": "clonamic-hermes",
        "executable": "hermes",
        "prompt_transport": "argv",
        "arguments": ["{cli_args}", "--ignore-rules", "-z", "{prompt}", "-t", ""],
    },
}


class CatalogError(ValueError):
    pass


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"cannot load {path.relative_to(ROOT)}: {error}") from error


def package_path(relative):
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts:
        raise CatalogError(f"manifest path escapes repository: {relative}")
    path = (ROOT / Path(*value.parts)).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise CatalogError(f"manifest path escapes repository: {relative}")
    return path


def validate_manifest(path, manifest):
    if not isinstance(manifest, dict):
        raise CatalogError(f"manifest is not an object: {path.relative_to(ROOT)}")
    unknown = set(manifest) - MANIFEST_FIELDS
    if unknown:
        raise CatalogError(f"unknown manifest fields in {path.relative_to(ROOT)}: {sorted(unknown)}")
    if manifest.get("$schema") != PLUGIN_SCHEMA:
        raise CatalogError(f"unsupported manifest schema: {path.relative_to(ROOT)}")
    name = manifest.get("name")
    if not isinstance(name, str) or not re.fullmatch(
        r"(?=.{1,64}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", name
    ):
        raise CatalogError(f"invalid plugin name: {name!r}")
    if "--" in name or ".." in name:
        raise CatalogError(f"invalid repeated separator in plugin name: {name}")
    author = manifest.get("author")
    if author is not None and (
        not isinstance(author, dict)
        or not set(author).issubset({"name", "email", "url"})
        or not all(isinstance(value, str) for value in author.values())
    ):
        raise CatalogError(f"invalid author object: {path.relative_to(ROOT)}")
    extensions = manifest.get("extensions")
    if extensions is not None and (
        not isinstance(extensions, dict)
        or not all(isinstance(value, dict) for value in extensions.values())
    ):
        raise CatalogError(f"invalid extensions object: {path.relative_to(ROOT)}")


def load_inventory():
    catalog = load_json(CATALOG_PATH)
    if not isinstance(catalog, dict) or set(catalog) != {"plugins"}:
        raise CatalogError("catalog must contain only a plugins array")
    entries = catalog["plugins"]
    if not isinstance(entries, list):
        raise CatalogError("catalog plugins must be an array")
    rows = []
    paths = set()
    names = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "manifest",
            "required",
            "category",
            "platforms",
            "dependencies",
        } and set(entry) != {
            "manifest", "required", "category", "platforms", "dependencies",
            "runtime_ready_required",
        }:
            raise CatalogError("catalog entry fields are invalid")
        relative = entry["manifest"]
        if not isinstance(relative, str) or relative in paths:
            raise CatalogError(f"duplicate or invalid manifest path: {relative!r}")
        if not isinstance(entry["category"], str) or not entry["category"]:
            raise CatalogError(f"invalid category for {relative}")
        if not isinstance(entry["required"], bool):
            raise CatalogError(f"invalid required flag for {relative}")
        platforms = entry["platforms"]
        if (
            not isinstance(platforms, list)
            or len(platforms) != len(set(platforms))
            or not set(platforms).issubset(CATALOG_PLATFORMS)
        ):
            raise CatalogError(f"invalid platforms for {relative}")
        dependencies = entry["dependencies"]
        if not isinstance(dependencies, list) or not all(
            isinstance(value, str) for value in dependencies
        ):
            raise CatalogError(f"invalid dependencies for {relative}")
        if "runtime_ready_required" in entry and not isinstance(entry["runtime_ready_required"], bool):
            raise CatalogError(f"invalid runtime readiness flag for {relative}")
        path = package_path(relative)
        if not path.is_file():
            raise CatalogError(f"missing manifest: {relative}")
        manifest = load_json(path)
        validate_manifest(path, manifest)
        if manifest["name"] in names:
            raise CatalogError(f"duplicate plugin name: {manifest['name']}")
        paths.add(relative)
        names.add(manifest["name"])
        rows.append((entry, manifest))
    graph = {entry["manifest"]: entry["dependencies"] for entry, _ in rows}
    for node, dependencies in graph.items():
        unknown = set(dependencies) - set(graph)
        if unknown:
            raise CatalogError(f"unknown dependencies for {node}: {sorted(unknown)}")
    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            raise CatalogError(f"dependency cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    required = [entry["manifest"] for entry, _ in rows if entry["required"]]
    if required != ["plugin.json"]:
        raise CatalogError("only the root plugin may be required")
    return rows


def source_path(manifest_path):
    parent = PurePosixPath(manifest_path).parent.as_posix()
    return "./" if parent == "." else f"./{parent}"


def native_manifest_path(manifest_path, platform):
    package = package_path(manifest_path).parent
    return package / NATIVE_DIRS[platform] / "plugin.json"


def descriptor_native_path(manifest_path, platform):
    parent = PurePosixPath(manifest_path).parent
    parts = [".."]
    if parent.as_posix() != ".":
        parts.extend(parent.parts)
    parts.extend((NATIVE_DIRS[platform], "plugin.json"))
    return PurePosixPath(*parts).as_posix()


def native_metadata(manifest):
    return {key: manifest[key] for key in NATIVE_METADATA_FIELDS if key in manifest}


def display_name(name):
    acronyms = {"ai": "AI", "gpt": "GPT", "mcp": "MCP", "ppt": "PPT"}
    return " ".join(
        acronyms.get(part, part.title())
        for part in name.replace(".", "-").split("-")
        if part
    )


def publisher_name(manifest):
    author = manifest.get("author", {})
    if isinstance(author.get("name"), str) and author["name"]:
        return author["name"]
    return display_name(manifest["name"].split("-", 1)[0])


def codex_manifest(entry, manifest):
    title = display_name(manifest["name"])
    description = manifest.get("description", f"{title} plugin.")
    payload = native_metadata(manifest)
    payload["author"] = manifest.get("author", {"name": publisher_name(manifest)})
    payload["skills"] = "./skills/"
    interface = {
        "displayName": title,
        "shortDescription": description,
        "longDescription": description,
        "developerName": publisher_name(manifest),
        "category": entry["category"].replace("-", " ").title(),
        "capabilities": ["Interactive"],
        "defaultPrompt": [f"Use {title} for this task."],
    }
    if "homepage" in manifest:
        interface["websiteURL"] = manifest["homepage"]
    payload["interface"] = interface
    return payload


def minimal_native_manifest(manifest):
    return native_metadata(manifest)


def codex_marketplace(rows):
    return {
        "name": "clonamic",
        "interface": {"displayName": "Clonamic"},
        "plugins": [
            {
                "name": manifest["name"],
                "source": {"source": "local", "path": source_path(entry["manifest"])},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": entry["category"],
            }
            for entry, manifest in rows
            if "codex" in entry["platforms"]
        ],
    }


def claude_marketplace(rows, platform="claude"):
    return {
        "name": "clonamic",
        "description": "Portable Agent Plugins from Clonamic",
        "owner": {"name": "Clonamic"},
        "plugins": [
            {
                "name": manifest["name"],
                "description": manifest.get("description", ""),
                "version": manifest.get("version"),
                "source": source_path(entry["manifest"]),
                "category": entry["category"],
                "tags": manifest.get("keywords", []),
            }
            for entry, manifest in rows
            if platform in entry["platforms"]
        ],
    }


def grok_marketplace(rows):
    payload = claude_marketplace(rows, platform="grok")
    payload["plugins"] = [
        {
            **row,
            "source": {"type": "local", "path": row["source"]},
        }
        for row in payload["plugins"]
    ]
    return payload


def descriptor(platform, rows):
    marketplace = {
        "codex": "../.agents/plugins/marketplace.json",
        "claude": "../.claude-plugin/marketplace.json",
        "grok": "../.grok-plugin/marketplace.json",
    }.get(platform)
    payload = {
        "namespace": NAMESPACE,
        "platform": platform,
        "catalog": "../catalog/plugins.json",
        "configuration": "../clonamic.json",
        "plugins": [],
    }
    if marketplace is not None:
        payload["marketplace"] = marketplace
    for entry, manifest in rows:
        if platform not in entry["platforms"]:
            continue
        row = {
            "manifest": f"../{entry['manifest']}",
            "name": manifest["name"],
            "description": manifest.get("description", ""),
            "required": entry["required"],
            "runtimeReadyRequired": entry.get("runtime_ready_required", False),
        }
        if "version" in manifest:
            row["version"] = manifest["version"]
        if platform in NATIVE_DIRS:
            row["nativeManifest"] = descriptor_native_path(entry["manifest"], platform)
        payload["plugins"].append(row)
    return payload


def render(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def expected_outputs():
    rows = load_inventory()
    outputs = {
        MARKETPLACE_PATHS["codex"]: render(codex_marketplace(rows)),
        MARKETPLACE_PATHS["claude"]: render(claude_marketplace(rows)),
        MARKETPLACE_PATHS["grok"]: render(grok_marketplace(rows)),
    }
    for platform in PLATFORMS:
        outputs[DESCRIPTOR_ROOT / f"{platform}.json"] = render(descriptor(platform, rows))
    for entry, manifest in rows:
        outputs[native_manifest_path(entry["manifest"], "codex")] = render(
            codex_manifest(entry, manifest)
        )
        for platform in ("claude", "grok"):
            outputs[native_manifest_path(entry["manifest"], platform)] = render(
                minimal_native_manifest(manifest)
            )
    template = EXECUTOR_TEMPLATE.read_text(encoding="utf-8")
    for name, provider in EXECUTOR_PROVIDERS.items():
        payload = json.dumps(provider, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        outputs[
            ROOT / "plugins" / name / "skills" / name / "scripts" / "call.py"
        ] = template.replace("__CLONAMIC_PROVIDER__", payload)
    return outputs


def managed_output_paths(root=ROOT):
    root = Path(root)
    outputs = set()
    outputs.update((root / ".agents/plugins").glob("*.json"))
    outputs.update((root / ".claude-plugin").glob("*.json"))
    outputs.update((root / ".grok-plugin").glob("*.json"))
    outputs.update((root / NAMESPACE).glob("*.json"))
    for package in (root, *sorted((root / "plugins").glob("*"))):
        for directory in NATIVE_DIRS.values():
            manifest = package / directory / "plugin.json"
            if manifest.is_file():
                outputs.add(manifest)
    for path in (root / "plugins").glob("*/skills/*/scripts/call.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "PROVIDER = json.loads(r'''" in source:
            outputs.add(path)
    return outputs


def main():
    parser = argparse.ArgumentParser(description="Generate client adapters from catalog manifests.")
    parser.add_argument("--check", action="store_true", help="Fail if generated files drift.")
    args = parser.parse_args()
    try:
        outputs = expected_outputs()
    except CatalogError as error:
        print(f"catalog error: {error}", file=sys.stderr)
        return 2
    if args.check:
        expected_paths = set(outputs)
        drift = [
            path.relative_to(ROOT)
            for path, expected in outputs.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != expected
        ]
        drift.extend(path.relative_to(ROOT) for path in managed_output_paths() - expected_paths)
        drift = sorted(set(drift))
        if drift:
            for path in drift:
                print(f"DRIFT {path}")
            return 1
        print(f"adapter outputs are current: {len(outputs)}/{len(outputs)}")
        return 0
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"generated {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
