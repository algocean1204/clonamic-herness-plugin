---
name: clonamic-preprocessing
description: Normalize fuzzy or multi-item input, build a caller-directed clarification packet, queue independent work, and run loop_auto only after explicit opt-in. Skip precise single-item requests.
---

# Clonamic Preprocessing

Use this skill only when normalization, material clarification, or a work queue makes the request easier to execute. Precise single-item work stays on the native path.

## Runtime

Use `scripts/preprocessing.py` for deterministic operations. Read [references/runtime-contract.json](references/runtime-contract.json) before persisting a queue.

- `normalize_text(text)` — normalize Unicode, spaces, newlines, and repeated blank lines without changing meaning.
- `clarification_contract(text, missing_fields)` — ask only about material fields the caller identified as missing.
- `enqueue`, `claim_next`, `record`, `queue_state` — maintain a priority-then-FIFO queue at an explicit path.
- `run_loop_auto(path, executor, enabled=True)` — drain queued items through a caller-supplied callable.

The queue stores normalized work text, priority, sequence, state, claim token, attempt count, and the caller's structured result. Each mutation uses a create-new lock with bounded waiting and atomic replacement. A stale active claim returns to pending; the old claim token can no longer record it.

## Explicit loop_auto

Run loop_auto only when the current user request or an already accepted work packet sets `loop_auto=true`. Never infer opt-in from task size or queue length. The caller supplies the executor and retains control of each work item.

Stop on an executor error or the declared step limit. Preserve the failed item and leave later items pending. A disabled request performs no calls and no queue mutation.

## Result

Return one `PreprocessingResult` containing normalized input, clarification questions, queued item identifiers, loop status, and any runtime error. The caller owns later execution and the final response.
