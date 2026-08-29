# Plugin boundaries

Every package has one public responsibility and one independent removal boundary.

| Package | Owns | Must not own |
|---|---|---|
| Core | Routing, write approval, completion verdicts, work reports, market selection | Domain execution, child installation |
| Development | Modular design, patch discipline, gated native review | Approval, completion, external executors |
| Preprocessing | Input normalization, clarification packets, explicit queues | Scope authority, final execution |
| Korean | Korean prose-document clarity | Chat, work reports, code, slides, email |
| PPT | Presentation specification, rendering, QA | General writing policy, external execution |
| Memory | Explicit store, recall, forget, graph | Automatic injection, implicit state |
| Executor children | One bounded call to one named provider | Automatic selection, provider substitution, completion claims |

Cross-package wiring belongs to the core router or the generated adapter layer. A child never imports another child. Shared policy is not copied into adapters.

A new child must have an independent trigger, contract, test suite, failure mode, installation value, and removal value. Otherwise the behavior stays in its current owner.
