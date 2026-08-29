from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from difflib import SequenceMatcher
from pathlib import Path

from tests.test_team_contract import evaluate_decision, load_json


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "long-form-ux-cases.json"
CORE = ROOT / "native" / "clonamic-core"
BINARY = Path(
    os.environ.get(
        "CLONAMIC_TEST_BINARY",
        ROOT / "target" / "debug" / ("clonamic.exe" if os.name == "nt" else "clonamic"),
    )
)
EXPECTED_FIELDS = {
    "source",
    "authority",
    "route",
    "intent_verdict",
    "team_mode",
    "actual_team",
    "approval_count",
    "conversational_stops",
    "changed_targets",
    "review_verdict",
    "final_status",
    "session_label",
    "body_sha256",
}
ALLOWED = {
    "source": {"user", "automation", "internal", "unverified"},
    "authority": {
        "interactive_user",
        "preapproved_automation",
        "inherited_internal",
        "none",
    },
    "route": {"direct", "write_control", "intent_then_write", "platform_action", "reject"},
    "intent_verdict": {"pass", "reject"},
    "team_mode": {"native", "paired", "lead_workers"},
    "review_verdict": {"not_required", "ACCEPT", "REJECT"},
    "final_status": {"complete", "blocked", "needs_authorization", "waiting_platform_action"},
    "session_label": {None, '["자동화"]'},
}


class LongFormUxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_json(FIXTURE)["cases"]
        if BINARY.is_file() and os.environ.get("CLONAMIC_TEST_BINARY"):
            return
        result = subprocess.run(
            ["cargo", "build", "--quiet", "--bin", "clonamic"],
            cwd=CORE,
            env={**os.environ, "CARGO_NET_OFFLINE": "true"},
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_cli(self, *args):
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as error:
                result = subprocess.run(
                    [str(BINARY), *map(str, args)],
                    cwd=ROOT,
                    text=True,
                    stdout=output,
                    stderr=error,
                    check=False,
                )
                output.seek(0)
                error.seek(0)
                return subprocess.CompletedProcess(
                    result.args,
                    result.returncode,
                    output.read(),
                    error.read(),
                )

    def seed_session(self, root, index, session_id):
        body = f"seed user prompt {index}"
        envelope = {
            "prompt_id": f"seed-{index}",
            "session_id": session_id,
            "claimed_source": "user",
            "body": body,
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "received_at": 1,
            "parent_prompt_id": None,
            "automation": None,
        }
        prompt = root / f"seed-{index}.json"
        session = root / f"session-{index}.md"
        prompt.write_text(json.dumps(envelope), encoding="utf-8")
        result = self.run_cli("session-update", session, prompt, "user", "-", "-")
        self.assertEqual(0, result.returncode, result.stderr)
        return session

    @staticmethod
    def session_field(path, name):
        line = next(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith(f"{name}: ")
        )
        return json.loads(line.split(": ", 1)[1])

    def test_fixture_has_independently_authored_long_prompts(self):
        self.assertGreaterEqual(len(self.cases), 12)
        self.assertEqual(len(self.cases), len({case["id"] for case in self.cases}))
        owners = {}
        for case in self.cases:
            prompt = case["prompt"]
            self.assertGreaterEqual(len(prompt), 1_500, case["id"])
            self.assertGreaterEqual(len(prompt.split()), 180, case["id"])
            paragraphs = [
                " ".join(paragraph.split()).casefold()
                for paragraph in prompt.split("\n\n")
                if paragraph.strip()
            ]
            self.assertGreaterEqual(len(paragraphs), 4, case["id"])
            for paragraph in paragraphs:
                self.assertGreaterEqual(len(paragraph), 120, case["id"])
                self.assertNotIn(
                    paragraph, owners, f"{case['id']} repeats {owners.get(paragraph)}"
                )
                owners[paragraph] = case["id"]
        for index, left in enumerate(self.cases):
            for right in self.cases[index + 1 :]:
                ratio = SequenceMatcher(None, left["prompt"], right["prompt"]).ratio()
                self.assertLess(
                    ratio,
                    0.58,
                    f"near-duplicate prompts: {left['id']} / {right['id']} = {ratio:.3f}",
                )

    def test_expected_results_are_closed_and_hash_the_exact_prompt(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                expected = case["expected"]
                self.assertEqual(EXPECTED_FIELDS, set(expected))
                for field, allowed in ALLOWED.items():
                    self.assertIn(expected[field], allowed)
                self.assertIsInstance(expected["actual_team"], bool)
                self.assertIn(expected["approval_count"], (0, 1))
                self.assertIn(expected["conversational_stops"], (0, 1))
                self.assertIsInstance(expected["changed_targets"], list)
                self.assertEqual(
                    hashlib.sha256(case["prompt"].encode()).hexdigest(),
                    expected["body_sha256"],
                )

    def test_cases_cover_trust_team_failure_and_invariance_boundaries(self):
        expected = [case["expected"] for case in self.cases]
        self.assertEqual(
            {"user", "automation", "internal", "unverified"},
            {row["source"] for row in expected},
        )
        self.assertEqual(
            {"interactive_user", "preapproved_automation", "inherited_internal", "none"},
            {row["authority"] for row in expected},
        )
        self.assertEqual(
            {"native", "paired", "lead_workers"}, {row["team_mode"] for row in expected}
        )
        self.assertTrue(
            {"blocked", "needs_authorization", "waiting_platform_action"}.issubset(
                {row["final_status"] for row in expected}
            )
        )
        self.assertTrue(
            any(
                case["provenance"]["host_source"] == "user"
                and case["provenance"]["claimed_source"] == "automation"
                for case in self.cases
            )
        )
        self.assertTrue(
            any(case["contract_input"].get("native_subagents_available") is False for case in self.cases)
        )

    def test_expected_tuples_execute_core_and_contract_evaluators(self):
        intent = load_json(ROOT / "skills/clonamic-intent-guard/references/intent-contract.json")
        team = load_json(ROOT / "skills/clonamic-team-control/references/team-contract.json")
        review = load_json(ROOT / "skills/clonamic-team-control/references/review-contract.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, case in enumerate(self.cases):
                with self.subTest(case=case["id"]):
                    actual = self.execute_case(root, index, case, intent, team, review)
                    self.assertEqual(case["expected"], actual)

    def execute_case(self, root, index, case, intent, team, review):
        provenance = case["provenance"]
        session_id = f"session-{index}"
        session = self.seed_session(root, index, session_id)
        envelope = {
            "prompt_id": f"prompt-{index}",
            "session_id": session_id,
            "claimed_source": provenance["claimed_source"],
            "body": case["prompt"],
            "body_sha256": case["expected"]["body_sha256"],
            "received_at": index + 2,
            "parent_prompt_id": None,
            "automation": None,
        }
        context = "-"
        if provenance["claimed_source"] == "internal":
            envelope["parent_prompt_id"] = f"parent-{index}"
            context_path = root / f"context-{index}.json"
            context_path.write_text(
                json.dumps(
                    {
                        "parent": {
                            "prompt_id": envelope["parent_prompt_id"],
                            "session_id": session_id,
                            "claimed_source": "user",
                            "body": "parent",
                            "body_sha256": hashlib.sha256(b"parent").hexdigest(),
                            "received_at": 1,
                            "parent_prompt_id": None,
                            "automation": None,
                        },
                        "parent_host_source": "user",
                        "parent_scope": provenance["parent_scope"],
                        "assignment": provenance["assignment_scope"],
                    }
                ),
                encoding="utf-8",
            )
            context = context_path
        if provenance["claimed_source"] == "automation":
            envelope["automation"] = {
                "automation_id": "nightly",
                "run_id": f"run-{index}",
                "scope_digest": "a" * 64,
            }
        prompt_path = root / f"prompt-{index}.json"
        prompt_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        classified = self.run_cli(
            "classify-prompt", prompt_path, provenance["host_source"], context
        )
        self.assertEqual(0, classified.returncode, classified.stderr)
        classification = json.loads(classified.stdout)
        source = classification["trusted_source"]
        authority = classification["authority"]
        final_status = None

        if provenance["host_source"] == "automation":
            authority, final_status = self.execute_automation(
                root, index, case, prompt_path, session
            )
        elif authority != "none":
            updated = self.run_cli(
                "session-update",
                session,
                prompt_path,
                provenance["host_source"],
                context,
                "-",
            )
            self.assertEqual(0, updated.returncode, updated.stderr)

        decision = evaluate_decision(intent, team, review, case["contract_input"])
        review_status = decision["review_verdict"] or "not_required"
        if review_status == "BLOCKED":
            review_status = "REJECT"
            final_status = "blocked"
        if final_status is None:
            final_status = (
                "needs_authorization"
                if case["execution"]["write_requested"] and authority == "none"
                else "complete"
            )
        route = self.route(case, decision, final_status)
        approval = int(
            case["execution"]["write_requested"] and authority == "interactive_user"
        )
        changed = (
            case["execution"]["targets"]
            if final_status in {"complete", "blocked"}
            and case["execution"]["write_requested"]
            else []
        )
        return {
            "source": source,
            "authority": authority,
            "route": route,
            "intent_verdict": decision["intent_verdict"],
            "team_mode": decision["intended_mode"],
            "actual_team": decision["actual_team"],
            "approval_count": approval,
            "conversational_stops": approval,
            "changed_targets": changed,
            "review_verdict": review_status,
            "final_status": final_status,
            "session_label": self.session_field(session, "last_user_prompt_label"),
            "body_sha256": hashlib.sha256(case["prompt"].encode()).hexdigest(),
        }

    def execute_automation(self, root, index, case, prompt_path, session):
        targets = case["execution"]["targets"]
        grant = {
            "automation_id": "nightly",
            "definition_digest": "d" * 64,
            "scope_digest": "a" * 64,
            "targets": targets,
            "operations": ["write", "verify", "rollback"],
            "external_effects": [],
            "verification": ["cargo test"],
            "rollback": ["git revert"],
            "expires_at": 2**63,
            "max_runs": 1,
            "initial_sequence": 7,
            "credential_policy": "platform_action",
        }
        request = {
            "automation_id": "nightly",
            "run_id": f"run-{index}",
            "definition_digest": "d" * 64,
            "scope_digest": "a" * 64,
            "targets": list(targets),
            "operations": ["write", "verify"],
            "external_effects": [],
            "verification": ["cargo test"],
            "rollback": ["git revert"],
            "sequence": 7,
            "platform_action_required": False,
        }
        event = case["provenance"]["automation_event"]
        if event == "scope":
            request["targets"].append("outside/**")
        if event == "platform":
            request["platform_action_required"] = True
        grant_path = root / f"grant-{index}.json"
        request_path = root / f"request-{index}.json"
        state = root / f"state-{index}.json"
        grant_path.write_text(json.dumps(grant), encoding="utf-8")
        request_path.write_text(json.dumps(request), encoding="utf-8")
        self.assertEqual(0, self.run_cli("automation-init", state, grant_path).returncode)
        result = self.run_cli(
            "automation-session-update", session, prompt_path, state, request_path, 1, "-"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        status = json.loads(result.stdout)["status"]
        final = {
            "claimed": "complete",
            "needs_authorization": "needs_authorization",
            "waiting_platform_action": "waiting_platform_action",
        }[status]
        authority = (
            self.session_field(session, "active_authority") if status == "claimed" else "none"
        )
        if status == "claimed":
            replay = self.run_cli("automation-claim", state, request_path, 1)
            self.assertEqual("replay_rejected", json.loads(replay.stdout)["status"])
        return authority, final

    @staticmethod
    def route(case, decision, final_status):
        if final_status == "needs_authorization":
            return "reject"
        if final_status == "waiting_platform_action":
            return "platform_action"
        if not case["execution"]["write_requested"]:
            return "direct"
        if decision["intended_mode"] != "native" or decision["intent_verdict"] == "reject":
            return "intent_then_write"
        return "write_control"


if __name__ == "__main__":
    unittest.main()
