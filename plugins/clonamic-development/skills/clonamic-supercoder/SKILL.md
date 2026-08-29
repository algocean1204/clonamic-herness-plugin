---
name: clonamic-supercoder
description: Apply conservative patch discipline to an already approved non-trivial code write when stale files or ambiguous edit targets create material risk. Skip read-only work, small exact edits, and writes outside approved scope.
---

# Clonamic Supercoder

Use the host's native file and terminal tools. This skill adds a patch contract, not a second runtime.

## Patch contract

Read [references/patch-contract.json](references/patch-contract.json), then:

1. Confirm the target and intended change are inside `approved_scope`.
2. Read a bounded window containing the complete edit target. Capture a content hash when the host supplies one.
3. Require exact, uniquely matching old content. Do not guess between matches or silently widen scope.
4. Re-read immediately before mutation when a deterministic stale check is unavailable. Report `capability_missing` instead of claiming hash verification.
5. Apply the smallest patch. Reject a candidate that fails an available syntax check; if an unexpected post-write syntax failure occurs, restore only when the unchanged post-image can be proven.
6. Run the narrowest relevant syntax, lint, and test checks after the last mutation. Unsupported checks stay explicit; they do not become passes.

Return one `CodeEvidence` containing status, changed files, patch results, checks actually run, unrun checks, and residual risks. The consumer owns any later completion verdict or report.

## Failure

- `stale_file` — the target changed after inspection; re-read before considering another patch.
- `ambiguous_match` — more than one target matches; add exact surrounding context or stop.
- `syntax_rejected` — the candidate is invalid; leave the pre-image intact when possible.
- `verification_failed` — a required check failed; preserve its output and do not claim success.
- `capability_missing` — a promised deterministic guard is unavailable; use the native path without claiming that guard ran.

Never invoke another agent, choose an executor, create authorization, decide completion, or write the user-facing report.
