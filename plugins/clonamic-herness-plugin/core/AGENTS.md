# Clonamic routing root

- Questions, explanations, opinions, inspection, review, and every other read-only request are direct: do not create a specification or approval gate.
- Before a persistent write, load `clonamic-write-control`; before claiming completion, load `clonamic-completion-check`; shape the final report with `clonamic-report`.
- External AI executors are user-controlled only. Load `clonamic-executors` after an explicit `/grok`, `/gpt`, `/claude`, or `/hermes` command; never choose one automatically.
