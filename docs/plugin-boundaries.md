# Plugin boundaries

Every package has one public responsibility and one independent removal boundary.

| Package | Owns | Must not own |
|---|---|---|
| Core | Routing, intent guard, proportional team control, write approval, completion verdicts, work reports, market selection | Domain execution, child installation |
| Code | Proportional coding, patch discipline, modular design, gated native review | Approval, completion, external executors |
| Preprocessing | Input normalization, clarification packets, explicit queues | Scope authority, final execution |
| Writing | Publication writing, Korean clarity, deterministic cleanup | Work reports, code, slides, email |
| Design | Frontend, Figma, visual systems, browser QA, media art | Core coding policy |
| Data | Dataset and Hugging Face workflows | Core coding policy |
| Documents | HWPX and document-specialist workflows | General artifact runtimes |
| PPT | Presentation specification, rendering, QA | General writing policy, external execution |
| Memory | Explicit store, recall, forget, graph, ontology provenance, TTL, backup and restore | Automatic injection, implicit state, automatic prompt capture, raw prompt bodies in provenance, authority |
| Executor children | One bounded call to one named provider | Automatic selection, provider substitution, completion claims |

Cross-package wiring belongs to the core router or the generated adapter layer. A child never imports another child. Shared policy is not copied into adapters.

`clonamic.json` controls optional routing eligibility. Core has no toggle. Configuration never substitutes for installation, and an unavailable optional package stays visible with its failed installation, platform, or dependency dimension.

`clonamic-intent-guard` owns scope drift, unnecessary work, and over-engineering rejection. `clonamic-team-control` prospectively chooses native, paired, or `main → lead → specialists` execution; defects and evidence failures never create a team retroactively. A pair runs worker then reviewer, isolated pairs alone may run in parallel, and same-file work is serialized. A lead neither executes nor integrates; one specialist integrates, and review waits for every result plus fresh evidence. Without subagents, `actual_team` is false and a local sequential second pass is not independent review. `clonamic-completion-check` remains the final evidence gate. These are core responsibilities, not new child packages; the package count remains one core plus twelve children.

A new child must have an independent trigger, contract, test suite, failure mode, installation value, and removal value. Otherwise the behavior stays in its current owner.
