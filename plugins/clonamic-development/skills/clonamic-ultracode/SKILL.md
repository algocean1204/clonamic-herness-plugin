---
name: clonamic-ultracode
description: Run bounded native multi-agent review only when multiple viable options, material boundary impact, unresolved evidence, and high wrong-choice cost are all present. Remain unavailable when native isolated agents are absent.
---

# Clonamic Ultracode

This is a rare decision-review stage. The router may activate it only after all four eligibility gates pass and the host confirms native isolated-agent capability.

## Review contract

Read [references/decision-contract.json](references/decision-contract.json). Give every native reviewer the same bounded decision packet: question, live options, repository evidence, constraints, exclusions, and review budget.

1. Collect independent positions before sharing any other position.
2. Require each position to name its evidence, strongest objection, and falsifying condition.
3. Run one bounded rebuttal round only when positions differ materially.
4. Declare `consensus` only when every surviving position reaches the same decision for compatible reasons.
5. Preserve disagreement as `no_consensus`; never convert a majority into unanimity.

Return one `DecisionReview` with status, recommendation when unanimous, dissent, evidence trail, unresolved questions, and budget use. The stage is read-only and cannot mutate project or machine state.

## Failure

- `unavailable` — native isolated agents are not available. Do not invoke an external executor or simulate multiple agents in one voice.
- `aborted` — the time, turn, or resource budget ended. Preserve partial positions without a recommendation.
- `no_consensus` — bounded review ended with honest disagreement. Preserve dissent and leave the decision unresolved.

No recursive delegation, hidden model selection, automatic retry, authorization, completion verdict, or user-report formatting belongs here.
