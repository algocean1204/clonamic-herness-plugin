# Benchmark method

Clonamic benchmarks compare control overhead and outcome quality. They do not rank model intelligence.

No public performance score is published yet.

## Profiles

| Profile | Installed packages | Purpose |
|---|---|---|
| Native baseline | None | Measure the host without Clonamic |
| Core only | `clonamic-herness-plugin` | Measure routing, one write gate, completion checks, reporting, install, and rollback |
| Full package | Core plus all nine children | Measure optional routing, development gates, explicit state, document/PPT work, and bounded executor wrappers |

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

Label repository-only checks separately from live host measurements. Do not infer live installation from a manifest check, and do not report Grok validation success without a recorded Grok run.
