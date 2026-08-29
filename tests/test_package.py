from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "plugins.json"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
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
EXPECTED_PACKAGES = {
    "clonamic-herness-plugin",
    "clonamic-code-plugin",
    "clonamic-writing-plugin",
    "clonamic-design-plugin",
    "clonamic-data-plugin",
    "clonamic-documents-plugin",
    "clonamic-ppt",
    "clonamic-preprocessing",
    "clonamic-memory",
    "clonamic-grok",
    "clonamic-gpt",
    "clonamic-claude",
    "clonamic-hermes",
}
PLATFORMS = {"codex", "claude", "grok", "hermes"}
CATALOG_PLATFORMS = {*PLATFORMS, "agent-plugins"}
MARKETPLACES = {
    "codex": ROOT / ".agents" / "plugins" / "marketplace.json",
    "claude": ROOT / ".claude-plugin" / "marketplace.json",
    "grok": ROOT / ".grok-plugin" / "marketplace.json",
}
DESCRIPTORS = {
    platform: ROOT / "io.github.algocean1204.clonamic" / f"{platform}.json"
    for platform in PLATFORMS
}
NATIVE_DIRS = {
    "codex": ".codex-plugin",
    "claude": ".claude-plugin",
    "grok": ".grok-plugin",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_inventory():
    catalog = load_json(CATALOG_PATH)
    rows = []
    for entry in catalog["plugins"]:
        manifest_path = ROOT / PurePosixPath(entry["manifest"])
        rows.append((entry, manifest_path, load_json(manifest_path)))
    return catalog, rows


class PackageContractTest(unittest.TestCase):
    def test_all_manifests_are_closed_agent_plugins_1_0_packages(self):
        _, rows = load_inventory()
        self.assertEqual(13, len(rows))
        self.assertEqual(EXPECTED_PACKAGES, {manifest["name"] for _, _, manifest in rows})
        for _, path, manifest in rows:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(SCHEMA, manifest["$schema"])
                self.assertLessEqual(set(manifest), MANIFEST_FIELDS)
                self.assertRegex(
                    manifest["name"],
                    r"^(?=.{1,64}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$",
                )
                self.assertNotIn("--", manifest["name"])
                self.assertNotIn("..", manifest["name"])
                expected_license = (
                    "MIT AND Apache-2.0 AND CC-BY-4.0 AND LGPL-2.1-only"
                    if manifest["name"] == "clonamic-design-plugin"
                    else "MIT"
                )
                self.assertEqual(expected_license, manifest["license"])
                if "author" in manifest:
                    self.assertLessEqual(set(manifest["author"]), {"name", "email", "url"})
                if "extensions" in manifest:
                    self.assertTrue(
                        all(isinstance(value, dict) for value in manifest["extensions"].values())
                    )

    def test_catalog_is_contained_unique_and_acyclic(self):
        catalog, rows = load_inventory()
        self.assertEqual({"plugins"}, set(catalog))
        self.assertEqual(13, len(catalog["plugins"]))
        root = ROOT.resolve()
        manifests = set()
        names = set()
        graph = {}
        for entry, path, manifest in rows:
            with self.subTest(manifest=entry["manifest"]):
                self.assertEqual(
                    {"manifest", "required", "category", "platforms", "dependencies"}, set(entry)
                )
                self.assertNotIn("name", entry)
                self.assertNotIn("version", entry)
                self.assertIsInstance(entry["required"], bool)
                relative = PurePosixPath(entry["manifest"])
                self.assertFalse(relative.is_absolute())
                self.assertNotIn("..", relative.parts)
                self.assertTrue(path.resolve().is_relative_to(root))
                self.assertTrue(path.is_file())
                self.assertNotIn(entry["manifest"], manifests)
                self.assertNotIn(manifest["name"], names)
                manifests.add(entry["manifest"])
                names.add(manifest["name"])
                self.assertIsInstance(entry["category"], str)
                self.assertTrue(entry["category"])
                self.assertEqual(len(entry["platforms"]), len(set(entry["platforms"])))
                self.assertLessEqual(set(entry["platforms"]), CATALOG_PLATFORMS)
                graph[entry["manifest"]] = entry["dependencies"]
        for dependencies in graph.values():
            self.assertLessEqual(set(dependencies), set(graph))

        visiting = set()
        visited = set()

        def visit(node):
            if node in visiting:
                self.fail(f"catalog dependency cycle at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    def test_each_package_is_independently_discoverable(self):
        _, rows = load_inventory()
        for _, manifest_path, manifest in rows:
            package = manifest_path.parent
            direct = sorted((package / "skills").glob("*/SKILL.md"))
            with self.subTest(package=manifest["name"]):
                self.assertTrue(direct)
                self.assertEqual(direct, sorted((package / "skills").rglob("SKILL.md")))
                for skill_path in direct:
                    text = skill_path.read_text(encoding="utf-8")
                    self.assertRegex(text, rf"(?m)^name: {re.escape(skill_path.parent.name)}$")
                    self.assertRegex(text, r"(?m)^description: .+$")
                    self.assertNotIn("TODO", text)
                with tempfile.TemporaryDirectory() as temporary:
                    isolated = Path(temporary) / manifest["name"]
                    isolated.mkdir()
                    shutil.copy2(manifest_path, isolated / "plugin.json")
                    shutil.copytree(package / "skills", isolated / "skills")
                    self.assertEqual(
                        manifest["name"], load_json(isolated / "plugin.json")["name"]
                    )
                    self.assertEqual(
                        [path.parent.name for path in direct],
                        [
                            path.parent.name
                            for path in sorted((isolated / "skills").glob("*/SKILL.md"))
                        ],
                    )

    def test_executor_handoff_is_complete_and_legacy_wrapper_is_absent(self):
        self.assertFalse((ROOT / "plugins" / "clonamic-herness-plugin").exists())
        for name in ("clonamic-grok", "clonamic-gpt", "clonamic-claude", "clonamic-hermes"):
            package = ROOT / "plugins" / name
            with self.subTest(package=name):
                self.assertTrue((package / "plugin.json").is_file())
                self.assertTrue((package / "skills" / name / "SKILL.md").is_file())
                self.assertTrue((package / "skills" / name / "scripts" / "call.py").is_file())
                self.assertTrue((package / "tests" / "test_call.py").is_file())

    def test_ppt_image_dependency_is_fail_closed(self):
        package = ROOT / "plugins" / "clonamic-ppt"
        manifest = load_json(package / "package.json")
        lock = load_json(package / "package-lock.json")
        self.assertEqual("file:vendor/image-size", manifest["dependencies"]["image-size"])
        self.assertEqual(
            "$image-size", manifest["overrides"]["pptxgenjs"]["image-size"]
        )
        self.assertEqual(
            "vendor/image-size",
            lock["packages"]["node_modules/image-size"]["resolved"],
        )
        guard = (package / "vendor" / "image-size" / "index.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("does not accept image inputs", guard)

    def test_public_payload_has_no_private_state_or_model_ids(self):
        private_markers = (
            "kim" + "taekyu",
            "user-" + "approvals.txt",
            "auth" + ".json",
            "agents-setting" + "-back-up",
            "Secret" + "_Project",
        )
        model_id = re.compile(r"\b(?:gpt|grok|claude)-\d+(?:\.\d+)*(?:-[a-z0-9.]+)?\b", re.I)
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or {".git", "target", "node_modules", "__pycache__"} & set(path.parts)
            ):
                continue
            try:
                raw_text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            text = raw_text.casefold()
            self.assertIsNone(
                re.search(
                    r"/Users/[^/]+/(?:Documents|Library|\.agents|\.claude|\.codex|\.grok)/",
                    raw_text,
                ),
                path.relative_to(ROOT),
            )
            for marker in private_markers:
                self.assertNotIn(marker.casefold(), text, f"{marker} in {path.relative_to(ROOT)}")
            self.assertIsNone(model_id.search(text), path.relative_to(ROOT))

    def test_generated_adapters_match_catalog_and_canonical_manifests(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate-adapters.py"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("50/50", result.stdout)
        _, rows = load_inventory()
        for platform, path in MARKETPLACES.items():
            with self.subTest(platform=platform):
                platform_rows = [
                    (entry, manifest)
                    for entry, _, manifest in rows
                    if platform in entry["platforms"]
                ]
                expected_names = [manifest["name"] for _, manifest in platform_rows]
                expected_versions = {
                    manifest["name"]: manifest.get("version")
                    for _, manifest in platform_rows
                }
                expected_sources = []
                for entry, _ in platform_rows:
                    parent = PurePosixPath(entry["manifest"]).parent.as_posix()
                    expected_sources.append("./" if parent == "." else f"./{parent}")
                payload = load_json(path)
                self.assertEqual(expected_names, [row["name"] for row in payload["plugins"]])
                actual_sources = []
                for row in payload["plugins"]:
                    source = row["source"]
                    actual_sources.append(source["path"] if isinstance(source, dict) else source)
                self.assertEqual(expected_sources, actual_sources)
                if platform != "codex":
                    self.assertEqual(
                        expected_versions,
                        {row["name"]: row.get("version") for row in payload["plugins"]},
                    )
        for platform, path in DESCRIPTORS.items():
            with self.subTest(descriptor=platform):
                expected_names = [
                    manifest["name"]
                    for entry, _, manifest in rows
                    if platform in entry["platforms"]
                ]
                payload = load_json(path)
                self.assertEqual("io.github.algocean1204.clonamic", payload["namespace"])
                self.assertEqual(platform, payload["platform"])
                self.assertEqual(expected_names, [row["name"] for row in payload["plugins"]])
                for row in payload["plugins"]:
                    if platform in NATIVE_DIRS:
                        native = (path.parent / row["nativeManifest"]).resolve()
                        self.assertTrue(native.is_file(), native)
                    else:
                        self.assertNotIn("nativeManifest", row)

    def test_native_manifests_derive_only_from_canonical_package_manifests(self):
        _, rows = load_inventory()
        minimal_fields = (
            "name",
            "version",
            "description",
            "author",
            "homepage",
            "repository",
            "license",
            "keywords",
        )
        for entry, manifest_path, canonical in rows:
            package = manifest_path.parent
            expected_minimal = {
                key: canonical[key] for key in minimal_fields if key in canonical
            }
            for platform, directory in NATIVE_DIRS.items():
                with self.subTest(package=canonical["name"], platform=platform):
                    native_path = package / directory / "plugin.json"
                    self.assertTrue(native_path.is_file(), native_path)
                    native = load_json(native_path)
                    self.assertNotIn("$schema", native)
                    if platform == "codex":
                        for key, value in expected_minimal.items():
                            self.assertEqual(value, native[key])
                        self.assertEqual("./skills/", native["skills"])
                        self.assertEqual(
                            entry["category"].replace("-", " ").title(),
                            native["interface"]["category"],
                        )
                    else:
                        self.assertEqual(expected_minimal, native)

    def test_native_manifest_and_direct_skills_travel_together_in_isolation(self):
        _, rows = load_inventory()
        for _, manifest_path, canonical in rows:
            package = manifest_path.parent
            expected_skills = [
                path.parent.name for path in sorted((package / "skills").glob("*/SKILL.md"))
            ]
            for platform, directory in NATIVE_DIRS.items():
                with self.subTest(package=canonical["name"], platform=platform):
                    with tempfile.TemporaryDirectory() as temporary:
                        isolated = Path(temporary) / canonical["name"]
                        isolated.mkdir()
                        shutil.copytree(package / "skills", isolated / "skills")
                        shutil.copytree(package / directory, isolated / directory)
                        native = load_json(isolated / directory / "plugin.json")
                        discovered = [
                            path.parent.name
                            for path in sorted((isolated / "skills").glob("*/SKILL.md"))
                        ]
                        self.assertEqual(canonical["name"], native["name"])
                        self.assertEqual(expected_skills, discovered)

    def test_executor_packages_are_not_offered_to_their_own_host(self):
        self_targets = {
            "codex": "clonamic-gpt",
            "claude": "clonamic-claude",
            "grok": "clonamic-grok",
            "hermes": "clonamic-hermes",
        }
        for platform, descriptor in DESCRIPTORS.items():
            names = {row["name"] for row in load_json(descriptor)["plugins"]}
            self.assertNotIn(self_targets[platform], names)

    def test_ci_uses_the_offline_local_validation_entrypoint(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        validator = (ROOT / "scripts" / "validate-public.py").read_text(encoding="utf-8")
        self.assertIn("python scripts/validate-public.py", workflow)
        self.assertIn("generate-adapters.py", validator)
        self.assertIn("cargo", validator)
        self.assertIn("unittest", validator)
        self.assertIn("CARGO_NET_OFFLINE", validator)
        self.assertIn("cargo fetch --locked", workflow)
        for network_client in ("curl ", "wget ", "requests.", "urllib."):
            self.assertNotIn(network_client, validator)


if __name__ == "__main__":
    unittest.main()
