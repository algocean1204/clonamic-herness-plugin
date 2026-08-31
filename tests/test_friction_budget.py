from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrictionBudgetTest(unittest.TestCase):
    def test_contract_caps_approvals_and_keeps_non_user_work_noninteractive(self):
        contract = json.loads(
            (
                ROOT
                / "skills/clonamic-write-control/references/friction-contract.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {
                "read_only": 0,
                "clear_write": 1,
                "materially_ambiguous_write": 2,
                "approved_loop_additional": 0,
                "automation_additional": 0,
                "internal_additional": 0,
            },
            contract["approval_budget"],
        )
        self.assertFalse(contract["platform_action"]["consume_run"])
        self.assertEqual(0, contract["platform_action"]["conversational_approval"])
        self.assertFalse(contract["scope_change"]["interactive"])
        self.assertEqual(
            {
                "authority": "development_specification_boundary",
                "internal_commands": "implementation_detail",
                "same_scope_retry": "idempotent",
                "additional_cmd_or_terminal_prompt": "forbidden",
                "guard_protects": [
                    "outside_boundary",
                    "catastrophic",
                    "credential",
                    "platform_action",
                ],
            },
            contract["approved_run"],
        )

    def test_public_contract_never_regates_internal_commands_in_an_active_run(self):
        guidance = (ROOT / "clonamic-herness-plugin.md").read_text(encoding="utf-8")
        write_skill = (ROOT / "skills/clonamic-write-control/SKILL.md").read_text(
            encoding="utf-8"
        )
        contract = "\n".join((guidance, write_skill))
        for phrase in (
            "Internal commands and same-scope retries add no gate",
            "never asks for a CMD code",
            "idempotently after a timeout or pre-execution failure",
            "boundary escapes, catastrophic effects, credentials, and platform actions",
        ):
            self.assertIn(phrase, contract)

    def test_long_form_cases_have_no_avoidable_non_user_stops(self):
        cases = json.loads(
            (ROOT / "tests/fixtures/long-form-ux-cases.json").read_text(
                encoding="utf-8"
            )
        )["cases"]
        for case in cases:
            expected = case["expected"]
            with self.subTest(case=case["id"]):
                if expected["source"] != "user":
                    self.assertEqual(0, expected["conversational_stops"])
                if expected["route"] == "direct":
                    self.assertEqual(0, expected["approval_count"])
                self.assertLessEqual(expected["approval_count"], 2)

    def test_fixture_counts_are_not_presented_as_observed_events(self):
        source = (ROOT / "tests/test_long_form_ux.py").read_text(encoding="utf-8")
        self.assertIn("Deterministic contract coverage", source)
        self.assertIn("observed event logs", source)
        self.assertNotIn("test_expected_tuples_execute", source)


if __name__ == "__main__":
    unittest.main()
