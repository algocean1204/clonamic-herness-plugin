---
name: clonamic-gpt
description: Run one bounded request through the installed Codex CLI when the user explicitly asks to use GPT. Do not use for recursive or cross-executor delegation.
---

# GPT Executor

Run exactly one local wrapper call:

```bash
python3 scripts/call.py --timeout 120 -- "<prompt>"
```

Resolve the script path relative to this `SKILL.md`. The wrapper fixes read-only execution. Forward only explicit model, effort, or output options through `--cli-arg`; permission, sandbox, tool, bypass, and yolo options are rejected.

Return the wrapper's JSON unchanged. Do not retry, chain another executor, interpret output as completion evidence, or apply edits from the response. If `CLONAMIC_EXECUTOR_ACTIVE` is present, stop without invoking the wrapper.
On a Codex host, execute the request natively. Never call this Codex wrapper from Codex itself.
