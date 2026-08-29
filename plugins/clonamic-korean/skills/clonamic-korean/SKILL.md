---
name: clonamic-korean
description: Review or conservatively edit Korean prose documents for translationese, empty abstraction, rhythm, structure, register, and form while preserving meaning. Do not use for ordinary chat, work reports, code, spreadsheets, slides, or email.
---

# Korean Document Clarity

Use this skill directly on a Korean prose document. It does not delegate work or choose an external runtime.

Before reading a file whose surface is uncertain, run `python3 scripts/scope.py --kind <kind> <path>`. Stop when it returns `applicable=false`. For inline text, classify the surface first; only `document` is supported.

## Review or edit

1. Read [references/preservation.md](references/preservation.md), then [references/korean-patterns.md](references/korean-patterns.md).
2. Preserve the author's facts, numbers, dates, names, quotations, links, negation, modality, and register.
3. For review, identify the smallest relevant rule and explain the concrete effect on the sentence.
4. For editing, make the smallest change that removes the problem. Do not invent an actor, reason, example, metric, source, or personal experience.
5. Return the requested review or revised prose directly. File application and user-facing workflow state remain with the host.

Do not edit code fences, commands, paths, formulas, table cells, or machine-generated lines embedded in a prose document. Do not handle approval, task completion, or work-report formatting.
