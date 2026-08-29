---
name: clonamic-router
description: Route an active Clonamic request to its smallest applicable intent, team, write, completion, report, or market path; keep read-only questions direct.
---

# Clonamic Router

Keep reads direct and route small writes to write control. For non-trivial mutation or team choice, read [../../clonamic-herness-plugin.md](../../clonamic-herness-plugin.md) once; load intent/team only as needed. Load write before mutation, completion before a changed-work claim, report after its verdict, and market only for optional selection.

Apply [references/prompt-envelope.json](references/prompt-envelope.json). Preserve the body; host metadata derives source, while automation needs a persisted claim. Before optional invocation resolve explicit config and require `effective: true`; disabling never installs, authorizes, or widens scope. `["자동화"]` is display-only.
