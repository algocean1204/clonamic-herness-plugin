---
name: clonamic-write-control
description: Control persistent writes with proportional specifications and one reusable approval. Use before creating, editing, deleting, installing, applying, deploying, publishing, sending, or otherwise mutating state. Never load for questions, opinions, inspection, review, or other read-only work.
---

# Clonamic Write Control

Keep reads frictionless and writes deliberate. The model owns judgment; deterministic tooling only verifies the write boundary.

## Route

1. Read-only request → leave this skill and answer directly. No specification, approval, plan file, or workflow status.
2. Clear persistent write → present one chat-only development specification, then wait for one approval.
3. Materially ambiguous write → present one work specification to lock intent; inspect after approval; present one development specification before mutation.
4. Precise tiny write → the development specification may be one compact line containing target, change, verification, rollback, and approval code.

Do not add a second gate because implementation details changed. Return to a gate only when scope, authority, user-visible output, or risk materially changes.

## Approval

- Present `승인:ABC123` as a correlation code, not as a security factor.
- Accept one surrounding backtick pair, the fullwidth colon, surrounding whitespace, and lowercase code input.
- When only one packet is pending, a plain `승인` may select it; multiple pending packets require the code.
- One approved development specification covers its entire inspect-fix-retest-apply-deploy-backup loop. Never ask again per command or iteration.
- Password, OAuth, biometric, and platform permission prompts remain platform actions.

Use the `clonamic` binary when available to issue or validate a grant. If structural hooks are unavailable, apply the same contract model-side and disclose that fallback only when it affects the requested write.

## Write packet

Include only what the user needs to decide:

- target and intended change;
- observable output;
- verification;
- external effects and credentials, if any;
- rollback;
- conflicts with existing project conventions.

The user's request is the source of scope. Prefer the smallest working change, reuse existing code, and reject adjacent automation. Read [references/write-contract.md](references/write-contract.md) only when the write is non-trivial or outside the project.

After approval, execute autonomously until every required item passes or a real user-only/external blocker remains.
