# Validation performance

The pre-change warm eight-worker median was 5.320 seconds for 26 local commands. The current suite
runs 28 commands with a 4.480-second median: 0.840 seconds faster, or 15.8%, while adding event UX,
runtime readiness, security, and portability coverage.

## Measurement

Measurements ran on macOS arm64 with Python 3.9.6 and Cargo 1.97.1. Every cell is the median of
three complete `python3 scripts/validate-public.py` runs. Warm runs reused `target/`; cold runs used
a new `CARGO_TARGET_DIR` each time. All runs exited zero with identical command coverage.

| Profile | Run 1 | Run 2 | Run 3 | Median |
|---|---:|---:|---:|---:|
| Warm, 1 worker | 17.510 s | 17.130 s | 17.260 s | 17.260 s |
| Warm, 2 workers | 9.820 s | 9.720 s | 9.590 s | 9.720 s |
| Warm, 4 workers | 6.060 s | 6.120 s | 6.140 s | 6.120 s |
| Warm, 8 workers | 4.460 s | 4.480 s | 4.500 s | 4.480 s |
| Cold, 8 workers | 13.150 s | 11.720 s | 11.480 s | 11.720 s |

Eight workers remain the default. The improvement comes from overlapping independent Python,
package, PPT, and rustfmt checks; removing copy-only package tests and the POSIX supervisor process;
and retaining Cargo clippy/test as ordered post-gates. No fixture sleep, timeout assertion, test,
manifest check, security check, or command identity was removed.

## Execution and failure behavior

Adapter drift and the debug binary build run first. Independent checks then run concurrently with
stable plan-order output. Every command has a configurable 300-second local deadline; CI uses 600
seconds per command plus a 30-minute job deadline. A timeout returns 124 and cleans the owned process
tree. Cargo clippy and tests remain sequential to avoid target-directory lock contention.

## Quality boundary

Twenty independently authored prompts of at least 1,500 characters provide deterministic contract
coverage, including six read-only classes. They do not prove model behavior. Black-box UX claims
require observed normalized host JSONL and are graded separately with
`scripts/evaluate-ux-events.py`; synthetic schema fixtures are explicitly ineligible as evidence.
