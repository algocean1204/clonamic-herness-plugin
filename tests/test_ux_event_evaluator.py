from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate-ux-events.py"
SPEC = importlib.util.spec_from_file_location("evaluate_ux_events", SCRIPT)
EVALUATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EVALUATOR)


def events(*rows, run_id="run-a"):
    normalized = []
    packet_codes = {}
    last_specification_kind = None
    last_authorization = None
    for index, (event_type, original) in enumerate(rows, 1):
        data = dict(original)
        if event_type == "request_received":
            data.setdefault("capture_kind", "observed")
            data.setdefault("host", "test-host")
        elif event_type == "assistant_message" and data.get("kind") in {
            "work_specification",
            "development_specification",
        }:
            last_specification_kind = data["kind"]
        elif event_type == "approval_wait":
            data.setdefault("specification_kind", last_specification_kind or "development_specification")
            packet_codes[data["packet_id"]] = data["code"]
        elif event_type == "approval_result":
            data.setdefault("code", packet_codes.get(data["packet_id"], "UNKNOWN"))
            if data.get("status") in {"activated", "already_active"}:
                last_authorization = "packet:{}:{}".format(data["packet_id"], data["code"].upper())
        elif event_type == "automation_decision" and data.get("status") == "claimed" and data.get("write_authorized"):
            last_authorization = "automation:{}".format(data["run_id"])
        elif event_type == "write":
            data.setdefault("authorization_id", last_authorization or "missing")
        elif event_type == "verification":
            data.setdefault("required", True)
            data.setdefault("evidence", "")
        elif event_type == "rollback":
            data.setdefault("required", True)
            data.setdefault("evidence", "")
        normalized.append({
            "schema_version": 1,
            "run_id": run_id,
            "seq": index,
            "type": event_type,
            "data": data,
        })
    return normalized


class UxEventEvaluatorTest(unittest.TestCase):
    def test_agent_evaluation_contract_requires_goals_feedback_and_bounded_rework(self):
        contract = json.loads(
            (
                ROOT
                / "skills/clonamic-team-control/references/evaluation-contract.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(20, contract["blind_prompt_minimum"])
        self.assertEqual(
            {
                "objective",
                "baseline",
                "target",
                "guardrails",
                "scenario_coverage",
                "measurement_method",
            },
            set(contract["goal_fields"]),
        )
        self.assertTrue(
            {"verdict", "evidence", "user_impact", "feedback", "next_experiment"}
            .issubset(contract["evaluator_output_fields"])
        )
        self.assertEqual(3, contract["rework"]["max_strategies"])
        self.assertTrue(contract["rework"]["same_evaluator"])

    def test_evaluation_contract_requires_observed_events_and_blind_prompts(self):
        contract = json.loads(
            (
                ROOT
                / "skills/clonamic-team-control/references/evaluation-contract.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(1, contract["schema_version"])
        self.assertEqual("observed_host_events", contract["measurement_source"])
        self.assertFalse(contract["fixture_metadata_proves_model_behavior"])
        self.assertEqual(20, contract["blind_prompt_minimum"])
        self.assertEqual(
            {"question", "explanation", "inspection", "review", "status", "recommendation"},
            set(contract["read_only_classes"]),
        )
        self.assertEqual(
            {"read_only": 0, "clear_write": 1, "ambiguous_write": 2, "approved_loop_additional": 0, "automation": 0},
            contract["approval_budget"],
        )
        self.assertEqual("reuse_existing_code", contract["multiple_pending_policy"])

    def test_read_and_write_metamorphic_pair_is_graded_from_events(self):
        read = events(
            ("request_received", {"source": "user", "prompt_sha256": "a" * 64}),
            ("assistant_message", {"kind": "answer"}),
            ("final", {"status": "complete"}),
        )
        write = events(
            ("request_received", {"source": "user", "prompt_sha256": "b" * 64}),
            ("assistant_message", {"kind": "development_specification"}),
            ("approval_wait", {"packet_id": "packet-a", "code": "ABC123"}),
            ("approval_result", {"packet_id": "packet-a", "status": "activated"}),
            ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
            ("write", {"target": "src/value.py"}),
            ("verification", {"id": "target-test", "status": "passed", "evidence": "1 passed"}),
            ("verdict", {"status": "complete", "evidence": "1 passed"}),
            ("assistant_message", {"kind": "completion_report"}),
            ("final", {"status": "complete"}),
        )

        read_summary = EVALUATOR.summarize(read)
        write_summary = EVALUATOR.summarize(write)
        self.assertEqual([], read_summary["violations"])
        self.assertEqual([], write_summary["violations"])

        self.assertEqual((0, 0, []), (
            read_summary["specification_count"],
            read_summary["approval_count"],
            read_summary["changed_targets"],
        ))
        self.assertEqual((1, 1, ["src/value.py"]), (
            write_summary["specification_count"],
            write_summary["approval_count"],
            write_summary["changed_targets"],
        ))

    def test_six_read_only_classes_have_zero_friction(self):
        for request_class in (
            "question",
            "explanation",
            "inspection",
            "review",
            "status",
            "recommendation",
        ):
            with self.subTest(request_class=request_class):
                summary = EVALUATOR.summarize(
                    events(
                        ("request_received", {"source": "user", "prompt_sha256": "c" * 64}),
                        ("assistant_message", {"kind": "answer"}),
                        ("final", {"status": "complete"}),
                    )
                )
                verdict = EVALUATOR.grade(
                    summary,
                    {
                        "request_class": request_class,
                        "approval_budget": 0,
                        "stop_budget": 0,
                        "specification_budget": 0,
                        "report_budget": 0,
                        "allowed_targets": [],
                        "expected_final_status": "complete",
                    },
                )
                self.assertTrue(verdict["passed"], verdict)

    def test_approval_budgets_are_zero_one_and_two_without_loop_regates(self):
        clear = events(
            ("request_received", {"source": "user", "prompt_sha256": "d" * 64}),
            ("assistant_message", {"kind": "development_specification"}),
            ("approval_wait", {"packet_id": "d", "code": "AAAAAA"}),
            ("approval_result", {"packet_id": "d", "status": "activated"}),
            ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
            ("write", {"target": "src/clear.py"}),
            ("verification", {"id": "first", "status": "failed", "evidence": "failed"}),
            ("strategy_failed", {"strategy_id": "first-patch"}),
            ("write", {"target": "src/clear.py"}),
            ("verification", {"id": "first", "status": "passed", "evidence": "passed"}),
            ("verdict", {"status": "complete", "evidence": "passed"}),
            ("assistant_message", {"kind": "completion_report"}),
            ("final", {"status": "complete"}),
        )
        ambiguous = events(
            ("request_received", {"source": "user", "prompt_sha256": "e" * 64}),
            ("assistant_message", {"kind": "work_specification"}),
            ("approval_wait", {"packet_id": "w", "code": "BBBBBB"}),
            ("approval_result", {"packet_id": "w", "status": "activated"}),
            ("assistant_message", {"kind": "development_specification"}),
            ("approval_wait", {"packet_id": "d", "code": "CCCCCC"}),
            ("approval_result", {"packet_id": "d", "status": "activated"}),
            ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
            ("write", {"target": "src/ambiguous.py"}),
            ("verification", {"id": "check", "status": "passed", "evidence": "passed"}),
            ("verdict", {"status": "complete", "evidence": "passed"}),
            ("assistant_message", {"kind": "completion_report"}),
            ("final", {"status": "complete"}),
        )
        automation = events(
            ("request_received", {"source": "automation", "prompt_sha256": "f" * 64}),
            ("automation_decision", {"status": "claimed", "interactive": False, "write_authorized": True, "run_id": "nightly-1"}),
            ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
            ("write", {"target": "reports/nightly.json"}),
            ("verification", {"id": "schema", "status": "passed", "evidence": "valid"}),
            ("verdict", {"status": "complete", "evidence": "valid"}),
            ("assistant_message", {"kind": "completion_report"}),
            ("final", {"status": "complete"}),
        )

        summaries = [EVALUATOR.summarize(value) for value in (clear, ambiguous, automation)]
        self.assertEqual([[], [], []], [summary["violations"] for summary in summaries])
        self.assertEqual([1, 2, 0], [summary["approval_count"] for summary in summaries])
        self.assertEqual(1, summaries[0]["conversational_stops"])

    def test_automation_retry_does_not_add_a_conversational_stop(self):
        summary = EVALUATOR.summarize(
            events(
                ("request_received", {"source": "automation", "prompt_sha256": "1" * 64}),
                ("automation_decision", {"status": "waiting_platform_action", "interactive": False, "write_authorized": False, "run_id": "run-1"}),
                ("automation_decision", {"status": "needs_authorization", "interactive": False, "write_authorized": False, "run_id": "run-1"}),
                ("automation_decision", {"status": "claimed", "interactive": False, "write_authorized": True, "run_id": "run-1"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("write", {"target": "reports/a.json"}),
                ("verification", {"id": "schema", "status": "passed", "evidence": "valid"}),
                ("verdict", {"status": "complete", "evidence": "valid"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("final", {"status": "complete"}),
            )
        )
        self.assertEqual([], summary["violations"])
        self.assertEqual(0, summary["conversational_stops"])
        self.assertEqual(
            ["waiting_platform_action", "needs_authorization", "claimed"],
            [row["status"] for row in summary["automation_decisions"]],
        )

    def test_team_fallback_requires_truthful_disclosure(self):
        without_disclosure = events(
            ("request_received", {"source": "user", "prompt_sha256": "2" * 64}),
            ("team_selected", {"intended_mode": "paired", "actual_team": False, "execution": "local_sequential_second_pass"}),
            ("verdict", {"status": "complete", "evidence": "local second pass"}),
            ("assistant_message", {"kind": "completion_report"}),
            ("final", {"status": "complete"}),
        )
        with_disclosure = without_disclosure[:-3] + [
            {
                "schema_version": 1,
                "run_id": "run-a",
                "seq": 3,
                "type": "assistant_message",
                "data": {"kind": "team_disclosure"},
            },
            {
                "schema_version": 1,
                "run_id": "run-a",
                "seq": 4,
                "type": "verdict",
                "data": {"status": "complete", "evidence": "local second pass"},
            },
            {
                "schema_version": 1,
                "run_id": "run-a",
                "seq": 5,
                "type": "assistant_message",
                "data": {"kind": "completion_report"},
            },
            {
                "schema_version": 1,
                "run_id": "run-a",
                "seq": 6,
                "type": "final",
                "data": {"status": "complete"},
            },
        ]
        self.assertIn("missing_team_fallback_disclosure", EVALUATOR.summarize(without_disclosure)["violations"])
        self.assertEqual([], EVALUATOR.summarize(with_disclosure)["violations"])

    def test_blocker_counts_distinct_nonblank_strategy_ids(self):
        summary = EVALUATOR.summarize(
            events(
                ("request_received", {"source": "user", "prompt_sha256": "3" * 64}),
                ("strategy_failed", {"strategy_id": "same"}),
                ("strategy_failed", {"strategy_id": " same "}),
                ("strategy_failed", {"strategy_id": ""}),
                ("strategy_failed", {"strategy_id": "second"}),
                ("strategy_failed", {"strategy_id": "third"}),
                ("rollback", {"id": "working-tree", "status": "passed", "evidence": "restored"}),
                ("verdict", {"status": "blocked", "evidence": "three strategies failed"}),
                ("assistant_message", {"kind": "blocker_report"}),
                ("final", {"status": "blocked"}),
            )
        )
        self.assertEqual(["same", "second", "third"], summary["failed_strategy_ids"])
        self.assertEqual(1, summary["rollback_passed"])
        self.assertEqual([], summary["violations"])

    def test_multiple_pending_must_reuse_an_existing_code(self):
        good = events(
            ("request_received", {"source": "user", "prompt_sha256": "4" * 64}),
            ("assistant_message", {"kind": "work_specification"}),
            ("approval_wait", {"packet_id": "first", "code": "ABC123"}),
            ("assistant_message", {"kind": "development_specification"}),
            ("approval_wait", {"packet_id": "second", "code": "DEF456"}),
            ("approval_result", {"packet_id": "first", "status": "multiple_pending"}),
            ("approval_result", {"packet_id": "first", "status": "activated", "code": "ABC123"}),
            ("final", {"status": "complete"}),
        )
        bad = good[:-1] + [
            {
                "schema_version": 1,
                "run_id": "run-a",
                "seq": 8,
                "type": "approval_wait",
                "data": {"packet_id": "replacement", "code": "AAAAAA", "specification_kind": "development_specification"},
            },
            {
                "schema_version": 1,
                "run_id": "run-a",
                "seq": 9,
                "type": "final",
                "data": {"status": "complete"},
            },
        ]
        self.assertEqual([], EVALUATOR.summarize(good)["violations"])
        self.assertIn("approval_code_reissued_after_multiple_pending", EVALUATOR.summarize(bad)["violations"])

    def test_duplicate_specifications_and_reports_are_rejected(self):
        summary = EVALUATOR.summarize(
            events(
                ("request_received", {"source": "user", "prompt_sha256": "5" * 64}),
                ("assistant_message", {"kind": "development_specification"}),
                ("assistant_message", {"kind": "development_specification"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("final", {"status": "complete"}),
            )
        )
        self.assertIn("duplicate_development_specification", summary["violations"])
        self.assertIn("duplicate_final_report", summary["violations"])

    def test_cli_outputs_normalized_json(self):
        rows = events(
            ("request_received", {"source": "user", "prompt_sha256": "6" * 64}),
            ("assistant_message", {"kind": "answer"}),
            ("final", {"status": "complete"}),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("complete", json.loads(result.stdout)["final_status"])


class UxCausalTraceRejectionTest(unittest.TestCase):
    def assert_violation(self, rows, name):
        self.assertIn(name, EVALUATOR.summarize(events(*rows))["violations"])

    def test_request_must_be_first(self):
        self.assert_violation(
            [
                ("assistant_message", {"kind": "answer"}),
                ("request_received", {"source": "user", "prompt_sha256": "7" * 64}),
                ("final", {"status": "complete"}),
            ],
            "request_not_first",
        )

    def test_final_must_be_last_and_forbid_later_events(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "8" * 64}),
                ("final", {"status": "complete"}),
                ("assistant_message", {"kind": "answer"}),
            ],
            "event_after_final",
        )

    def test_event_data_schema_is_closed(self):
        with self.assertRaises(EVALUATOR.EventError):
            EVALUATOR.summarize(
                events(
                    ("request_received", {"source": "user", "prompt_sha256": "9" * 64, "unexpected": True}),
                    ("final", {"status": "complete"}),
                )
            )

    def test_expectation_schema_is_closed(self):
        summary = EVALUATOR.summarize(
            events(
                ("request_received", {"source": "user", "prompt_sha256": "a" * 64}),
                ("final", {"status": "complete"}),
            )
        )
        with self.assertRaises(EVALUATOR.EventError):
            EVALUATOR.grade(summary, {"unexpected": True})

    def test_approval_result_must_match_packet_and_code(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "b" * 64}),
                ("assistant_message", {"kind": "development_specification"}),
                ("approval_wait", {"packet_id": "d", "code": "ABC123"}),
                ("approval_result", {"packet_id": "d", "code": "DEF456", "status": "activated"}),
                ("final", {"status": "needs_authorization"}),
            ],
            "approval_result_packet_code_mismatch",
        )

    def test_write_requires_prior_bound_authorization(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "c" * 64}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("write", {"target": "src/a.py", "authorization_id": "packet:d:ABC123"}),
                ("verification", {"id": "test", "status": "passed", "required": True, "evidence": "passed"}),
                ("verdict", {"status": "complete", "evidence": "passed"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("final", {"status": "complete"}),
            ],
            "write_before_authorization",
        )

    def test_verification_must_follow_latest_write(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "d" * 64}),
                ("assistant_message", {"kind": "development_specification"}),
                ("approval_wait", {"packet_id": "d", "code": "ABC123"}),
                ("approval_result", {"packet_id": "d", "code": "ABC123", "status": "activated"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("verification", {"id": "test", "status": "passed", "required": True, "evidence": "stale"}),
                ("write", {"target": "src/a.py", "authorization_id": "packet:d:ABC123"}),
                ("verdict", {"status": "complete", "evidence": "stale"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("final", {"status": "complete"}),
            ],
            "fresh_required_verification_missing",
        )

    def test_report_must_follow_verdict(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "e" * 64}),
                ("assistant_message", {"kind": "completion_report"}),
                ("verdict", {"status": "complete", "evidence": "done"}),
                ("final", {"status": "complete"}),
            ],
            "report_before_verdict",
        )

    def test_changed_complete_run_requires_exactly_one_report(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "f" * 64}),
                ("assistant_message", {"kind": "development_specification"}),
                ("approval_wait", {"packet_id": "d", "code": "ABC123"}),
                ("approval_result", {"packet_id": "d", "code": "ABC123", "status": "activated"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("write", {"target": "src/a.py", "authorization_id": "packet:d:ABC123"}),
                ("verification", {"id": "test", "status": "passed", "required": True, "evidence": "passed"}),
                ("verdict", {"status": "complete", "evidence": "passed"}),
                ("final", {"status": "complete"}),
            ],
            "changed_run_report_count_not_one",
        )

    def test_latest_failed_or_unrun_required_check_rejects_completion(self):
        for status in ("failed", "unrun"):
            with self.subTest(status=status):
                self.assert_violation(
                    [
                        ("request_received", {"source": "user", "prompt_sha256": "1" * 64}),
                        ("assistant_message", {"kind": "development_specification"}),
                        ("approval_wait", {"packet_id": "d", "code": "ABC123"}),
                        ("approval_result", {"packet_id": "d", "code": "ABC123", "status": "activated"}),
                        ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                        ("write", {"target": "src/a.py", "authorization_id": "packet:d:ABC123"}),
                        ("verification", {"id": "test", "status": status, "required": True, "evidence": "not passed"}),
                        ("verdict", {"status": "complete", "evidence": "not passed"}),
                        ("assistant_message", {"kind": "completion_report"}),
                        ("final", {"status": "complete"}),
                    ],
                    "required_verification_not_passed",
                )

    def test_team_topology_must_be_single_and_valid(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "2" * 64}),
                ("team_selected", {"intended_mode": "paired", "actual_team": True, "execution": "parallel_specialists"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("final", {"status": "complete"}),
            ],
            "team_selection_count_not_one",
        )

    def test_changed_run_selects_team_before_first_write(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "7" * 64}),
                ("assistant_message", {"kind": "development_specification"}),
                ("approval_wait", {"packet_id": "development", "code": "ABC123"}),
                ("approval_result", {"packet_id": "development", "code": "ABC123", "status": "activated"}),
                ("write", {"target": "src/a.py", "authorization_id": "packet:development:ABC123"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("verification", {"id": "test", "status": "passed", "required": True, "evidence": "passed"}),
                ("verdict", {"status": "complete", "evidence": "passed"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("final", {"status": "complete"}),
            ],
            "team_selected_after_first_write",
        )

    def test_final_status_must_match_verdict(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "3" * 64}),
                ("verdict", {"status": "blocked", "evidence": "blocked"}),
                ("assistant_message", {"kind": "blocker_report"}),
                ("final", {"status": "complete"}),
            ],
            "final_status_mismatches_verdict",
        )

    def test_work_specification_approval_never_authorizes_user_write(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "4" * 64}),
                ("assistant_message", {"kind": "work_specification"}),
                ("approval_wait", {"packet_id": "work", "code": "ABC123"}),
                ("approval_result", {"packet_id": "work", "code": "ABC123", "status": "activated"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("write", {"target": "src/a.py", "authorization_id": "packet:work:ABC123"}),
                ("verification", {"id": "test", "status": "passed", "required": True, "evidence": "passed"}),
                ("verdict", {"status": "complete", "evidence": "passed"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("final", {"status": "complete"}),
            ],
            "write_without_development_approval",
        )

    def test_verdict_must_follow_latest_required_verification(self):
        self.assert_violation(
            [
                ("request_received", {"source": "user", "prompt_sha256": "5" * 64}),
                ("assistant_message", {"kind": "development_specification"}),
                ("approval_wait", {"packet_id": "development", "code": "ABC123"}),
                ("approval_result", {"packet_id": "development", "code": "ABC123", "status": "activated"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("write", {"target": "src/a.py", "authorization_id": "packet:development:ABC123"}),
                ("verdict", {"status": "complete", "evidence": "too early"}),
                ("verification", {"id": "test", "status": "passed", "required": True, "evidence": "passed"}),
                ("assistant_message", {"kind": "completion_report"}),
                ("final", {"status": "complete"}),
            ],
            "verdict_before_required_verification",
        )

    def test_changed_blocked_run_accepts_failed_check_after_verified_recovery(self):
        summary = EVALUATOR.summarize(
            events(
                ("request_received", {"source": "user", "prompt_sha256": "6" * 64}),
                ("assistant_message", {"kind": "development_specification"}),
                ("approval_wait", {"packet_id": "development", "code": "ABC123"}),
                ("approval_result", {"packet_id": "development", "code": "ABC123", "status": "activated"}),
                ("team_selected", {"intended_mode": "native", "actual_team": False, "execution": "direct"}),
                ("write", {"target": "src/a.py", "authorization_id": "packet:development:ABC123"}),
                ("verification", {"id": "required-test", "status": "failed", "required": True, "evidence": "still fails"}),
                ("rollback", {"id": "working-tree", "status": "passed", "required": True, "evidence": "preimage restored"}),
                ("verdict", {"status": "blocked", "evidence": "required test failed; rollback verified"}),
                ("assistant_message", {"kind": "blocker_report"}),
                ("final", {"status": "blocked"}),
            )
        )
        self.assertEqual([], summary["violations"])


if __name__ == "__main__":
    unittest.main()
