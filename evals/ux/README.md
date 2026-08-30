# UX event protocol

Model and host behavior is measured only from events captured by the host that ran the request. The evaluator never derives routing, approval, completion, or quality from prompt text or fixture metadata.

Each JSONL row has exactly `schema_version`, `run_id`, `seq`, `type`, and `data`. Sequence numbers start at one and are contiguous. `request_received` is first, `final` is last, and every event type uses the closed data schema in `scripts/evaluate-ux-events.py`.

Real measurements use `capture_kind: observed` and name the host that emitted the events. Capture assistant message kinds, approval waits and results, authorization identifiers, writes, team selection, verification, rollback, verdict, report, and final status at the host boundary. Store a prompt SHA-256, not prompt bytes. Do not reconstruct missing events after the run.

`synthetic-two-gate.jsonl` is the only example. It is a synthetic schema fixture, not an observed run and not evidence of model quality. Its expectation explicitly disables the observed-capture requirement.

```sh
python scripts/evaluate-ux-events.py \
  evals/ux/synthetic-two-gate.jsonl \
  --expectation evals/ux/synthetic-two-gate-expectation.json
```
