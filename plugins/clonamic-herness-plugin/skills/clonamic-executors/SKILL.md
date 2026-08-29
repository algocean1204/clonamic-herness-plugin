---
name: clonamic-executors
description: Route exactly one bounded unit to Grok, Codex, Claude, or Hermes after the user explicitly invokes `/grok`, `/gpt`, `/claude`, or `/hermes`. Never select, recommend, or invoke an external executor automatically.
---

# Clonamic Executors

External executors are user-controlled interfaces, not optimization targets.

## Contract

- Act only after the current user explicitly names one slash command.
- Send one bounded unit with its scope, exclusions, required outputs, and verification.
- A self-target executes locally instead of recursively invoking its own CLI.
- Never make a second hop, retry blindly, or substitute another external model.
- If the requested CLI is unavailable, state that fact and do not silently delegate elsewhere.
- The orchestrator verifies returned artifacts and owns the final report.

Read [references/executors.md](references/executors.md) for command resolution. Model names and efforts belong to the host platform's existing configuration; this plugin never hardcodes or rewrites them.
