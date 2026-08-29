from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTENT_SKILL = ROOT / "skills" / "clonamic-intent-guard"
TEAM_SKILL = ROOT / "skills" / "clonamic-team-control"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_team(contract, context):
    fallback = contract["capability_fallback"]
    benefit = context.get(contract["team_gate"], False)
    second_tier = contract["modes"]["lead_workers"]
    if (
        benefit
        and context.get(second_tier["necessity_signal"], False)
        and context.get("specialist_count", 0) >= second_tier["minimum_specialists"]
    ):
        intended_mode = "lead_workers"
    else:
        paired = contract["modes"]["paired"]
        intended_mode = "paired" if benefit and context.get(paired["need_signal"], False) else "native"

    if intended_mode == "native":
        return contract["default"]

    if context.get(fallback["signal"], True) is False:
        return {
            "intended_mode": intended_mode,
            "actual_team": fallback["actual_team"],
            "execution": fallback["execution"],
            "independent_review": fallback["independent_review"],
            "disclose_limitation": fallback["disclose_limitation"],
        }

    if intended_mode == "paired":
        collision = any(context.get(signal, False) for signal in paired["sequential_signals"])
        parallel_pairs = (
            not collision
            and context.get(paired["parallel_pairs"]["signal"], False)
            and context.get("worker_reviewer_pair_count", 1)
            >= paired["parallel_pairs"]["minimum_pairs"]
        )
        return {
            "intended_mode": "paired",
            "actual_team": True,
            "execution": "parallel_pairs" if parallel_pairs else "sequential",
            "independent_review": True,
            "disclose_limitation": False,
        }

    collision = context.get(second_tier["collision_signal"], False)
    return {
        "intended_mode": "lead_workers",
        "actual_team": True,
        "execution": "serialized_specialists" if collision else "parallel_specialists",
        "independent_review": True,
        "disclose_limitation": False,
    }


def evaluate_intent(contract, context):
    signals = set(context.get("signals", []))
    rejected = signals.intersection(contract["violation_checks"])
    return {
        "status": "reject" if rejected else "pass",
        "smallest_valid_scope": context.get("smallest_valid_scope", []),
    }


def evaluate_review(contract, context):
    if all(context.get(field, False) is True for field in contract["accept_requires"]):
        return {"status": "ACCEPT", "next": "complete"}

    rejection = context.get("reject", {})
    if any(not rejection.get(field) for field in contract["reject_required_fields"]):
        return {"status": "INVALID_REJECT", "next": "complete_reject_packet"}

    strategy_ids = context.get(contract["rework"]["strategy_id_field"], [])
    counted_ids = {
        strategy_id.strip()
        for strategy_id in strategy_ids
        if isinstance(strategy_id, str) and strategy_id.strip()
    }
    if len(counted_ids) >= contract["rework"]["max_strategies"]:
        return {"status": "BLOCKED", "next": "report_blocker"}
    return {"status": "REJECT", "next": "bounded_rework"}


def evaluate_decision(intent_contract, team_contract, review_contract, context):
    team = evaluate_team(team_contract, context)
    intent = evaluate_intent(
        intent_contract,
        {
            "signals": context.get("intent_signals", []),
            "smallest_valid_scope": context.get("smallest_valid_scope", []),
        },
    )
    review_context = context
    if team["intended_mode"] == "lead_workers" and not context.get("all_specialist_results", False):
        review_context = dict(context)
        review_context["all_required_results_present"] = False
    review = (
        evaluate_review(review_contract, review_context)
        if context.get("review_applicable", False)
        else None
    )
    return {
        "intended_mode": team["intended_mode"],
        "actual_team": team["actual_team"],
        "execution": team["execution"],
        "intent_verdict": intent["status"],
        "review_verdict": review["status"] if review else None,
    }


class TeamContractTest(unittest.TestCase):
    def test_canonical_instruction_source_and_two_skills_exist(self):
        source = (ROOT / "clonamic-herness-plugin.md").read_text(encoding="utf-8")
        self.assertIn("canonical instruction source", source.casefold())
        for skill in (INTENT_SKILL, TEAM_SKILL):
            with self.subTest(skill=skill.name):
                text = (skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("../../clonamic-herness-plugin.md", text)
                self.assertRegex(text, rf"(?m)^name: {skill.name}$")

    def test_intent_contract_separates_violations_from_output_scope(self):
        contract = load_json(INTENT_SKILL / "references" / "intent-contract.json")
        self.assertEqual(
            {
                "scope_drift",
                "adjacent_work",
                "duplicate_implementation",
                "speculative_abstraction",
                "reasoning_past_evidence",
            },
            set(contract["violation_checks"]),
        )
        self.assertNotIn("smallest_valid_scope", contract["violation_checks"])
        self.assertEqual(
            ["status", "reasons", "out_of_scope", "unnecessary_work", "smallest_valid_scope", "rework"],
            contract["output"]["fields"],
        )

    def test_team_contract_preserves_direct_worker_and_second_tier_boundaries(self):
        contract = load_json(TEAM_SKILL / "references" / "team-contract.json")
        self.assertEqual(
            {
                "intended_mode": "native",
                "actual_team": False,
                "execution": "direct",
                "independent_review": False,
                "disclose_limitation": False,
            },
            contract["default"],
        )
        self.assertEqual("prospective_before_execution", contract["selection_phase"])
        self.assertEqual("benefit_exceeds_coordination_cost", contract["team_gate"])
        self.assertEqual(
            {"worker_defect", "missing_evidence", "false_completion"},
            set(contract["non_signals"]),
        )
        self.assertEqual(["worker", "independent_reviewer"], contract["modes"]["paired"]["roles"])
        paired = contract["modes"]["paired"]
        self.assertEqual("sequential_after_delivered_result_and_fresh_evidence", paired["final_verdict"]["execution"])
        self.assertEqual(["delivered_result", "fresh_evidence"], paired["final_verdict"]["requires"])
        self.assertEqual("independent_pairs", paired["parallel_pairs"]["signal"])
        self.assertEqual(2, paired["parallel_pairs"]["minimum_pairs"])
        self.assertFalse(paired["shared_file_policy"]["concurrent_workers"])
        self.assertEqual("one_worker_then_reviewer", paired["shared_file_policy"]["execution"])
        self.assertEqual("single", contract["direct_worker"]["session"])
        self.assertFalse(contract["direct_worker"]["may_delegate"])
        lead = contract["modes"]["lead_workers"]["lead"]
        self.assertEqual({"assign", "review", "accept", "reject", "reassign"}, set(lead["actions"]))
        self.assertEqual({"execute", "integrate"}, set(lead["forbidden_actions"]))
        self.assertEqual("main_to_lead_to_specialists", contract["modes"]["lead_workers"]["topology"])
        self.assertEqual("one_assigned_specialist", contract["modes"]["lead_workers"]["integration_owner"])
        self.assertEqual("serialized_specialists", contract["modes"]["lead_workers"]["collision_execution"])
        self.assertEqual(
            ["all_specialist_results", "fresh_evidence"],
            contract["modes"]["lead_workers"]["final_verdict_requires"],
        )
        self.assertFalse(contract["executor_policy"]["auto_select_external"])

    def test_review_contract_requires_evidence_and_bounds_rework(self):
        contract = load_json(TEAM_SKILL / "references" / "review-contract.json")
        self.assertEqual(["ACCEPT", "REJECT"], contract["verdicts"])
        self.assertEqual(
            ["reasons", "evidence", "missing_requirements", "rework_scope", "reverification_conditions"],
            contract["reject_required_fields"],
        )
        self.assertEqual(
            ["all_required_results_present", "fresh_evidence", "intent_preserved"],
            contract["accept_requires"],
        )
        self.assertTrue(contract["reject_fields_must_be_nonempty"])
        self.assertEqual(3, contract["rework"]["max_strategies"])
        self.assertTrue(contract["rework"]["materially_different"])
        self.assertEqual("failed_strategy_ids", contract["rework"]["strategy_id_field"])
        self.assertEqual("distinct_identity", contract["rework"]["count_by"])
        self.assertEqual("trim", contract["rework"]["identity_normalization"])
        self.assertEqual("ignore", contract["rework"]["blank_identity_policy"])
        self.assertEqual("blocker", contract["rework"]["after_limit"])

    def test_capability_fallback_is_local_and_never_claims_a_team(self):
        contract = load_json(TEAM_SKILL / "references" / "team-contract.json")
        fallback = contract["capability_fallback"]
        self.assertEqual("native_subagents_available", fallback["signal"])
        self.assertEqual("preserve_prospective_selection", fallback["intended_mode"])
        self.assertFalse(fallback["actual_team"])
        self.assertEqual("local_sequential_second_pass", fallback["execution"])
        self.assertFalse(fallback["independent_review"])
        self.assertTrue(fallback["requires_team_gate"])
        self.assertTrue(fallback["disclose_limitation"])
        self.assertFalse(fallback["claim_team_created"])

    def test_decision_fixtures_use_one_stable_tuple(self):
        cases = load_json(ROOT / "tests" / "fixtures" / "team-ux-cases.json")
        expected_fields = {
            "intended_mode",
            "actual_team",
            "execution",
            "intent_verdict",
            "review_verdict",
        }
        decisions = [case for case in cases if case["domain"] == "decision"]
        self.assertGreaterEqual(len(decisions), 9)
        for case in decisions:
            with self.subTest(case=case["name"]):
                self.assertTrue(case["input"].get("request"))
                self.assertEqual(expected_fields, set(case["expected"]))

    def test_all_ux_cases_match_the_contracts(self):
        intent = load_json(INTENT_SKILL / "references" / "intent-contract.json")
        team = load_json(TEAM_SKILL / "references" / "team-contract.json")
        review = load_json(TEAM_SKILL / "references" / "review-contract.json")
        cases = load_json(ROOT / "tests" / "fixtures" / "team-ux-cases.json")
        self.assertGreaterEqual(len(cases), 12)
        evaluators = {
            "intent": lambda case: evaluate_intent(intent, case),
            "team": lambda case: evaluate_team(team, case),
            "review": lambda case: evaluate_review(review, case),
            "decision": lambda case: evaluate_decision(intent, team, review, case),
        }
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(case["expected"], evaluators[case["domain"]](case["input"]))

    def test_ux_fixtures_cover_the_required_failure_and_team_shapes(self):
        names = {case["name"] for case in load_json(ROOT / "tests" / "fixtures" / "team-ux-cases.json")}
        required_fragments = {
            "simple_read",
            "tightly_coupled",
            "independent_work",
            "three_specialists",
            "missing_completion",
            "scope_creep",
            "speculative_abstraction",
            "unavailable_subagents",
            "same_file_collision",
            "failed_strategy",
            "repeated_strategy",
            "missing_reject",
            "reviewer_before_result",
            "second_tier_lead",
            "native_false_completion",
            "unrequested_framework",
            "same_file_without_benefit",
            "two_specialists_no_lead",
            "adjacent_cleanup",
        }
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertTrue(any(fragment in name for name in names), fragment)


if __name__ == "__main__":
    unittest.main()
