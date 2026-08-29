---
name: clonamic-router
description: Route a request through Clonamic's direct-response, write-control, completion, reporting, or optional-plugin path. Use when Clonamic is active for the current task; do not use as a substitute for a domain skill.
---

# Clonamic Router

Choose one narrow route for the current stage:

- Questions, explanations, opinions, inspection, review, and other read-only requests stay direct. Do not create a specification or approval gate.
- Before a persistent mutation, load `clonamic-write-control`.
- Before claiming non-trivial changed work is complete, load `clonamic-completion-check`.
- After a completion or blocker verdict, load `clonamic-report` only when a work report is needed.
- When the user asks which optional Clonamic plugin fits a capability, load `clonamic-market`.

Load only the selected route. Optional plugins are never installed, enabled, or invoked merely because they appear in the catalog.
