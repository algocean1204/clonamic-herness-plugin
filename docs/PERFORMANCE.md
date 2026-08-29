# Validation performance

The authoritative serial baseline is 12.390 seconds. The latest integrated three-run median is 6.730 seconds with four Python-suite workers.

## Measurement

The integrated measurements ran on macOS 26.5.1 arm64 with Python 3.9.6 and Cargo 1.97.1. Dependencies and Rust build artifacts were warm, Cargo ran offline, and `CLONAMIC_TEST_WORKERS=4`. Each run executed `python3 scripts/validate-public.py` with output suppressed while preserving its exit status.

| Measurement | Run 1 | Run 2 | Run 3 | Median |
| --- | ---: | ---: | ---: | ---: |
| Authoritative serial baseline | — | — | — | 12.390 s |
| Integrated parallel validation | 6.730 s | 6.890 s | 6.480 s | 6.730 s |

The median decreased by 5.660 seconds, or 45.7%. A full one-worker run completed in 13.771 seconds and a four-worker comparison run completed in 5.966 seconds before the later config and PPT safety suites were added. The current integrated suite includes executable provenance, automation, session, team, intent, review, process-tree cleanup, context-budget, plugin configuration, expanded memory, and hostile OOXML checks.

## Execution plan

The adapter drift check runs first. The root Python suite and independent `plugins/*/tests` suites then run concurrently, with root output first followed by stable sorted package paths. PPT checks and every Rust command remain sequential. All parallel Python results are collected before the first failure in plan order is returned.

`CLONAMIC_TEST_WORKERS` accepts integers from 1 through 4 and defaults to 4. Worker-count tests verify identical result and failure ordering for 1 and 4 workers. A nested root-suite check also verifies that concurrent root tests leave the tracked diff unchanged and that supervised descendants do not survive.

## Quality gate

Speed is reported separately from behavior quality. Fourteen independently authored user and automation scenarios each exceed 1,500 characters, reject duplicate paragraphs and near-duplicate prompts, and execute the real core CLI plus the canonical team, intent, and review evaluators. Expected results cover trusted and unverified sources, forged automation markers, scope changes, platform credentials, unavailable team capability, bounded review, and blocked completion. No model name, model score, keyword score, or fixture-specific routing threshold affects validation success.

Process supervision is also a correctness gate. Tests start descendants that outlive their direct parent and prove cleanup after success, nonzero failure, cancellation, and POSIX interruption. POSIX uses a dedicated process group; Windows uses a kill-on-close Job Object without an external process-tree utility.
