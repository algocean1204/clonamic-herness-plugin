import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MANIFEST_FIELDS = {"$schema", "name", "version", "description", "license", "keywords"}


def load_runtime(root):
    path = Path(root) / "skills" / "clonamic-memory" / "scripts" / "memory.py"
    if not path.is_file():
        raise AssertionError("skill-relative memory runtime is missing")
    spec = importlib.util.spec_from_file_location(f"clonamic_memory_{os.getpid()}_{id(path)}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class MemoryPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "package"
        shutil.copytree(ROOT, self.root)
        self.runtime = load_runtime(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def database_path(self):
        return self.root / "state" / "memory.sqlite3"

    def test_closed_manifest_and_single_direct_skill(self):
        manifest = json.loads((self.root / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(SCHEMA, manifest["$schema"])
        self.assertEqual(MANIFEST_FIELDS, set(manifest))
        self.assertEqual("clonamic-memory", manifest["name"])
        self.assertEqual("MIT", manifest["license"])
        skills = list((self.root / "skills").glob("*/SKILL.md"))
        self.assertEqual(["clonamic-memory"], [path.parent.name for path in skills])
        self.assertTrue((skills[0].parent / "agents" / "openai.yaml").is_file())
        self.assertFalse((self.root / "scripts").exists())

    def test_explicit_store_recall_and_forget(self):
        database = self.database_path()
        self.runtime.store(database, "m1", "Module boundaries need evidence", ["architecture"])
        self.runtime.store(database, "m2", "Queue work by priority", ["queue"])
        rows = self.runtime.recall(database, "module evidence", limit=5)
        self.assertEqual("m1", rows[0]["id"])
        self.assertTrue(self.runtime.forget(database, "m1"))
        self.assertEqual([], self.runtime.recall(database, "module evidence", limit=5))
        self.assertFalse(self.runtime.forget(database, "missing"))

    def test_store_updates_existing_id_without_duplication(self):
        database = self.database_path()
        self.runtime.store(database, "m1", "old value", [])
        self.runtime.store(database, "m1", "new value", ["current"])
        rows = self.runtime.recall(database, "new value", limit=5)
        self.assertEqual(1, len(rows))
        self.assertEqual(["current"], rows[0]["tags"])

    def test_graph_is_bounded_cycle_safe_and_forget_cascades_edges(self):
        database = self.database_path()
        for memory_id in ("a", "b", "c"):
            self.runtime.store(database, memory_id, f"node {memory_id}", [])
        self.runtime.link(database, "a", "b", "relates_to")
        self.runtime.link(database, "b", "c", "supports")
        self.runtime.link(database, "c", "a", "revises")
        graph = self.runtime.graph(database, "a", depth=2, limit=10)
        self.assertEqual({"a", "b", "c"}, {row["id"] for row in graph["nodes"]})
        self.assertEqual(3, len(graph["edges"]))
        self.runtime.forget(database, "b")
        graph = self.runtime.graph(database, "a", depth=2, limit=10)
        self.assertEqual({"a", "c"}, {row["id"] for row in graph["nodes"]})
        self.assertTrue(all("b" not in (edge["source"], edge["target"]) for edge in graph["edges"]))

    def test_link_rejects_missing_nodes_and_self_edges(self):
        database = self.database_path()
        self.runtime.store(database, "a", "node a", [])
        with self.assertRaises(KeyError):
            self.runtime.link(database, "a", "missing", "relates_to")
        with self.assertRaises(ValueError):
            self.runtime.link(database, "a", "a", "relates_to")

    def test_production_surface_excludes_automatic_or_cross_package_state(self):
        forbidden = (
            "hot_" + "inject",
            "prompt " + "injection",
            "pre" + "processing",
            "app" + "roval",
            "ses" + "sion",
            "mo" + "del",
            "au" + "th_",
            "creden" + "tials",
        )
        for path in self.root.rglob("*"):
            if not path.is_file() or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8").casefold()
            for token in forbidden:
                self.assertNotIn(token, text, f"{token} in {path.relative_to(self.root)}")


if __name__ == "__main__":
    unittest.main()
