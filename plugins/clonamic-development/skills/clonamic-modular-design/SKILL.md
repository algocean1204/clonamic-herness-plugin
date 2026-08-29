---
name: clonamic-modular-design
description: Design a new system or large refactor from repository evidence, with justified module boundaries, one public surface per module, explicit data contracts, and a migration order. Skip small edits and ordinary structure questions.
---

# Clonamic Modular Design

Treat modularization as a conclusion supported by evidence, not a default. Inventory the current system before designing a refactor.

## Boundary gates

- Split only when a candidate has at least two independent reasons to change and either independent test value, multiple real consumers, or a different change cadence.
- Keep function-sized behavior inside its owner. A helper is not a module.
- Commonize only after three real use sites, a stable contract, and domain independence are all present.
- Merge pass-through boundaries, boundaries always used together, and boundaries with effectively identical inputs and outputs.

Every surviving module has one public entry point plus its input and output types. Wiring belongs in one composition root; sibling modules do not construct or invoke one another. Configuration and environment values enter as declared inputs. Removing a module must require only deleting its folder and unwiring the root.

## Result

Read [references/module-contract.json](references/module-contract.json). Produce one `DesignResult` with:

- current-state evidence and scale verdict;
- a straight main pipeline;
- field-level input and output contracts;
- declared failure behavior per module;
- dependency and removal notes;
- a decision log covering every split, merge, commonization, and rejected abstraction;
- a strangler-style migration order with a cutover check per step for refactors.

When the user requested a persistent design artifact and its path is inside `approved_scope`, write exactly one `DESIGN.md`. Otherwise return the same design in chat without creating files.

## Failure

Return `blocked_missing_evidence` when the current system cannot be inspected well enough to justify boundaries. Return `invalid_contract` when an output cannot feed its declared consumer, a cycle remains, failure behavior is unspecified, or a public surface is ambiguous. Never fill evidence gaps with assumptions.

This skill owns design structure only. It does not authorize writes, execute patches, decide completion, or shape the user-facing report.
