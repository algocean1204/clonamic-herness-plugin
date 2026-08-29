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


if __name__ == "__main__":
    unittest.main()
