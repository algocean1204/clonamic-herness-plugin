import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_manifest_and_skill_are_closed(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-documents-plugin", manifest["name"])
        self.assertEqual(["clonamic-hwpx"], [p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")])


if __name__ == "__main__":
    unittest.main()
