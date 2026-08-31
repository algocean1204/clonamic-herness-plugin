from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog/plugins.json"
CONFIG = ROOT / "clonamic.json"
SCHEMA = ROOT / "schemas/clonamic-config.schema.json"
CHILDREN = {
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


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class PluginConfigContractTest(unittest.TestCase):
    def test_catalog_marks_only_the_root_required(self):
        rows = load(CATALOG)["plugins"]
        self.assertEqual(13, len(rows))
        self.assertTrue(rows[0]["required"])
        self.assertEqual("plugin.json", rows[0]["manifest"])
        self.assertTrue(all(row["required"] is False for row in rows[1:]))
        self.assertTrue(all("agent-plugins" in row["platforms"] for row in rows))

    def test_shipped_config_has_exactly_twelve_enabled_children(self):
        payload = load(CONFIG)
        self.assertEqual({"$schema", "schema_version", "plugins"}, set(payload))
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual(CHILDREN, set(payload["plugins"]))
        self.assertTrue(all(value is True for value in payload["plugins"].values()))
        self.assertNotIn("clonamic-herness-plugin", payload["plugins"])

    def test_schema_is_closed_supports_partial_overlays_and_excludes_core(self):
        schema = load(SCHEMA)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(["schema_version", "plugins"], schema["required"])
        self.assertEqual(
            {"type": "integer", "const": 1},
            schema["properties"]["schema_version"],
        )
        plugins = schema["properties"]["plugins"]
        self.assertFalse(plugins["additionalProperties"])
        self.assertNotIn("required", plugins)
        self.assertEqual(CHILDREN, set(plugins["properties"]))
        self.assertTrue(
            all(value == {"type": "boolean"} for value in plugins["properties"].values())
        )

    def test_descriptors_add_required_and_configuration_but_marketplaces_do_not(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "io.github.algocean1204.clonamic/adapters/generate.py"),
                "--check",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for platform in ("codex", "claude", "grok", "hermes", "cursor"):
            descriptor = load(ROOT / "io.github.algocean1204.clonamic" / f"{platform}.json")
            self.assertEqual("../clonamic.json", descriptor["configuration"])
            self.assertTrue(all(isinstance(row["required"], bool) for row in descriptor["plugins"]))
        for platform in ("codex", "claude", "grok", "cursor"):
            path = (
                ROOT
                / "io.github.algocean1204.clonamic"
                / "marketplaces"
                / f"{platform}.json"
            )
            for row in load(path)["plugins"]:
                self.assertNotIn("required", row)
                self.assertNotIn("configuration", row)


if __name__ == "__main__":
    unittest.main()
