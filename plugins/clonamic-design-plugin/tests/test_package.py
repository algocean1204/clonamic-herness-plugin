import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_manifest_and_skills_are_closed(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-design-plugin", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual(
            "MIT AND Apache-2.0 AND CC-BY-4.0 AND LGPL-2.1-only",
            manifest["license"],
        )
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 10)
        self.assertEqual(skills, sorted((ROOT / "skills").rglob("SKILL.md")))


if __name__ == "__main__":
    unittest.main()
