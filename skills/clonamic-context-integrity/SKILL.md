---
name: clonamic-context-integrity
description: >
  Context-integrity doctrine to minimize hallucination in long sessions — verify-before-assert,
  high-context checkpointing, post-compaction staleness rules, importance-based double-pass
  compaction. Use in long sessions, when context feels saturated, after compaction, or when
  the user mentions 환각/hallucination/컨텍스트/압축.
---

# Anti-Hallucination (Context Integrity)

> Hallucination risk scales with context saturation and survives through lossy compaction.
> The defense: verify instead of recall, checkpoint before saturation, compress with a
> double pass.

## 1. Verify-before-assert

- Any fact recalled from >30 turns ago, or from before a compaction: **re-verify** via
  `rg`/Read before stating it or acting on it. Recalled line numbers are always stale.
- State verified vs assumed explicitly. An unverified claim is labeled UNVERIFIED, never
  presented as fact.
- Never fabricate CLI flags, API signatures, or file contents — check `--help`/source first
  (cheaper than one wrong command).

## 2. High-context protocol (before saturation)

- When the session is long/heavy: **checkpoint critical state to disk** — active task spec,
  locked quantities, decisions + reasons, touched file list — into the task's scratchpad or
  memory topic file. Disk survives; context doesn't.
- Prefer re-reading a source snippet over trusting memory of it. Reads are cheap;
  wrong recall is not.
- Big multi-phase work: keep the phase state in a file (N/N done), not only in conversation.

## 3. Compaction (double-pass — mirrors hooks/precompact-guard.sh)

PASS 1 — extract must-keep verbatim: task spec + quantities + item states, user decisions
and reasons, file paths + key line refs, UNVERIFIED claims, open blockers, session invariants.
PASS 2 — re-scan the original: anything referenced later but missing from the summary goes
back in. Drop narration and raw tool logs first; never drop failures or corrections.

## 4. Post-compaction rules

- Treat everything recalled through a summary as **stale-by-default**: re-verify paths,
  line numbers, and progress state before the next action.
- First action after compaction on a task: re-read the checkpoint file (§2), not the summary.

## Harness wiring (Codex)

- No equivalent PreCompact lifecycle hook or `autoCompactWindow` config on this host —
  apply the §3 double-pass manually when summarizing or when context feels saturated.
- Checkpoint critical state to disk (§2) is the first defense; do not wait for an automatic
  compaction guard that does not exist here.
