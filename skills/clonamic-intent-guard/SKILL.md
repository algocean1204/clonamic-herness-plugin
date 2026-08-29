---
name: clonamic-intent-guard
description: Detect scope drift, adjacent work, duplicate implementation, speculative abstraction, or reasoning beyond sufficient evidence. Use before non-trivial execution and when a plan or implementation appears wider than the user's request; skip routine direct answers and exact tiny changes.
---

# Clonamic Intent Guard

Read the canonical instructions at [../../clonamic-herness-plugin.md](../../clonamic-herness-plugin.md), then apply [references/intent-contract.json](references/intent-contract.json) to the current request, plan, and evidence.

Return one `IntentVerdict`. `pass` keeps the current scope. `reject` identifies the evidence-backed reason, removes out-of-scope or unnecessary work, and supplies the smallest valid scope plus bounded rework. Re-evaluate only the corrected scope.

This skill is read-only. It does not authorize writes, select executors, create a team, or decide final completion.
