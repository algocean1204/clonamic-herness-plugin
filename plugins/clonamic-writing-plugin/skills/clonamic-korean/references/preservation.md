# Preservation

This skill changes Korean prose only. It is not applicable when the primary surface is ordinary chat, a work report, source code, a spreadsheet, slides, or email.

Keep these spans exact unless the user explicitly supplied a replacement:

- numbers, dates, money, ratios, units, versions, and identifiers
- person, organization, product, place, law, paper, and project names
- direct quotations, citations, URLs, DOI values, and link targets
- negation, uncertainty, permission, obligation, comparison, and causal direction
- code fences, commands, paths, API names, placeholders, formulas, logs, and machine-generated lines
- table and CSV cell values

Do not add facts, actors, reasons, examples, customers, metrics, quotations, or lived experience. If a clear rewrite needs missing information, flag the gap instead of filling it.

Before returning an edit, compare the original and revision for every protected span. A lost or changed protected span invalidates the revision.
