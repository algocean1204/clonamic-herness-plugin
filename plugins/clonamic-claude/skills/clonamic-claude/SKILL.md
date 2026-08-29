---
name: clonamic-claude
description: Run one bounded request through the installed Claude CLI when the user explicitly asks to use Claude. Do not use for recursive or cross-executor delegation.
---

# Claude Executor

Run exactly one local wrapper call:

```bash
python3 scripts/call.py --timeout 120 -- "<prompt>"
```

Resolve the script path relative to this `SKILL.md`. The wrapper fixes read-only, no-tools execution. Forward only explicit model, effort, or output options through `--cli-arg`; permission, sandbox, tool, bypass, and yolo options are rejected.

Return the wrapper's JSON unchanged. Do not retry, chain another executor, interpret output as completion evidence, or apply edits from the response. If `CLONAMIC_EXECUTOR_ACTIVE` is present, stop without invoking the wrapper.
On a Claude host, execute the request natively. Never call this Claude wrapper from Claude itself.
