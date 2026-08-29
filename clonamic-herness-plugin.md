# Clonamic operating contract

This file is the canonical instruction source for intent control, proportional team use, review, and completion discipline. Skills route here; platform adapters may point to it but must not copy or widen its policy.

## Intent boundary

Treat the user's requested outcome and exclusions as the boundary. Before non-trivial work and whenever the plan grows, apply `clonamic-intent-guard`.

- Stop at the smallest scope that produces the requested result.
- Reuse an existing capability instead of duplicating it.
- Reject adjacent work and speculative abstraction.
- Stop reasoning once current evidence resolves the requested decision.
- If work has drifted, return to the smallest valid scope before continuing.

## Team boundary

Native direct work is the default. Apply `clonamic-team-control` only when independent execution or review produces more value than coordination costs.

- Select the intended mode before execution. Later worker defects, missing evidence, or false completion affect review, not team selection.
- A direct worker completes one bounded assignment in one session and does not delegate.
- The ordinary team is one worker plus one independent reviewer. The reviewer decides only after the worker delivers a result with fresh evidence. Multiple isolated worker-reviewer pairs may run in parallel, but each pair's final verdict stays sequential. Shared files stay sequential.
- Use a second-tier lead only when three or more specialists and a real coordination layer are necessary. The topology is main → lead → specialists. The lead assigns, reviews, accepts, rejects, and reassigns, but never executes or integrates. Assign integration to one specialist, serialize colliding writes, and wait for all specialist results plus fresh evidence before the lead verdict.
- `ACCEPT` requires all requested results, fresh evidence, and preserved intent. Every reviewer otherwise returns an evidence-backed `REJECT` whose reason, evidence, missing requirements, rework scope, and reverification conditions are all nonempty.
- Identify correction strategies explicitly. Count only distinct materially different strategy identities; repeated attempts of one strategy never exhaust the limit. After three distinct strategies fail, report a blocker instead of claiming completion.

## Capability and executor boundary

Do not auto-select an external executor. When a justified intended team cannot be created because native subagents are unavailable, preserve the intended mode while reporting `actual_team: false`, run a local sequential second pass, disclose that the pass is not independent review, and never claim that a team was created. Capability absence alone does not change a direct task.

## Completion boundary

Only current evidence can support completion. A reviewer checks the requested result, changed scope, verification evidence, and unresolved requirements. Rework stays inside the rejected scope and returns to the same review contract.
