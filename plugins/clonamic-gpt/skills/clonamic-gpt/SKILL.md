---
name: clonamic-gpt
description: Run one bounded installed Codex CLI request only when explicitly asked for GPT; never use for recursive or cross-executor delegation.
---

# GPT Executor

Run one local wrapper call:

```bash
python3 scripts/call.py --timeout 120 -- "<prompt>"
```

Resolve the script from this skill. It enforces read-only execution. Forward only explicit model, effort, or output options through `--cli-arg`; it rejects permission, sandbox, tool, bypass, and yolo flags.

Return its JSON unchanged. Do not retry, chain, treat output as completion evidence, or apply edits. Stop when `CLONAMIC_EXECUTOR_ACTIVE` is present.
On a Codex host, execute the request natively. Never call this Codex wrapper from Codex itself.
