# Philosophy

Clonamic exists to remove friction from AI-assisted work. A control that slows ordinary reading, repeats a decision, or silently changes the user's machine is a defect.

## Trust the model where judgment helps

The model decides how much to inspect, which implementation fits the project, whether a request is ambiguous, and what evidence proves the result. Static rules should not prescribe every file, command, or reasoning step.

Deterministic code is reserved for boundaries where a wrong guess has a concrete cost: persistent writes, destructive commands, secret exposure, external side effects, rollback, and completion evidence.

## Reads are free; writes are deliberate

Questions, opinions, explanations, status checks, review, and inspection do not need a specification. A persistent write receives the smallest useful packet. Clear writes need one development packet. A separate work packet exists only when the user's intent must be locked before analysis.

Approval is a decision correlation mechanism. It is not a password. Formatting differences do not invalidate the decision, and one approved packet covers the complete test/fix/apply loop.

## Broad capability, narrow activation

The plugin ships several capabilities, but it loads only the module needed for the current stage. The always-on router is three lines. Domain procedures, external executors, architecture design, and heavy verification stay dormant until selected.

## Explicit executor control

The current agent works by default. Grok, Codex, Claude, and Hermes are available through explicit slash commands. The harness never chooses another model because a task is large, repetitive, or expensive.

## Completion is observed

Before reporting completion, the agent compares the user's required items with current artifacts, fresh tests, applied state, and remote state when relevant. Missing work continues. A repeated real blocker is reported as a blocker, not hidden behind a completion sentence.

## The user's environment is not ours

Installation is additive and reversible. Existing model settings, plugins, MCP servers, credentials, memory, sessions, and project files stay untouched. Removal restores the managed router change and leaves unrelated user edits in place.

## Reports carry decisions, not process narration

The first line states the result. Failures and unverified items appear first. Evidence uses commands, counts, hashes, or file locations. Tool order and repeated conclusions are omitted.
