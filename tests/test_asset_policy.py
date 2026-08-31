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
    "clonamic-my-language-plugin",
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

    def test_my_language_child_is_optional_versioned_and_explicit_only(self):
        package = ROOT / "plugins/clonamic-my-language-plugin"
        manifest = json.loads((package / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-my-language-plugin", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        skills = {
            "clonamic-my-language",
            "clonamic-my-language-export",
            "clonamic-my-language-review",
        }
        self.assertEqual(
            skills,
            {path.parent.name for path in (package / "skills").glob("*/SKILL.md")},
        )
        for name in skills:
            skill = (package / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            metadata = (package / "skills" / name / "agents/openai.yaml").read_text(
                encoding="utf-8"
            )
            with self.subTest(skill=name):
                self.assertIn("disable-model-invocation: true", skill)
                self.assertIn("allow_implicit_invocation: false", metadata)

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

    def test_portable_runtime_has_no_implicit_legacy_memory_backend(self):
        findings = []
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or {".git", "target", "node_modules", "__pycache__"} & set(path.parts)
                or path.name == "migration.md"
                or "tests" in path.parts
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8").casefold()
            except UnicodeDecodeError:
                continue
            if "forgetforge" in text:
                findings.append(str(path.relative_to(ROOT)))
        self.assertEqual([], findings)

    def test_core_skills_have_portable_fallbacks_without_vendor_home_paths(self):
        session = (ROOT / "skills/clonamic-session-intent/SKILL.md").read_text(encoding="utf-8")
        market = (ROOT / "skills/clonamic-market/SKILL.md").read_text(encoding="utf-8")
        context = (ROOT / "skills/clonamic-context-integrity/SKILL.md").read_text(encoding="utf-8")
        for text in (session, market, context):
            self.assertNotIn("~/.claude", text)
            self.assertNotIn("~/.codex", text)
            self.assertNotIn("CLAUDE.md", text)
        self.assertIn("Portable fallback", session)
        self.assertIn("Never enumerate sibling sessions", session)
        self.assertIn("when the binary is available", market)
        self.assertIn("model-side", market)
        self.assertNotIn("checkpoint critical state to disk", context)
        self.assertIn("Never create a scratchpad, memory row, or checkpoint file", context)
        self.assertIn("conversation fallback", context)

        for skill_path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            text = skill_path.read_text(encoding="utf-8")
            with self.subTest(skill=skill_path.parent.name):
                self.assertNotIn("Harness wiring (Codex)", text)
                self.assertNotIn("~/.claude", text)
                self.assertNotIn("~/.codex", text)

    def test_core_skill_cross_references_resolve_inside_the_root_package(self):
        root_skills = {
            path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
        }
        session = (ROOT / "skills/clonamic-session-intent/SKILL.md").read_text(encoding="utf-8")
        for required in ("clonamic-completion-check", "clonamic-report"):
            self.assertIn(required, root_skills)
            self.assertIn(f"`{required}`", session)
        self.assertNotIn("verification-before-completion", session)

    def test_optional_figma_skill_never_launches_an_executor(self):
        skill = (
            ROOT / "plugins/clonamic-design-plugin/skills/clonamic-figma-workflow/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Never launch Claude, Codex", skill)
        self.assertIn("explicit slash command", skill)
        self.assertIn("Do not install a server", skill)

    def test_skill_commands_never_resolve_helpers_from_project_cwd(self):
        pattern = re.compile(r"\b(?:python3?|node|bash|sh)\s+(?:\./)?scripts/")
        findings = []
        roots = [ROOT / "skills", *(ROOT / "plugins").glob("*/skills")]
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*.md"):
                text = path.read_text(encoding="utf-8")
                if pattern.search(text):
                    findings.append(str(path.relative_to(ROOT)))
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
