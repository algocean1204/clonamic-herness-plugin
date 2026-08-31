from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = (
    ROOT / "io.github.algocean1204.clonamic/adapters/install-cursor.py"
)


def load_installer():
    spec = importlib.util.spec_from_file_location("clonamic_cursor_installer", INSTALLER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CursorAdapterTest(unittest.TestCase):
    def test_install_toggle_doctor_uninstall_and_preimage_restore(self):
        installer = load_installer()
        with tempfile.TemporaryDirectory(prefix="clonamic-cursor-install-") as temporary:
            root = Path(temporary)
            target = root / ".cursor/plugins/local"
            state = root / ".cursor/clonamic/install-state.json"
            collision = target / "clonamic-memory"
            collision.mkdir(parents=True)
            (collision / "sentinel.txt").write_text("original\n", encoding="utf-8")

            installed = installer.install(target, state, [ROOT / "clonamic.json"])
            self.assertEqual(14, len(installed["plugins"]))
            self.assertFalse((target / "clonamic-memory/sentinel.txt").exists())
            core = target / "clonamic-herness-plugin"
            self.assertTrue((core / ".cursor-plugin/plugin.json").is_file())
            self.assertTrue((core / "rules/clonamic-operating-contract.mdc").is_file())
            self.assertFalse((core / "plugin.json").exists())
            self.assertEqual("verified", installer.doctor(target, state)["action"])

            overlay = root / "disable-memory.json"
            overlay.write_text(
                json.dumps({"plugins": {"clonamic-memory": False}}),
                encoding="utf-8",
            )
            disabled = installer.install(
                target,
                state,
                [ROOT / "clonamic.json", overlay],
            )
            self.assertNotIn("clonamic-memory", disabled["plugins"])
            self.assertEqual(
                "original\n",
                (target / "clonamic-memory/sentinel.txt").read_text(encoding="utf-8"),
            )

            installer.install(target, state, [ROOT / "clonamic.json"])
            removed = installer.uninstall(target, state)
            self.assertEqual(14, len(removed["plugins"]))
            self.assertFalse(state.exists())
            self.assertEqual(
                "original\n",
                (target / "clonamic-memory/sentinel.txt").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                [Path("clonamic-memory")],
                sorted(path.relative_to(target) for path in target.iterdir()),
            )

    def test_modified_managed_plugin_blocks_update_and_uninstall(self):
        installer = load_installer()
        with tempfile.TemporaryDirectory(prefix="clonamic-cursor-drift-") as temporary:
            root = Path(temporary)
            target = root / "plugins/local"
            state = root / "state/install-state.json"
            installer.install(target, state, [ROOT / "clonamic.json"])
            changed = target / "clonamic-herness-plugin/clonamic-herness-plugin.md"
            changed.write_text(changed.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
            with self.assertRaises(installer.InstallError):
                installer.doctor(target, state)
            with self.assertRaises(installer.InstallError):
                installer.install(target, state, [ROOT / "clonamic.json"])
            with self.assertRaises(installer.InstallError):
                installer.uninstall(target, state)

    def test_failed_update_restores_previous_installation(self):
        installer = load_installer()
        with tempfile.TemporaryDirectory(prefix="clonamic-cursor-rollback-") as temporary:
            root = Path(temporary)
            target = root / "plugins/local"
            state = root / "state/install-state.json"
            only_core = root / "only-core.json"
            optional = json.loads((ROOT / "clonamic.json").read_text(encoding="utf-8"))["plugins"]
            only_core.write_text(
                json.dumps({"plugins": {name: False for name in optional}}),
                encoding="utf-8",
            )
            installer.install(
                target,
                state,
                [ROOT / "clonamic.json", only_core],
            )
            before_state = state.read_bytes()
            before_digest = installer.tree_digest(target / "clonamic-herness-plugin")
            original_copy = installer.copy_directory

            def fail_on_memory(source, destination):
                if destination == target / "clonamic-memory":
                    raise OSError("injected copy failure")
                return original_copy(source, destination)

            with mock.patch.object(installer, "copy_directory", side_effect=fail_on_memory):
                with self.assertRaises(OSError):
                    installer.install(target, state, [ROOT / "clonamic.json"])

            self.assertEqual(before_state, state.read_bytes())
            self.assertEqual(
                before_digest,
                installer.tree_digest(target / "clonamic-herness-plugin"),
            )
            self.assertFalse((target / "clonamic-memory").exists())
            self.assertEqual("verified", installer.doctor(target, state)["action"])


if __name__ == "__main__":
    unittest.main()
