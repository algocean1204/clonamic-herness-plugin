---
name: clonamic-development-router
description: Route software-development work between the native path, modular design, conservative patching, and bounded native multi-agent review. Use when a coding or architecture request needs a proportional development method; keep ordinary work native.
---

# Clonamic Development Router

Choose the smallest development stage that materially reduces risk. The native path is the default.

## Route

Read [references/activation-contract.json](references/activation-contract.json), then return one `DevelopmentRoute`:

```text
DevelopmentRoute {
  stages: list[native | modular-design | supercoder | ultracode],
  reasons: list[str],
  degraded: list[str],
  ultracode: not_eligible | active | unavailable
}
```

Apply stages in this order when more than one qualifies:

1. `modular-design` for a real architecture, new-system, or large-refactor decision.
2. `supercoder` for an already approved non-trivial code write with stale or ambiguous patch risk.
3. `ultracode` only when all four decision gates pass and the host exposes native isolated agents.

Task size, file count, repetition, or an importance label never activates Ultracode by itself. When its four gates pass but native isolated agents are unavailable, set `ultracode: unavailable`; do not substitute another execution path or simulate consensus.

Read [references/ownership-contract.json](references/ownership-contract.json) before handing work to a specialist. This plugin consumes `approved_scope` when a write is already authorized. It does not create authorization, decide completion, shape the user report, install components, or select external executors.

## Failure

Missing or contradictory routing evidence returns the native stage with the uncertainty recorded in `degraded`. Routing itself has no side effects.
