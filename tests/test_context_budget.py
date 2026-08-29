from __future__ import annotations

import json
import re
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
CORE_SKILLS = {
    "clonamic-router",
    "clonamic-intent-guard",
    "clonamic-team-control",
}
ROOT_GUIDANCE = ROOT / "clonamic-herness-plugin.md"


def skill_paths():
    return sorted(ROOT.glob("skills/*/SKILL.md")) + sorted(
        ROOT.glob("plugins/*/skills/*/SKILL.md")
    )


def description(path: Path):
    match = re.search(r"(?m)^description: (.+)$", path.read_text(encoding="utf-8"))
    if match is None:
        raise AssertionError(f"missing description: {path.relative_to(ROOT)}")
    return match.group(1)


class ContextBudgetTest(unittest.TestCase):
    def test_skill_metadata_and_bodies_fit_public_context_budget(self):
        paths = skill_paths()
        self.assertEqual(19, len(paths))
        self.assertLessEqual(sum(len(description(path)) for path in paths), 3_200)
        self.assertLessEqual(sum(len(path.read_bytes()) for path in paths), 24_000)

    def test_core_routing_instructions_fit_eager_budget(self):
        paths = [path for path in skill_paths() if path.parent.name in CORE_SKILLS]
        self.assertEqual(CORE_SKILLS, {path.parent.name for path in paths})
        paths.append(ROOT_GUIDANCE)
        self.assertLessEqual(sum(len(path.read_bytes()) for path in paths), 5_000)

    def test_every_canonical_package_and_citation_use_version_0_1_0(self):
        catalog = json.loads((ROOT / "catalog" / "plugins.json").read_text(encoding="utf-8"))
        versions = {}
        for entry in catalog["plugins"]:
            path = ROOT / PurePosixPath(entry["manifest"])
            versions[str(path.relative_to(ROOT))] = json.loads(
                path.read_text(encoding="utf-8")
            )["version"]
        self.assertEqual({"0.1.0"}, set(versions.values()), versions)
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertRegex(citation, r"(?m)^version: 0\.1\.0$")

        generated = sorted(ROOT.glob("**/.codex-plugin/plugin.json"))
        generated += sorted(ROOT.glob("**/.claude-plugin/plugin.json"))
        generated += sorted(ROOT.glob("**/.grok-plugin/plugin.json"))
        self.assertEqual(30, len(generated))
        self.assertEqual(
            {"0.1.0"},
            {json.loads(path.read_text(encoding="utf-8"))["version"] for path in generated},
        )
        descriptors = sorted((ROOT / "io.github.algocean1204.clonamic").glob("*.json"))
        self.assertEqual(4, len(descriptors))
        descriptor_versions = {
            row["version"]
            for path in descriptors
            for row in json.loads(path.read_text(encoding="utf-8"))["plugins"]
        }
        self.assertEqual({"0.1.0"}, descriptor_versions)
        for relative in (
            ".claude-plugin/marketplace.json",
            ".grok-plugin/marketplace.json",
        ):
            rows = json.loads((ROOT / relative).read_text(encoding="utf-8"))["plugins"]
            self.assertEqual({"0.1.0"}, {row["version"] for row in rows})


if __name__ == "__main__":
    unittest.main()
