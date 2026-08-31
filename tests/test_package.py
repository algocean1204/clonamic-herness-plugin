from __future__ import annotations

import json
import importlib.util
import hashlib
import os
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
SKILL_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
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
NAMESPACE = "io.github.algocean1204.clonamic"
MARKETPLACES = {
    platform: ROOT / NAMESPACE / "marketplaces" / f"{platform}.json"
    for platform in ("codex", "claude", "grok")
}
DESCRIPTORS = {
    platform: ROOT / NAMESPACE / f"{platform}.json"
    for platform in PLATFORMS
}
NATIVE_PLATFORMS = {"codex", "claude", "grok"}
STAGED_NATIVE_DIRS = {
    "codex": ".codex-plugin",
    "claude": ".claude-plugin",
    "grok": ".grok-plugin",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_generator():
    path = ROOT / NAMESPACE / "adapters/generate.py"
    spec = importlib.util.spec_from_file_location("clonamic_generate_adapters", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_stager():
    path = ROOT / NAMESPACE / "adapters/stage-host-marketplace.py"
    spec = importlib.util.spec_from_file_location("clonamic_stage_host", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_inventory():
    catalog = load_json(CATALOG_PATH)
    rows = []
    for entry in catalog["plugins"]:
        manifest_path = ROOT / PurePosixPath(entry["manifest"])
        rows.append((entry, manifest_path, load_json(manifest_path)))
    return catalog, rows


def top_level_frontmatter_fields(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"missing frontmatter: {path}")
    fields: set[str] = set()
    for line in lines[1:]:
        if line == "---":
            return fields
        if line and not line[0].isspace() and ":" in line:
            fields.add(line.split(":", 1)[0])
    raise AssertionError(f"unterminated frontmatter: {path}")


def canonical_digest() -> str:
    digest = hashlib.sha256()
    paths = [ROOT / "plugin.json", *sorted((ROOT / "skills").rglob("*"))]
    paths.extend(sorted((ROOT / "plugins").glob("*/plugin.json")))
    paths.extend(sorted((ROOT / "plugins").glob(f"*/{NAMESPACE}/**/plugin.json")))
    for path in paths:
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class PackageContractTest(unittest.TestCase):
    def test_managed_output_inventory_detects_obsolete_manifest_and_executor(self):
        root = Path(tempfile.mkdtemp(prefix="clonamic-managed-output-"))
        try:
            manifest = root / "plugins/obsolete/.codex-plugin/plugin.json"
            executor = root / "plugins/obsolete/skills/obsolete/scripts/call.py"
            manifest.parent.mkdir(parents=True)
            executor.parent.mkdir(parents=True)
            manifest.write_text("{}", encoding="utf-8")
            executor.write_text("PROVIDER = json.loads(r'''{}''')", encoding="utf-8")
            self.assertEqual(
                {manifest, executor},
                load_generator().managed_output_paths(root),
            )
        finally:
            shutil.rmtree(root)

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

    def test_client_files_are_namespaced_in_canonical_packages(self):
        _, rows = load_inventory()
        for _, manifest_path, _ in rows:
            package = manifest_path.parent
            with self.subTest(package=package.relative_to(ROOT)):
                for forbidden in (".codex-plugin", ".claude-plugin", ".grok-plugin", ".agents"):
                    self.assertFalse((package / forbidden).exists())
                for platform in NATIVE_PLATFORMS:
                    self.assertTrue((package / NAMESPACE / platform / "plugin.json").is_file())

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
                self.assertLessEqual(
                    set(entry),
                    {"manifest", "required", "category", "platforms", "dependencies", "runtime_ready_required"},
                )
                self.assertTrue(
                    {"manifest", "required", "category", "platforms", "dependencies"}.issubset(entry)
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
                boundary = package.resolve()
                self.assertTrue(manifest_path.resolve().is_relative_to(boundary))
                self.assertTrue(
                    all(path.resolve().is_relative_to(boundary) for path in direct)
                )

    def test_all_skill_frontmatter_uses_agent_skills_fields_only(self):
        _, rows = load_inventory()
        for _, manifest_path, _ in rows:
            for skill_path in sorted((manifest_path.parent / "skills").glob("*/SKILL.md")):
                with self.subTest(skill=skill_path.parent.name):
                    fields = top_level_frontmatter_fields(skill_path)
                    self.assertLessEqual(fields, SKILL_FRONTMATTER_FIELDS)
                    self.assertTrue({"name", "description"}.issubset(fields))

    def test_router_activation_contract_distinguishes_discovery_from_enforcement(self):
        router = (ROOT / "skills/clonamic-router/SKILL.md").read_text(encoding="utf-8")
        description = re.search(r"(?m)^description: (.+)$", router)
        self.assertIsNotNone(description)
        for capability in (
            "persistent writes",
            "deployment",
            "publication",
            "team decisions",
            "changed-work completion",
        ):
            self.assertIn(capability, description.group(1))

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        compatibility = (ROOT / "docs/COMPATIBILITY.md").read_text(encoding="utf-8")
        for document in (readme, compatibility):
            self.assertIn("proves discovery, not automatic invocation", document)
            self.assertIn("Guaranteed always-on routing requires", document)

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
                if (
                    marker == ("auth" + ".json")
                    and path == ROOT / NAMESPACE / "adapters/stage-host-marketplace.py"
                ):
                    continue
                self.assertNotIn(marker.casefold(), text, f"{marker} in {path.relative_to(ROOT)}")
            self.assertIsNone(model_id.search(text), path.relative_to(ROOT))

    def test_generated_adapters_match_catalog_and_canonical_manifests(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / NAMESPACE / "adapters/generate.py"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("50/50", result.stdout)
        generator = load_generator()
        self.assertEqual(
            set(generator.expected_outputs()),
            generator.managed_output_paths(ROOT),
        )
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
                    if platform in NATIVE_PLATFORMS:
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
            for platform in sorted(NATIVE_PLATFORMS):
                with self.subTest(package=canonical["name"], platform=platform):
                    native_path = package / NAMESPACE / platform / "plugin.json"
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

    def test_native_manifest_and_direct_skills_share_one_package_boundary(self):
        _, rows = load_inventory()
        for _, manifest_path, canonical in rows:
            package = manifest_path.parent
            boundary = package.resolve()
            expected_skills = [
                path.parent.name for path in sorted((package / "skills").glob("*/SKILL.md"))
            ]
            for platform in sorted(NATIVE_PLATFORMS):
                with self.subTest(package=canonical["name"], platform=platform):
                    native_path = package / NAMESPACE / platform / "plugin.json"
                    self.assertTrue(native_path.resolve().is_relative_to(boundary))
                    self.assertTrue((package / "skills").resolve().is_relative_to(boundary))
                    native = load_json(native_path)
                    discovered = [
                        path.parent.name
                        for path in sorted((package / "skills").glob("*/SKILL.md"))
                    ]
                    self.assertEqual(canonical["name"], native["name"])
                    self.assertEqual(expected_skills, discovered)

    def test_host_staging_is_atomic_contained_and_does_not_mutate_sources(self):
        script = ROOT / NAMESPACE / "adapters/stage-host-marketplace.py"
        before = canonical_digest()
        untracked_secret = ROOT / "plugins/clonamic-data-plugin/.env"
        self.assertFalse(untracked_secret.exists())
        untracked_secret.write_text("TOKEN=must-not-stage\n", encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory(prefix="clonamic-host-stage-") as temporary:
                temporary_path = Path(temporary)
                for platform, native_directory in STAGED_NATIVE_DIRS.items():
                    output = temporary_path / platform
                    result = subprocess.run(
                        [sys.executable, str(script), platform, str(output)],
                        cwd=ROOT,
                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertFalse(any(path.name == ".env" for path in output.rglob("*")))
                    marketplace_relative = {
                        "codex": Path(".agents/plugins/marketplace.json"),
                        "claude": Path(".claude-plugin/marketplace.json"),
                        "grok": Path(".grok-plugin/marketplace.json"),
                    }[platform]
                    marketplace = load_json(output / marketplace_relative)
                    for row in marketplace["plugins"]:
                        source = row["source"]
                        relative = source["path"] if isinstance(source, dict) else source
                        package = (output / relative).resolve()
                        self.assertTrue(package.is_relative_to(output.resolve()))
                        self.assertTrue((package / native_directory / "plugin.json").is_file())
                        self.assertTrue((package / "skills").is_dir())

                occupied = temporary_path / "occupied"
                occupied.mkdir()
                (occupied / "sentinel").write_text("keep", encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(script), "codex", str(occupied)],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(2, result.returncode)
                self.assertEqual("keep", (occupied / "sentinel").read_text(encoding="utf-8"))
                self.assertEqual([], list(temporary_path.glob(".occupied.tmp-*")))

            in_repo = ROOT / ".forbidden-host-stage"
            result = subprocess.run(
                [sys.executable, str(script), "codex", str(in_repo)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, result.returncode)
            self.assertFalse(in_repo.exists())
        finally:
            untracked_secret.unlink(missing_ok=True)
        self.assertEqual(before, canonical_digest())

    def test_stager_rejects_private_files_and_symlinks(self):
        stager = load_stager()
        with tempfile.TemporaryDirectory(prefix="clonamic-stage-safety-") as temporary:
            root = Path(temporary)
            (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            with self.assertRaises(stager.StageError):
                stager.scan_private_payload(root)
            (root / ".env").unlink()
            outside = root / "outside"
            outside.write_text("private", encoding="utf-8")
            source_root = root / "source"
            source_root.mkdir()
            link = source_root / "leak"
            link.symlink_to(outside)
            original_root = stager.ROOT
            stager.ROOT = source_root
            try:
                with self.assertRaises(stager.StageError):
                    stager.copy_tracked_file(
                        link,
                        root / "copy",
                        {Path("leak"): ("120000", "0" * 40)},
                    )
                outside_dir = root / "outside-dir"
                outside_dir.mkdir()
                (outside_dir / "file.txt").write_text("private", encoding="utf-8")
                ancestor_link = source_root / "linked"
                ancestor_link.symlink_to(outside_dir, target_is_directory=True)
                with self.assertRaises(stager.StageError):
                    stager.copy_tracked_file(
                        ancestor_link / "file.txt",
                        root / "copy-ancestor",
                        {Path("linked/file.txt"): ("100644", "0" * 40)},
                    )
            finally:
                stager.ROOT = original_root

    def test_stager_copies_index_blob_not_dirty_worktree_bytes(self):
        stager = load_stager()
        with tempfile.TemporaryDirectory(prefix="clonamic-index-stage-") as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            source = root / "payload.txt"
            source.write_text("reviewed\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "payload.txt"], check=True)
            source.write_text("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n", encoding="utf-8")
            original_root = stager.ROOT
            stager.ROOT = root
            try:
                inventory = stager.tracked_inventory()
                destination = Path(temporary) / "staged.txt"
                stager.copy_tracked_file(source, destination, inventory)
                self.assertEqual("reviewed\n", destination.read_text(encoding="utf-8"))
            finally:
                stager.ROOT = original_root

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
        release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        validator = (ROOT / "scripts" / "validate-public.py").read_text(encoding="utf-8")
        self.assertIn("python scripts/validate-public.py", workflow)
        self.assertIn("timeout-minutes:", workflow)
        self.assertIn("io.github.algocean1204.clonamic/adapters/generate.py", validator)
        self.assertIn("cargo", validator)
        self.assertIn("unittest", validator)
        self.assertIn("CARGO_NET_OFFLINE", validator)
        self.assertIn("CLONAMIC_TEST_TIMEOUT_SECONDS", validator)
        self.assertIn("cargo fetch --locked", workflow)
        self.assertIn("Validate release tag", release)
        self.assertIn("Validate runner architecture", release)
        self.assertIn("python scripts/validate-public.py", release)
        self.assertIn("clonamic-agent-plugins-v1.0.0.tar.gz", release)
        self.assertIn("stage-host-marketplace.py codex", release)
        self.assertIn("stage-host-marketplace.py claude", release)
        self.assertIn("stage-host-marketplace.py grok", release)
        self.assertIn("Smoke-test staged binary", release)
        self.assertIn("timeout-minutes:", release)
        for network_client in ("curl ", "wget ", "requests.", "urllib."):
            self.assertNotIn(network_client, validator)


if __name__ == "__main__":
    unittest.main()
