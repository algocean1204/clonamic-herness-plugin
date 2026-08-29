---
name: clonamic-router
description: Route a request through Clonamic's direct-response, intent, team, write-control, completion, reporting, or optional-plugin path. Use when Clonamic is active for the current task; do not use as a substitute for a domain skill.
---

# Clonamic Router

Choose one narrow route for the current stage:

- Questions, explanations, opinions, inspection, review, and other read-only requests stay direct. Do not load the root guidance, create a specification, or add an approval gate unless a real team decision is needed.
- Small, precise persistent mutations load `clonamic-write-control` directly. Do not load the root guidance or create a team.
- For a non-trivial mutation or a real team decision, read the plugin-root `clonamic-herness-plugin.md` once. Then load `clonamic-intent-guard` to bound the work and `clonamic-team-control` only when its team decision is needed.
- Before any persistent mutation, load `clonamic-write-control`.
- Before claiming non-trivial changed work is complete, load `clonamic-completion-check`.
- After a completion or blocker verdict, load `clonamic-report` only when a work report is needed.
- When the user asks which optional Clonamic plugin fits a capability, load `clonamic-market`.

Load only the selected route. Do not reread or copy the root guidance into a platform adapter. Optional plugins are never installed, enabled, or invoked merely because they appear in the catalog.
