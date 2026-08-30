from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {
    "clonamic-herness-plugin",
    "clonamic-code-plugin",
    "clonamic-preprocessing",
    "clonamic-memory",
    "clonamic-grok",
    "clonamic-gpt",
    "clonamic-claude",
    "clonamic-hermes",
}
SELECTIVE = {
    "clonamic-writing-plugin",
    "clonamic-ppt",
    "clonamic-design-plugin",
    "clonamic-data-plugin",
    "clonamic-documents-plugin",
}
CODE_SKILLS = {
    "clonamic-code-router",
    "clonamic-supercoder",
    "clonamic-modular-design",
    "clonamic-ultracode",
}


class AssetPolicyTest(unittest.TestCase):
    def test_package_contracts_do_not_copy_complete_trees_to_test_discovery(self):
        source = (ROOT / "tests/test_package.py").read_text(encoding="utf-8")
        self.assertNotIn("shutil.copytree", source)
        self.assertNotIn("TemporaryDirectory", source)

    def test_catalog_matches_active_and_selective_policy(self):
        catalog = json.loads((ROOT / "catalog/plugins.json").read_text(encoding="utf-8"))
        names = {
            json.loads((ROOT / row["manifest"]).read_text(encoding="utf-8"))["name"]
            for row in catalog["plugins"]
        }
        self.assertEqual(ACTIVE | SELECTIVE, names)

    def test_code_plugin_has_one_public_surface_with_four_skills(self):
        package = ROOT / "plugins/clonamic-code-plugin"
        manifest = json.loads((package / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-code-plugin", manifest["name"])
        skills = {path.parent.name for path in (package / "skills").glob("*/SKILL.md")}
        self.assertEqual(CODE_SKILLS, skills)
        for name in ("clonamic-supercoder", "clonamic-ultracode"):
            metadata = (package / "skills" / name / "agents/openai.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("allow_implicit_invocation: false", metadata)

    def test_external_methods_have_one_notice_and_no_runtime_hooks(self):
        package = ROOT / "plugins/clonamic-code-plugin"
        notices = (package / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for owner in ("Dietrich Gebert", "Jesse Vincent", "Garry Tan"):
            self.assertIn(owner, notices)
        production = "\n".join(
            path.read_text(encoding="utf-8")
            for path in package.rglob("*")
            if path.is_file() and "tests" not in path.parts
        ).casefold()
        for forbidden in ("sessionstart", "telemetry", "subagent-driven-development"):
            self.assertNotIn(forbidden, production)

    def test_public_identifiers_are_clonamic_without_legacy_branding(self):
        forbidden = re.compile(
            r"(?<![a-z0-9])(?:clx(?:-[a-z0-9-]+)?|cluxion)(?![a-z0-9])"
        )
        exemptions = {"THIRD_PARTY_NOTICES.md", "migration.md"}
        findings = []
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or {".git", "target", "node_modules", "__pycache__"} & set(path.parts)
                or path.name in exemptions
                or "tests" in path.parts
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if forbidden.search(text.casefold()):
                findings.append(str(path.relative_to(ROOT)))
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
