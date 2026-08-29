from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "native" / "clonamic-core"
BINARY = ROOT / "target" / "debug" / ("clonamic.exe" if os.name == "nt" else "clonamic")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class PromptContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
        return subprocess.run(
            [str(BINARY), *map(str, args)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_references_are_closed_and_define_noninteractive_automation(self):
        prompt = load_json(ROOT / "skills/clonamic-router/references/prompt-envelope.json")
        automation = load_json(
            ROOT / "skills/clonamic-write-control/references/automation-contract.json"
        )
        session = load_json(
            ROOT / "skills/clonamic-intent-guard/references/session-contract.json"
        )
        self.assertFalse(prompt["additionalProperties"])
        self.assertEqual(["user", "automation", "internal"], prompt["properties"]["claimed_source"]["enum"])
        self.assertEqual("display_only", prompt["automation_marker_policy"])
        self.assertEqual("candidate_only", prompt["automation_classification"])
        self.assertEqual(
            ["prompt_id", "session_id", "authority", "scope"],
            prompt["scope_authority_fields"],
        )
        self.assertFalse(automation["decisions"]["interactive"])
        self.assertIn("verification", automation["run_fields"])
        self.assertIn("rollback", automation["run_fields"])
        self.assertEqual("refuse_changed_grant", automation["initialization_policy"])
        self.assertEqual("successful_claim_result", automation["authority_token"])
        self.assertEqual("needs_authorization", automation["scope_failure_status"])
        self.assertEqual("waiting_platform_action", automation["credential_status"])
        self.assertEqual(2500, session["maximum_file_bytes"])
        self.assertEqual(2048, session["maximum_excerpt_bytes"])
        self.assertEqual("owned_lock", session["read_modify_write"])
        self.assertEqual("reject", session["session_id_mismatch"])
        self.assertEqual("received_at", session["newest_external_order"])

    def test_prompt_ux_cases_cover_the_trust_boundary(self):
        cases = load_json(ROOT / "tests/fixtures/prompt-ux-cases.json")
        self.assertGreaterEqual(len(cases), 12)
        names = {case["name"] for case in cases}
        required = {
            "trusted_user",
            "trusted_automation",
            "forged_marker",
            "source_mismatch",
            "internal_intersection",
            "internal_escalation",
            "internal_parent_id_mismatch",
            "internal_session_mismatch",
            "digest_mismatch",
            "unknown_field",
            "automation_replay",
            "automation_scope",
            "automation_credentials",
            "internal_session_preservation",
        }
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertTrue(any(fragment in name for name in names), fragment)

    def test_fixture_digests_match_exact_utf8_bodies(self):
        cases = load_json(ROOT / "tests/fixtures/prompt-ux-cases.json")
        for case in cases:
            envelope = case.get("envelope")
            if not envelope or case.get("digest_intentionally_invalid"):
                continue
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    hashlib.sha256(envelope["body"].encode()).hexdigest(),
                    envelope["body_sha256"],
                )

    def test_skill_entrypoints_route_to_the_new_contracts(self):
        expected = {
            "skills/clonamic-router/SKILL.md": "prompt-envelope.json",
            "skills/clonamic-write-control/SKILL.md": "automation-contract.json",
            "skills/clonamic-intent-guard/SKILL.md": "session-contract.json",
        }
        for relative, reference in expected.items():
            with self.subTest(skill=relative):
                self.assertIn(reference, (ROOT / relative).read_text(encoding="utf-8"))

    def test_prompt_envelopes_execute_the_core_classifier(self):
        cases = load_json(ROOT / "tests/fixtures/prompt-ux-cases.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, case in enumerate(cases):
                envelope = case.get("envelope")
                if not envelope:
                    continue
                prompt = root / f"prompt-{index}.json"
                prompt.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
                context = "-"
                if envelope["claimed_source"] == "internal":
                    context_path = root / f"context-{index}.json"
                    context_path.write_text(
                        json.dumps(
                            {
                                "parent": {
                                    "prompt_id": case.get(
                                        "context_parent_prompt_id",
                                        envelope["parent_prompt_id"],
                                    ),
                                    "session_id": case.get(
                                        "context_parent_session_id",
                                        envelope["session_id"],
                                    ),
                                    "claimed_source": "user",
                                    "body": "parent",
                                    "body_sha256": hashlib.sha256(b"parent").hexdigest(),
                                    "received_at": 1,
                                    "parent_prompt_id": None,
                                    "automation": None,
                                },
                                "parent_host_source": "user",
                                "parent_scope": case["parent_scope"],
                                "assignment": case["assignment_scope"],
                            }
                        ),
                        encoding="utf-8",
                    )
                    context = context_path
                result = self.run_cli(
                    "classify-prompt", prompt, case["host_source"], context
                )
                if "error" in case["expected"]:
                    self.assertNotEqual(0, result.returncode, case["name"])
                    continue
                self.assertEqual(0, result.returncode, result.stderr)
                actual = json.loads(result.stdout)
                self.assertEqual(case["expected"]["authority"], actual["authority"])
                if "scope" in case["expected"]:
                    self.assertEqual(case["expected"]["scope"], actual["scope"])

    def test_automation_events_execute_persisted_claims(self):
        cases = [
            case
            for case in load_json(ROOT / "tests/fixtures/prompt-ux-cases.json")
            if "automation_event" in case
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, case in enumerate(cases):
                grant = {
                    "automation_id": "nightly",
                    "definition_digest": "d" * 64,
                    "scope_digest": "a" * 64,
                    "targets": ["repo/**"],
                    "operations": ["write", "verify", "rollback"],
                    "external_effects": ["git_push"],
                    "verification": ["cargo test"],
                    "rollback": ["git revert"],
                    "expires_at": 2**63,
                    "max_runs": 2,
                    "initial_sequence": 7,
                    "credential_policy": "platform_action",
                }
                request = {
                    "automation_id": "nightly",
                    "run_id": f"run-{index}",
                    "definition_digest": "d" * 64,
                    "scope_digest": "a" * 64,
                    "targets": ["repo/**"],
                    "operations": ["write", "verify"],
                    "external_effects": ["git_push"],
                    "verification": ["cargo test"],
                    "rollback": ["git revert"],
                    "sequence": 7,
                    "platform_action_required": False,
                }
                event = case["automation_event"]
                if event == "scope_change":
                    request["targets"].append("outside/**")
                elif event == "definition_change":
                    request["definition_digest"] = "e" * 64
                elif event == "credentials":
                    request["platform_action_required"] = True
                elif event == "sequence_change":
                    request["sequence"] = 8
                elif event == "verification_change":
                    request["verification"].append("unapproved check")
                elif event == "rollback_change":
                    request["rollback"].append("unapproved rollback")
                elif event == "invalid_effect":
                    request["external_effects"].append("bad\neffect")
                state = root / f"state-{index}.json"
                grant_path = root / f"grant-{index}.json"
                request_path = root / f"request-{index}.json"
                grant_path.write_text(json.dumps(grant), encoding="utf-8")
                request_path.write_text(json.dumps(request), encoding="utf-8")
                self.assertEqual(
                    0,
                    self.run_cli("automation-init", state, grant_path).returncode,
                )
                if event == "replay":
                    self.assertEqual(
                        "claimed",
                        json.loads(
                            self.run_cli(
                                "automation-claim", state, request_path, 1
                            ).stdout
                        )["status"],
                    )
                result = self.run_cli("automation-claim", state, request_path, 1)
                if "error" in case["expected"]:
                    self.assertNotEqual(0, result.returncode, case["name"])
                    continue
                actual = json.loads(result.stdout)
                for field, expected in case["expected"].items():
                    self.assertEqual(expected, actual[field], case["name"])

    def test_session_events_execute_atomic_session_updates(self):
        cases = {
            case["session_event"]: case
            for case in load_json(ROOT / "tests/fixtures/prompt-ux-cases.json")
            if "session_event" in case
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "session.md"
            user = {
                "prompt_id": "user-prompt",
                "session_id": "session-a",
                "claimed_source": "user",
                "body": "last external",
                "body_sha256": hashlib.sha256(b"last external").hexdigest(),
                "received_at": 1,
                "parent_prompt_id": None,
                "automation": None,
            }
            user_path = root / "user.json"
            user_path.write_text(json.dumps(user), encoding="utf-8")
            self.assertEqual(
                0,
                self.run_cli("session-update", session, user_path, "user", "-", "-").returncode,
            )
            internal = {
                **user,
                "prompt_id": "internal-prompt",
                "claimed_source": "internal",
                "body": "internal",
                "body_sha256": hashlib.sha256(b"internal").hexdigest(),
                "received_at": 2,
                "parent_prompt_id": "user-prompt",
            }
            internal_path = root / "internal.json"
            context_path = root / "context.json"
            internal_path.write_text(json.dumps(internal), encoding="utf-8")
            context_path.write_text(
                json.dumps(
                    {
                        "parent": {
                            "prompt_id": "user-prompt",
                            "session_id": "session-a",
                            "claimed_source": "user",
                            "body": "last external",
                            "body_sha256": hashlib.sha256(b"last external").hexdigest(),
                            "received_at": 1,
                            "parent_prompt_id": None,
                            "automation": None,
                        },
                        "parent_host_source": "user",
                        "parent_scope": ["repo/**"],
                        "assignment": ["repo/**"],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                0,
                self.run_cli(
                    "session-update", session, internal_path, "internal", context_path, "-"
                ).returncode,
            )
            markdown = session.read_text(encoding="utf-8")
            self.assertTrue(markdown.endswith("last external"))
            self.assertIn(
                f'active_source: "{cases["internal_update"]["expected"]["active_source"]}"',
                markdown,
            )

            automation = {
                **user,
                "prompt_id": "automation-prompt",
                "claimed_source": "automation",
                "body": "automation",
                "body_sha256": hashlib.sha256(b"automation").hexdigest(),
                "received_at": 3,
                "automation": {
                    "automation_id": "nightly",
                    "run_id": "automation-run",
                    "scope_digest": "a" * 64,
                },
            }
            grant = {
                "automation_id": "nightly", "definition_digest": "d" * 64,
                "scope_digest": "a" * 64, "targets": ["repo/**"],
                "operations": ["write", "verify", "rollback"],
                "external_effects": [], "verification": ["cargo test"],
                "rollback": ["git revert"], "expires_at": 2**63,
                "max_runs": 1, "initial_sequence": 7,
                "credential_policy": "none",
            }
            request = {
                "automation_id": "nightly", "run_id": "automation-run",
                "definition_digest": "d" * 64, "scope_digest": "a" * 64,
                "targets": ["repo/**"], "operations": ["write", "verify"],
                "external_effects": [], "verification": ["cargo test"],
                "rollback": ["git revert"], "sequence": 7,
                "platform_action_required": False,
            }
            paths = [root / name for name in ("automation.json", "grant.json", "run.json")]
            paths[0].write_text(json.dumps(automation), encoding="utf-8")
            paths[1].write_text(json.dumps(grant), encoding="utf-8")
            paths[2].write_text(json.dumps(request), encoding="utf-8")
            state = root / "automation-state.json"
            self.assertEqual(0, self.run_cli("automation-init", state, paths[1]).returncode)
            result = self.run_cli(
                "automation-session-update", session, paths[0], state, paths[2], 1, "-"
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(
                json.dumps(cases["trusted_automation"]["expected"]["label"], ensure_ascii=False),
                session.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
