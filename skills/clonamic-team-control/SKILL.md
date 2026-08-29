---
name: clonamic-team-control
description: Choose native direct work, a worker-reviewer pair, or a necessary second-tier lead with specialist workers. Use when non-trivial work may benefit from independent execution or verification; do not activate a team from size, repetition, or importance alone.
---

# Clonamic Team Control

Read the canonical instructions at [../../clonamic-herness-plugin.md](../../clonamic-herness-plugin.md), then apply [references/team-contract.json](references/team-contract.json).

- Select the intended mode prospectively, before execution. Keep `native` unless expected team benefit exceeds coordination cost. Worker defects, missing evidence, and false completion are review outcomes, never reasons to promote the mode.
- Use `paired` for one direct worker and one independent reviewer. The reviewer returns a verdict only after the worker result and fresh evidence arrive. Multiple isolated worker-reviewer pairs may run in parallel; each pair's verdict remains sequential. Colliding files stay sequential.
- Use `lead_workers` only when the contract's specialist count and second-tier necessity gates both pass. The topology is main → lead → specialists. The lead assigns and reviews but never executes or integrates; one specialist owns integration. Serialize colliding writes and wait for every specialist result plus fresh evidence before the lead verdict.
- Direct workers use one session and never delegate.
- Do not auto-select external executors. If the intended team cannot be created because native subagents are unavailable, preserve the intended mode but set `actual_team: false` and perform a local sequential second pass without claiming independent review. Capability absence alone never changes a direct task.

For each delivered result, apply [references/review-contract.json](references/review-contract.json). `ACCEPT` requires every result, fresh evidence, and preserved intent. Every `REJECT` field must be nonempty. Keep rework bounded to the rejected requirements, count only distinct strategy identities, and stop with a blocker after three materially different strategies are exhausted.
