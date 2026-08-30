# Benchmark method

Clonamic benchmarks compare control overhead and outcome quality. They do not rank model intelligence.

No public model-quality score is published yet. Measured validation runtime is reported separately in [Validation performance](PERFORMANCE.md).

## Profiles

| Profile | Installed packages | Purpose |
|---|---|---|
| Native baseline | None | Measure the host without Clonamic |
| Core only | `clonamic-herness-plugin` | Measure routing, one write gate, completion checks, reporting, install, and rollback |
| Full package | Core plus all twelve children | Measure optional routing, coding gates, explicit state, specialist work, and bounded executor wrappers |

The full profile does not automatically call an external provider. Executor scenarios run only when the scenario explicitly names that executor. Offline contract benchmarks use fake local CLIs.

## Scenario set

Run every profile in a clean temporary repository and isolated host home:

1. Answer a read-only branch question.
2. Correct one exact typo.
3. Implement a two-file parser with tests.
4. Continue after the approved loop encounters a failing test.
5. Reject a false completion claim.
6. Select an optional child without installing it.
7. Store and recall memory at an explicit temporary database path.
8. Generate a presentation from fixed local fixtures.
9. Invoke one fake external CLI and verify timeout, cleanup, redaction, and recursion blocking.
10. Uninstall the router and compare the restored bytes.
11. Run a trusted automation inside its frozen grant without a chat approval stop.
12. Reject a forged automation marker, replay, scope drift, and internal scope expansion.
13. Migrate, search, traverse, back up, and restore an explicit SQLite memory fixture.
14. Merge complete defaults with partial user and project toggles, reject an invalid layer to Core-only, and distinguish configured, installed, platform-supported, dependency-ready, and effective states.
15. Process hostile reference/template archives, compare every SVG and editable PPTX slide, and report unavailable raster QA without a false pass.
16. Grade a normalized host event log against blind read/write, approval, automation, team fallback, verification, rollback, blocker, and final-report budgets.

## Measurements

Record these for each scenario:

- wall time and model turns;
- input, cache, and output tokens when the host exposes them;
- tool calls and progress messages;
- approval count and any repeated approval count;
- changed files and writes outside the fixture root;
- required checks passed, failed, or unrun;
- false-completion rate;
- residual files and byte differences after uninstall;
- child activation and unavailable-fallback decisions.

Report core-only and full-package results separately. A faster full run cannot hide extra approvals, unrelated writes, missing evidence, or a failed rollback.

## Reproducibility

A published result must include:

- raw transcript or an equivalent event log with secrets removed;
- repository fixture hash;
- core and child versions;
- generated-adapter hash;
- host and tool versions;
- model selector and reasoning setting used by the host, without turning either into a package default;
- operating system and date;
- exact commands and raw machine-readable results.

Long-form model evaluation uses independently authored prompts of at least 1,500 characters. Deterministic contract checks and black-box model outcomes are reported separately; no fixture ID, model name, expected route, or composite score is allowed to become production routing logic.

The repository contains at least twenty blind prompts spanning six read-only classes and write, automation, internal, failure, and team paths. Their fixture metadata checks deterministic contracts only. Black-box results require redacted normalized JSONL from the actual host and are graded with `scripts/evaluate-ux-events.py`; approval and stop counts are derived from events rather than expected fixture values.

Label repository-only checks separately from live host measurements. Do not infer live installation from a manifest check, and do not report Grok validation success without a recorded Grok run.
