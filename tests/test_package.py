import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "clonamic-herness-plugin"


class PackageContractTest(unittest.TestCase):
    def test_json_manifests_parse_and_name_one_plugin(self):
        paths = (
            ROOT / ".agents/plugins/marketplace.json",
            ROOT / ".claude-plugin/marketplace.json",
            ROOT / ".grok-plugin/marketplace.json",
            PLUGIN / ".codex-plugin/plugin.json",
            PLUGIN / ".claude-plugin/plugin.json",
            PLUGIN / ".grok-plugin/plugin.json",
        )
        for path in paths:
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "plugin.json":
                    self.assertEqual("clonamic-herness-plugin", data["name"])
                    self.assertEqual("0.1.0", data["version"])
                else:
                    self.assertEqual("clonamic", data["name"])
                    self.assertEqual(
                        ["clonamic-herness-plugin"],
                        [plugin["name"] for plugin in data["plugins"]],
                    )

    def test_four_skills_are_complete_and_discriminating(self):
        expected = {
            "clonamic-write-control",
            "clonamic-completion-check",
            "clonamic-report",
            "clonamic-executors",
        }
        skills = {path.parent.name: path for path in (PLUGIN / "skills").glob("*/SKILL.md")}
        self.assertEqual(expected, set(skills))
        for name, path in skills.items():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("TODO", text, name)
            self.assertIn(f"name: {name}", text)
            self.assertIn("description:", text)
            self.assertTrue((path.parent / "agents/openai.yaml").is_file())

    def test_read_write_and_executor_contracts_are_unambiguous(self):
        router = (PLUGIN / "core/AGENTS.md").read_text(encoding="utf-8")
        write = (PLUGIN / "skills/clonamic-write-control/SKILL.md").read_text(encoding="utf-8")
        executors = (PLUGIN / "skills/clonamic-executors/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("read-only request are direct", router)
        self.assertIn("Clear persistent write", write)
        self.assertIn("Materially ambiguous write", write)
        self.assertIn("entire inspect-fix-retest-apply-deploy-backup loop", write)
        self.assertIn("Never select, recommend, or invoke", executors)
        for command in ("/grok", "/gpt", "/claude", "/hermes"):
            self.assertIn(command, executors)

    def test_hermes_adapter_registers_only_bundled_skills(self):
        module_path = PLUGIN / "__init__.py"
        spec = importlib.util.spec_from_file_location("clonamic_hermes_adapter", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)

        class Context:
            def __init__(self):
                self.rows = []

            def register_skill(self, name, path):
                self.rows.append((name, Path(path)))

        context = Context()
        module.register(context)
        self.assertEqual(4, len(context.rows))
        for name, path in context.rows:
            self.assertTrue((path / "SKILL.md").is_file(), name)
            self.assertTrue(path.is_relative_to(PLUGIN))

    def test_public_payload_has_no_private_machine_state(self):
        forbidden = (
            "/" + "Users" + "/",
            "kim" + "taekyu",
            "session" + "-intent",
            "user-" + "approvals.txt",
            "auth" + ".json",
            "agents-setting" + "-back-up",
            "Secret" + "_Project",
        )
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "target" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for marker in forbidden:
                self.assertNotIn(marker, text, f"{marker} in {path.relative_to(ROOT)}")

    def test_docs_expose_install_uninstall_and_limitations(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        compatibility = (ROOT / "docs/COMPATIBILITY.md").read_text(encoding="utf-8")
        for platform in ("Codex", "Claude Code", "Grok Build", "Hermes"):
            self.assertIn(platform, readme)
            self.assertIn(platform, compatibility)
        self.assertIn("uninstall-router", readme)
        self.assertIn("model-only", compatibility)

    def test_scenario_matrix_covers_friction_boundaries(self):
        scenarios = json.loads((ROOT / "tests/fixtures/scenarios.json").read_text())
        self.assertEqual(
            {"read", "clear_write", "ambiguous_write", "approved_loop", "false_done"},
            {row["id"] for row in scenarios},
        )
        self.assertEqual(0, next(row for row in scenarios if row["id"] == "read")["approvals"])
        self.assertEqual(
            0,
            next(row for row in scenarios if row["id"] == "approved_loop")[
                "additional_approvals"
            ],
        )

    def test_ci_uses_declared_cross_platform_matrix_without_third_party_toolchain_action(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("macos-latest", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn("rustup toolchain install 1.85.1", workflow)
        self.assertNotIn("dtolnay", workflow)
        self.assertIn("actions/checkout@v6", workflow)
        self.assertIn("actions/setup-python@v6", workflow)
        self.assertIn(".sha256", release)
        self.assertIn("Get-FileHash", release)
        self.assertIn("WriteAllText", release)
        self.assertNotIn("Out-File", release)


if __name__ == "__main__":
    unittest.main()
