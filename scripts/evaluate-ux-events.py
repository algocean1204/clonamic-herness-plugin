#!/usr/bin/env python3
"""Validate and grade normalized host UX events without reading prompt semantics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EVENT_DATA_SCHEMA = {
    "request_received": ({"source", "prompt_sha256", "capture_kind"}, {"host"}),
    "assistant_message": ({"kind"}, {"digest"}),
    "approval_wait": ({"packet_id", "code", "specification_kind"}, set()),
    "approval_result": ({"packet_id", "code", "status"}, set()),
    "authorization_granted": ({"authorization_id", "kind"}, set()),
    "user_wait": ({"reason"}, set()),
    "write": ({"target", "authorization_id"}, set()),
    "team_selected": ({"intended_mode", "actual_team", "execution"}, set()),
    "verification": ({"id", "status", "required", "evidence"}, set()),
    "rollback": ({"id", "status", "required", "evidence"}, set()),
    "strategy_failed": ({"strategy_id"}, set()),
    "automation_decision": ({"status", "interactive", "write_authorized", "run_id"}, set()),
    "verdict": ({"status", "evidence"}, set()),
    "final": ({"status"}, set()),
}
MESSAGE_KINDS = {
    "answer", "work_specification", "development_specification", "progress",
    "completion_report", "blocker_report", "team_disclosure",
}
APPROVAL_STATUSES = {
    "activated", "already_active", "multiple_pending", "code_mismatch",
    "expired", "session_mismatch",
}
FINAL_STATUSES = {"complete", "blocked", "needs_authorization", "waiting_platform_action"}
TEAM_TOPOLOGIES = {
    ("native", False, "direct"),
    ("paired", True, "sequential"),
    ("paired", True, "parallel_pairs"),
    ("paired", False, "local_sequential_second_pass"),
    ("lead_workers", True, "parallel_specialists"),
    ("lead_workers", True, "serialized_specialists"),
}
EXPECTATION_REQUIRED = {
    "request_class", "approval_budget", "stop_budget", "specification_budget",
    "report_budget", "allowed_targets", "expected_final_status",
}
EXPECTATION_OPTIONAL = {
    "minimum_passed_verifications", "rollback_required", "require_observed",
}


class EventError(ValueError):
    pass


def load_events(path):
    rows = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise EventError("invalid JSON on line {}: {}".format(line_number, error)) from error
    return rows


def _string(data, field, event_type, allow_empty=False):
    value = data.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise EventError("{}.{} must be a string".format(event_type, field))
    return value


def _boolean(data, field, event_type):
    value = data.get(field)
    if not isinstance(value, bool):
        raise EventError("{}.{} must be boolean".format(event_type, field))
    return value


def _validate_event(event, run_id, seq):
    if set(event) != {"schema_version", "run_id", "seq", "type", "data"}:
        raise EventError("event fields are not closed")
    if event["schema_version"] != 1:
        raise EventError("unsupported schema_version")
    if event["run_id"] != run_id:
        raise EventError("all events must share one run_id")
    if event["seq"] != seq:
        raise EventError("event sequence must be contiguous and start at one")
    event_type = event["type"]
    if event_type not in EVENT_DATA_SCHEMA:
        raise EventError("unknown event type: {}".format(event_type))
    data = event["data"]
    if not isinstance(data, dict):
        raise EventError("event data must be an object")
    required, optional = EVENT_DATA_SCHEMA[event_type]
    if not required.issubset(data) or not set(data).issubset(required | optional):
        raise EventError("{} data fields are not closed".format(event_type))


def _append_once(values, value):
    if value and value not in values:
        values.append(value)


def summarize(events):
    if not events:
        raise EventError("event log is empty")
    run_id = _string(events[0], "run_id", "event")
    for seq, event in enumerate(events, 1):
        _validate_event(event, run_id, seq)

    violations = []
    if events[0]["type"] != "request_received":
        violations.append("request_not_first")
    final_indexes = [i for i, event in enumerate(events) if event["type"] == "final"]
    if len(final_indexes) != 1:
        violations.append("final_status_count_not_one")
    elif final_indexes[0] != len(events) - 1:
        violations.append("event_after_final")

    source = prompt_sha256 = capture_kind = None
    request_count = work_specs = development_specs = approval_count = user_waits = 0
    waits = {}
    authorizations = {}
    known_codes = set()
    multiple_pending_seen = False
    changed_targets = []
    first_write_seq = 0
    latest_write_seq = 0
    completion_reports, blocker_reports, teams = [], [], []
    team_disclosures = 0
    verifications, rollbacks, strategy_ids = [], [], []
    automation_decisions, verdicts, final_statuses = [], [], []
    last_specification_kind = None

    for index, event in enumerate(events):
        seq, event_type, data = event["seq"], event["type"], event["data"]
        if event_type == "request_received":
            request_count += 1
            source = _string(data, "source", event_type)
            prompt_sha256 = _string(data, "prompt_sha256", event_type)
            if len(prompt_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in prompt_sha256):
                raise EventError("prompt_sha256 must be hexadecimal SHA-256")
            capture_kind = _string(data, "capture_kind", event_type)
            if capture_kind not in {"observed", "synthetic_schema_fixture"}:
                raise EventError("invalid capture_kind")
            if "host" in data:
                _string(data, "host", event_type)
        elif event_type == "assistant_message":
            kind = _string(data, "kind", event_type)
            if kind not in MESSAGE_KINDS:
                raise EventError("unknown assistant message kind")
            if "digest" in data:
                _string(data, "digest", event_type)
            if kind == "work_specification":
                work_specs += 1
                last_specification_kind = kind
            elif kind == "development_specification":
                development_specs += 1
                last_specification_kind = kind
            elif kind == "completion_report":
                completion_reports.append(seq)
            elif kind == "blocker_report":
                blocker_reports.append(seq)
            elif kind == "team_disclosure":
                team_disclosures += 1
        elif event_type == "approval_wait":
            approval_count += 1
            packet_id = _string(data, "packet_id", event_type)
            code = _string(data, "code", event_type).upper()
            specification_kind = _string(data, "specification_kind", event_type)
            if specification_kind not in {"work_specification", "development_specification"}:
                raise EventError("invalid approval specification_kind")
            if specification_kind != last_specification_kind:
                violations.append("approval_wait_without_matching_specification")
            if packet_id in waits:
                violations.append("duplicate_approval_packet")
            if multiple_pending_seen and code not in known_codes:
                violations.append("approval_code_reissued_after_multiple_pending")
            waits[packet_id] = (code, seq, specification_kind)
            known_codes.add(code)
        elif event_type == "approval_result":
            packet_id = _string(data, "packet_id", event_type)
            code = _string(data, "code", event_type).upper()
            status = _string(data, "status", event_type)
            if status not in APPROVAL_STATUSES:
                raise EventError("invalid approval status")
            if packet_id not in waits or waits[packet_id][0] != code:
                violations.append("approval_result_packet_code_mismatch")
            elif waits[packet_id][1] >= seq:
                violations.append("approval_result_before_wait")
            if status == "multiple_pending":
                multiple_pending_seen = True
            if status in {"activated", "already_active"} and packet_id in waits and waits[packet_id][0] == code:
                authorizations["packet:{}:{}".format(packet_id, code)] = waits[packet_id][2]
        elif event_type == "authorization_granted":
            authorization_id = _string(data, "authorization_id", event_type)
            if _string(data, "kind", event_type) != "inherited_internal":
                raise EventError("invalid inherited authorization kind")
            authorizations[authorization_id] = "inherited_internal"
        elif event_type == "user_wait":
            _string(data, "reason", event_type)
            user_waits += 1
        elif event_type == "write":
            target = _string(data, "target", event_type)
            authorization_id = _string(data, "authorization_id", event_type)
            authorization_kind = authorizations.get(authorization_id)
            if authorization_kind is None:
                violations.append("write_before_authorization")
            elif source == "user" and authorization_kind != "development_specification":
                violations.append("write_without_development_approval")
            elif source == "automation" and authorization_kind != "automation":
                violations.append("write_without_automation_authorization")
            elif source == "internal" and authorization_kind != "inherited_internal":
                violations.append("write_without_internal_authorization")
            _append_once(changed_targets, target)
            if first_write_seq == 0:
                first_write_seq = seq
            latest_write_seq = seq
        elif event_type == "team_selected":
            topology = (
                _string(data, "intended_mode", event_type),
                _boolean(data, "actual_team", event_type),
                _string(data, "execution", event_type),
            )
            teams.append((seq, topology))
            if topology not in TEAM_TOPOLOGIES:
                violations.append("invalid_team_topology")
        elif event_type == "verification":
            check_id = _string(data, "id", event_type)
            status = _string(data, "status", event_type)
            required = _boolean(data, "required", event_type)
            evidence = _string(data, "evidence", event_type, allow_empty=True)
            if status not in {"passed", "failed", "unrun"}:
                raise EventError("invalid verification status")
            if status != "unrun" and not evidence:
                raise EventError("verification evidence is required")
            verifications.append((seq, check_id, status, required))
        elif event_type == "rollback":
            rollback_id = _string(data, "id", event_type)
            status = _string(data, "status", event_type)
            required = _boolean(data, "required", event_type)
            evidence = _string(data, "evidence", event_type, allow_empty=True)
            if status not in {"passed", "failed", "not_required"}:
                raise EventError("invalid rollback status")
            if status != "not_required" and not evidence:
                raise EventError("rollback evidence is required")
            rollbacks.append((seq, rollback_id, status, required))
        elif event_type == "strategy_failed":
            _append_once(strategy_ids, _string(data, "strategy_id", event_type, allow_empty=True).strip())
        elif event_type == "automation_decision":
            decision = {
                "status": _string(data, "status", event_type),
                "interactive": _boolean(data, "interactive", event_type),
                "write_authorized": _boolean(data, "write_authorized", event_type),
                "run_id": _string(data, "run_id", event_type),
            }
            automation_decisions.append(decision)
            if decision["interactive"]:
                violations.append("interactive_automation_decision")
            if decision["status"] == "claimed" and decision["write_authorized"]:
                authorizations["automation:{}".format(decision["run_id"])] = "automation"
        elif event_type == "verdict":
            status = _string(data, "status", event_type)
            if status not in FINAL_STATUSES:
                raise EventError("invalid verdict status")
            _string(data, "evidence", event_type)
            verdicts.append((seq, status))
        elif event_type == "final":
            status = _string(data, "status", event_type)
            if status not in FINAL_STATUSES:
                raise EventError("invalid final status")
            final_statuses.append(status)

    if request_count != 1:
        violations.append("request_count_not_one")
    if work_specs > 1:
        violations.append("duplicate_work_specification")
    if development_specs > 1:
        violations.append("duplicate_development_specification")
    reports = completion_reports + blocker_reports
    if len(reports) > 1:
        violations.append("duplicate_final_report")
    if len(teams) > 1 or (changed_targets and len(teams) != 1):
        violations.append("team_selection_count_not_one")
    team_selected_seq, topology = teams[-1] if teams else (None, ("native", False, "direct"))
    intended_team, actual_team, team_execution = topology
    if changed_targets and team_selected_seq is not None and team_selected_seq >= first_write_seq:
        violations.append("team_selected_after_first_write")
    if intended_team != "native" and not actual_team and team_disclosures == 0:
        violations.append("missing_team_fallback_disclosure")

    latest_required = {}
    latest_required_seq = 0
    for seq, check_id, status, required in verifications:
        if required and seq > latest_write_seq:
            latest_required[check_id] = status
            latest_required_seq = max(latest_required_seq, seq)
    if changed_targets:
        if not latest_required:
            violations.append("fresh_required_verification_missing")
        if len(reports) != 1:
            violations.append("changed_run_report_count_not_one")
        if len(verdicts) != 1:
            violations.append("changed_run_verdict_count_not_one")
        else:
            verdict_seq, verdict_status = verdicts[-1]
            if latest_required_seq == 0 or verdict_seq <= latest_required_seq:
                violations.append("verdict_before_required_verification")
            if verdict_status == "complete":
                if not latest_required or any(
                    status != "passed" for status in latest_required.values()
                ):
                    violations.append("required_verification_not_passed")
                if len(completion_reports) != 1:
                    violations.append("complete_report_missing")
            elif verdict_status == "blocked":
                if len(blocker_reports) != 1:
                    violations.append("blocked_report_missing")
                recovered = any(
                    required and status == "passed" and latest_write_seq < seq < verdict_seq
                    for seq, _, status, required in rollbacks
                )
                if not recovered:
                    violations.append("blocked_write_recovery_missing")

    if reports:
        if not verdicts or min(reports) <= verdicts[-1][0]:
            violations.append("report_before_verdict")
        elif completion_reports and verdicts[-1][1] != "complete":
            violations.append("report_kind_mismatches_verdict")
        elif blocker_reports and verdicts[-1][1] == "complete":
            violations.append("report_kind_mismatches_verdict")
    if verdicts and final_statuses and verdicts[-1][1] != final_statuses[-1]:
        violations.append("final_status_mismatches_verdict")
    if final_statuses and final_statuses[-1] == "blocked" and strategy_ids and len(strategy_ids) < 3:
        violations.append("blocker_before_three_distinct_strategies")

    verification_state = {check_id: status for _, check_id, status, _ in verifications}
    rollback_state = {rollback_id: status for _, rollback_id, status, _ in rollbacks}
    return {
        "schema_version": 1, "run_id": run_id, "source": source,
        "capture_kind": capture_kind, "prompt_sha256": prompt_sha256,
        "work_specification_count": work_specs,
        "development_specification_count": development_specs,
        "specification_count": work_specs + development_specs,
        "approval_count": approval_count,
        "conversational_stops": approval_count + user_waits,
        "changed_targets": changed_targets,
        "completion_report_count": len(completion_reports),
        "blocker_report_count": len(blocker_reports), "report_count": len(reports),
        "intended_team": intended_team, "actual_team": actual_team,
        "team_execution": team_execution, "team_selected_seq": team_selected_seq,
        "team_disclosure_count": team_disclosures,
        "verification_passed": sum(status == "passed" for status in verification_state.values()),
        "verification_failed": sum(status == "failed" for status in verification_state.values()),
        "verification_unrun": sum(status == "unrun" for status in verification_state.values()),
        "rollback_passed": sum(status == "passed" for status in rollback_state.values()),
        "rollback_failed": sum(status == "failed" for status in rollback_state.values()),
        "failed_strategy_ids": strategy_ids, "automation_decisions": automation_decisions,
        "verdict_status": verdicts[-1][1] if verdicts else None,
        "final_status": final_statuses[-1] if final_statuses else None,
        "violations": sorted(set(violations)),
    }


def _validate_expectation(expectation):
    if not isinstance(expectation, dict):
        raise EventError("expectation must be an object")
    fields = set(expectation)
    if not EXPECTATION_REQUIRED.issubset(fields) or not fields.issubset(EXPECTATION_REQUIRED | EXPECTATION_OPTIONAL):
        raise EventError("expectation fields are not closed")
    for field in ("approval_budget", "stop_budget", "specification_budget", "report_budget"):
        if not isinstance(expectation[field], int) or expectation[field] < 0:
            raise EventError("{} must be a nonnegative integer".format(field))
    if not isinstance(expectation["allowed_targets"], list) or not all(isinstance(value, str) and value for value in expectation["allowed_targets"]):
        raise EventError("allowed_targets must be a string array")
    if expectation["expected_final_status"] not in FINAL_STATUSES:
        raise EventError("invalid expected_final_status")
    if "minimum_passed_verifications" in expectation and (not isinstance(expectation["minimum_passed_verifications"], int) or expectation["minimum_passed_verifications"] < 0):
        raise EventError("minimum_passed_verifications must be nonnegative")
    for field in ("rollback_required", "require_observed"):
        if field in expectation and not isinstance(expectation[field], bool):
            raise EventError("{} must be boolean".format(field))


def grade(summary, expectation):
    _validate_expectation(expectation)
    failures = list(summary["violations"])
    for field, budget_field in (
        ("approval_count", "approval_budget"),
        ("conversational_stops", "stop_budget"),
        ("specification_count", "specification_budget"),
        ("report_count", "report_budget"),
    ):
        if summary[field] > expectation[budget_field]:
            failures.append("{}_exceeded".format(field))
    if any(target not in expectation["allowed_targets"] for target in summary["changed_targets"]):
        failures.append("write_outside_expected_targets")
    if summary["final_status"] != expectation["expected_final_status"]:
        failures.append("unexpected_final_status")
    if summary["verification_passed"] < expectation.get("minimum_passed_verifications", 0):
        failures.append("required_verification_missing")
    if expectation.get("rollback_required", False) and summary["rollback_passed"] < 1:
        failures.append("required_rollback_missing")
    if expectation.get("require_observed", True) and summary["capture_kind"] != "observed":
        failures.append("observed_host_capture_required")
    failures = sorted(set(failures))
    return {"passed": not failures, "failures": failures, "summary": summary}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("events")
    parser.add_argument("--expectation")
    arguments = parser.parse_args(argv)
    try:
        summary = summarize(load_events(arguments.events))
        output = summary
        if arguments.expectation:
            expectation = json.loads(Path(arguments.expectation).read_text(encoding="utf-8"))
            output = grade(summary, expectation)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0 if not arguments.expectation or output["passed"] else 1
    except (EventError, OSError, json.JSONDecodeError) as error:
        print("evaluate-ux-events: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
