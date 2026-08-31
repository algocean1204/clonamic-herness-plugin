---
name: clonamic-gpt
description: Run one bounded installed Codex CLI request only when explicitly asked for GPT; never use for recursive or cross-executor delegation.
---

# GPT Executor

Run one local wrapper call:

```bash
python3 "$CLONAMIC_GPT_ROOT/scripts/call.py" --timeout 120 -- "<prompt>"
```

Resolve `CLONAMIC_GPT_ROOT` to the host-provided directory containing this `SKILL.md`; never scan vendor homes or execute a project-relative `scripts/call.py`. The wrapper enforces read-only execution. Forward only explicit model, effort, or output options through `--cli-arg`; it rejects permission, sandbox, tool, bypass, and yolo flags.

Return its JSON unchanged. Do not retry, chain, treat output as completion evidence, or apply edits. Stop when `CLONAMIC_EXECUTOR_ACTIVE` is present.
On a Codex host, execute the request natively. Never call this Codex wrapper from Codex itself.
