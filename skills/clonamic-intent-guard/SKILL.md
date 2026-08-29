---
name: clonamic-intent-guard
description: Reject scope drift, adjacent work, duplication, speculative abstraction, and reasoning beyond sufficient evidence before non-trivial execution.
---

# Clonamic Intent Guard

Read [../../clonamic-herness-plugin.md](../../clonamic-herness-plugin.md), apply [references/intent-contract.json](references/intent-contract.json), and return one `IntentVerdict`. A rejection removes excess work and supplies the smallest valid scope plus bounded rework.

For session display state, apply [references/session-contract.json](references/session-contract.json). Internal prompts never replace Last User Prompt. This skill is read-only: it grants no write, delegation, installation, or completion authority.
