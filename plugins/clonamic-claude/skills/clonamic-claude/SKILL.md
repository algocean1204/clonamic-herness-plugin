---
name: clonamic-claude
description: Run one bounded installed Claude CLI request only when explicitly asked; never use for recursive or cross-executor delegation.
---

# Claude Executor

Run one local wrapper call:

```bash
python3 scripts/call.py --timeout 120 -- "<prompt>"
```

Resolve the script from this skill. It enforces read-only, no-tools execution. Forward only explicit model, effort, or output options through `--cli-arg`; it rejects permission, sandbox, tool, bypass, and yolo flags.

Return its JSON unchanged. Do not retry, chain, treat output as completion evidence, or apply edits. Stop when `CLONAMIC_EXECUTOR_ACTIVE` is present.
On a Claude host, execute the request natively. Never call this Claude wrapper from Claude itself.
