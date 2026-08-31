import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_manifest_and_skills_are_closed(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-design-plugin", manifest["name"])
        self.assertEqual("1.0.0", manifest["version"])
        self.assertEqual(
            "MIT AND Apache-2.0 AND CC-BY-4.0 AND LGPL-2.1-only",
            manifest["license"],
        )
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 10)
        self.assertEqual(skills, sorted((ROOT / "skills").rglob("SKILL.md")))

    def test_design_sources_are_revision_locked(self):
        lock = json.loads((ROOT / "design-sources.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(1, lock["schema_version"])
        self.assertEqual(10, len(lock["sources"]))
        self.assertEqual(1, len(lock["bundles"]))
        for source in lock["sources"]:
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(source["repository"].startswith("https://"))
            self.assertTrue(source["license"])
        bundle = lock["bundles"][0]
        self.assertEqual("p5.js", bundle["name"])
        for key in ("runtime_sha256", "source_sha256", "license_sha256"):
            self.assertRegex(bundle[key], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
