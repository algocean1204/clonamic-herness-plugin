---
name: clonamic-completion-check
description: Verify that requested work is actually complete immediately before reporting completion. Use after any non-trivial mutation, deployment, publication, or multi-step task; skip ordinary read-only answers and trivial acknowledgements.
---

# Clonamic Completion Check

Do not turn a model claim into a completion claim. Re-read the request and compare it with observable state after the final mutation.

## Gate

For every required item, record:

- delivered artifact or state;
- current evidence from this run;
- verdict: complete or unmet.

Fresh evidence means the exact test, diff, remote state, installed state, or output required by the item. Exit code alone proves only process exit. A test run before the last change is stale.

If any required item is unmet and work can continue, continue without asking. If the same required item fails in three materially different correction attempts, report a blocker instead of claiming completion.

When the `clonamic` binary is available, serialize the compact manifest described in [references/completion-manifest.md](references/completion-manifest.md) and run `clonamic verify <manifest>`.

Only after the verdict is complete may `clonamic-report` produce the final response.
