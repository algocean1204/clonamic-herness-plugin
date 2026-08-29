---
name: clonamic-session-intent
description: Session-scoped intent and DoD maintenance. Load for explicit session-scoped requirements, a missing/stale/conflicting injected core, unfinished-session resume, ambiguous completion evidence, or temptation to ask whether to continue while work remains. Use to create or reconcile the current UUID core; ordinary task execution and completion rely on the always-on intent rule and hook injection, so do not load this body on every prompt or turn. Triggers — 세션 지시, 요구사항 변경 기록, resume 상태 충돌, 완료 판정 진단, DoD ambiguity, 의도 추적 요청.
---

# clonamic-session-intent
One mechanism, two halves: a persistent intent file and a completion-loop gate that decides whether a turn may end. Both run silently — never narrate them.

## 1. One bounded file per logical session

The file is injected every prompt, so every line is paid every turn. Keep one lean,
state-only core rather than growing a transcript or adding another session-state file.

The file is **per logical session** (full UUID `session_id`, never cwd). Canonical path:

`~/.claude/session-intent/<uuid>/core.md`

Resolve for THIS session with `python3 ~/.claude/hooks/session_intent_paths.py --session-id "$SID" core`, or pass hook JSON via `--from-stdin`. The helper prefers a valid hook `session_id`; fallback is only a full-UUID basename of `transcript_path`; otherwise no path (no cwd/hash/unknown/short-UUID/shared-seed). The legacy `detail` selector intentionally returns empty. intent-lock names the core path in its injected header when a core exists; if the SID is valid but core is absent, it prints one concise exact core path hint so the session can create it on the first prompt. Never read another SID or cwd-legacy core. **Ownership:** a core is written only by its own logical session's orchestrator. A delegated subagent or external CLI must never search for (no glob over `session-intent/`), read, infer, or write another SID's core; its subtask never replaces the parent's user-level Task/DoD, even in a core its own SID resolves. If its own validated hook/session SID resolves no path, it writes no core and reports state only in its reply to the orchestrator.

cwd-keyed directories and `_legacy*` under `session-intent/` are recovery-only (not injected, not archived by the SID hook). Legacy flat `~/.claude/SESSION_INTENT.md`/`SESSION_DETAIL.md` are auto-migrated to `_legacy*.md` once.

- **`session-intent/<uuid>/core.md` (injected)** — target **~20 lines / ~1.5 KB** (config-doctor WARNs above the 2.5 KB ceiling per §5 — never fails; 1.5 KB is the trim target). Holds ONLY the metadata and compact current ID rows below, plus session-specific overrides and one explicit handoff/checkpoint pointer when needed. Include only applicable rows. Overwrite in place; never append.

```md
# Session Core
State: <pending|executing|blocked|closed>
Approval: <current approval state>
ID: <session UUID>
Time: <started> / <updated>
Token: <measured input/output/total|unavailable>

## 작업명세서 [ACTIVE|CLOSED]
- W1: <requirement>
- O1: <output>
- A1: <acceptance>
- X1: <exclusion>

## 개발명세서 [N/A|PENDING|APPROVED|CLOSED]
- D1 [W1]: <change>
- V1 [A1]: <verification>
- R1 [D1]: <outside-project recovery; omit when inapplicable>

## 보고명세서 [PENDING|FINAL]
- Status: <final-stage only|ID verdicts>
- Apply/deploy/backup: <applicable status>
- Unverified/blocker: <none|item>
- Risk/issue: <none|item>
- Next action: <none|user-only unblock>
```

The real lever is STATE-ONLY with ZERO running history. A State item tracks STATE ("streak 0/5", "cycle-4 running"), never a running log. Per-cycle evidence (what each sweep found/fixed, test counts, commit hashes) belongs in git history or an explicitly authorized project handoff/checkpoint, NOT here — the file may hold only a bare pointer ("latest: X closed, selftest N/0"). If it nears its cap, compress before adding. When a task needs a Definition of Done, put it in the State block as verifiable checkboxes (each names its check — "works well" is not a DoD item).

Use stable W/O/A/X and D/V IDs plus conditional R rows from the approved chat packets, but compress each into one state row;
the chat packets remain the authoritative detail. Use development `N/A` when the task has no
implementation stage. While executing, keep the report section to one pending line. After the final
chat report, retain the compact `closed` snapshot until the next task overwrites it. Never store
approval prose, the Manifest body, command output, per-cycle evidence, or revision history in the core. Record tokens
only from a measured runtime value; otherwise write `unavailable` rather than estimate.

## 2. Per-prompt update judgment

On each user prompt, judge once: is this a new task, approval transition, material direction change,
blocker, or final closure?
- Yes → overwrite only the affected current rows, update `Time`, then work.
- No (question, "go on", ack, small nudge, ordinary execution milestone) → leave the file untouched.

**Directive-target gate** (classify BEFORE acting; default scope = session):
- **HOW-I-WORK** — model/tool choice, verify-method, delegation, tone, ordering (no explicit artifact operation) → record in this session's core ONLY. Never write it into CLAUDE.md, a rule, a guide, a skill, or a hook.
- **CHANGE-A-THING** — a concrete edit to code, or to `~/.claude` / `~/.codex` config, that the user names → act on it (that operation only).
- **Ambiguous** → ask one line ("이번 세션만, 아니면 앞으로 항상?"); default to session; make no persistent global write.

Classify by the directive's DIRECT OBJECT (an explicit artifact operation), NOT persistence words like "always / use / avoid" — inferring globalization from a general-sounding directive is the over-application to avoid. Promote a working-method into global guidance/rule/skill ONLY on explicit say-so ("앞으로 항상", "글로벌 규칙으로", "make this standing").

## 3. Completion loop — run before ending ANY working turn

1. Read the DoD plus the request's per-item list (every enumerated item, quantity, file).
2. Judge EACH item individually: met-with-evidence or unmet. Never batch-judge — "mostly done" means unmet. Evidence rules live in skill `verification-before-completion`; do not re-derive them here.
3. All items met → check them off, report per `clonamic-report`. The turn may end.
4. Any item unmet and no external blocker → adjust approach and CONTINUE in this same turn. Do not stop; do not ask. Loop back to step 1 (bound: if 3 adjust cycles fail on the same item, treat it as a blocker).
5. Real external blocker only (missing credential, user-only decision, hard failure after retries) → state the blocker, what is done, what remains. Naming a blocker is the ONLY sanctioned early stop.

## 4. Hard prohibition

While any DoD item is unmet: NEVER emit "이어서 할까요?", "계속할까요?", "진행할까요?", or any continue-permission question. Continuation is the default, not a request. Asking permission to finish assigned work is a completion-loop failure, not politeness.

## 5. Wiring

- `intent-lock.py` (Claude UserPromptSubmit hook) resolves only this SID's core via `session_intent_paths.py` and injects it each turn; if core is absent but SID is valid, prints the exact core path hint (create on first prompt). The Codex UserPromptSubmit adapter uses the same resolver and emits the same bounded core through `hookSpecificOutput.additionalContext`. This skill owns writing the file; hooks only read it.
- `session-intent-archive.sh` (Claude SessionEnd hook) archives the core into forgetforge as `session-intent-<session_id>` with `--node-type session --session-id <session_id> --expire-days 90` — recall/hot-invisible, session graph-recallable, TTL-swept by prune. Archives only a validated full-UUID SID (never `unknown`). Keeps the on-disk file for ordinary resume; does not promote/move to a shared seed or delete. **Retention choice:** archived UUID directories stay as small recovery state because resume may reuse the SID — no automatic age deletion/GC without a proven archive-success ownership signal (do not add a SessionStart/Stop GC hook for this). Codex has no SessionEnd hook, so do not misuse its turn-level Stop event for archival. A completed task stays as one compact `closed` snapshot until a new task overwrites it.
- `precompact-guard.sh` (existing PreCompact hook) parses hook JSON and includes only this SID's lean core in the MUST-KEEP block — no new hook.
- `config-doctor.py` warns if any **full-UUID** active core exceeds its ~2.5 KB injection budget; cwd-keyed, legacy detail files, and `_legacy*` dirs are recovery-only and untouched.
- Evidence discipline: `verification-before-completion`. Report form: `clonamic-report`.

## 6. Hard bans (do not add)

No index, DB, locks/stamps, new SessionStart/Stop hook for intent, auto legacy attribution, mtime mapping, seed inheritance, archive deletion, or GC daemon.
