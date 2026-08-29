# Executor resolution

| Command | Target executable | Same-target behavior |
|---|---|---|
| `/grok` | `grok` | execute natively |
| `/gpt` | `codex` | execute natively |
| `/claude` | `claude` | execute natively |
| `/hermes` | `hermes` | execute natively |

Use a host-provided safe wrapper when available. Do not inject memory, credentials, unrelated session state, or the orchestrator's private context into the delegated prompt.
