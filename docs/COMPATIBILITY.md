# Compatibility

Compatibility claims use three labels:

- **Repository-checked:** local schemas, files, deterministic behavior, or generated-output consistency are covered by repository checks.
- **Host-measured:** the package was installed and exercised on a named host release with recorded evidence.
- **Fallback:** portable skill behavior remains available, but the host-specific structural feature is not asserted.

## Platform matrix

| Surface | Canonical package | Repository-checked contract | Host-measured claim | Declared fallback |
|---|---|---|---|---|
| Agent Plugins 1.0.0 | Root `plugin.json`; each child `plugins/*/plugin.json` | Closed manifest and package-local contract | Depends on the client implementation | Load the matching skill directory directly when supported |
| Codex | Generated Codex marketplace and manifest outputs | Artifact shape and core contracts | No blanket live-install claim | Model-side skill contract when a structural hook is unavailable |
| Claude Code | Generated Claude marketplace and plugin outputs | Artifact shape and core contracts | No blanket live-install claim | Skills remain usable without claiming hook enforcement |
| Grok Build | Generated Grok marketplace and plugin outputs | Artifact shape only unless a release record says otherwise | No Grok validation success is claimed | Skills remain usable; missing commands or hooks are reported unavailable |
| Hermes | Generated registration output | Registration and package contracts can be checked locally | No blanket live-install claim | Direct skill loading or explicit CLI use, without claiming hook enforcement |

Generated files are compatibility outputs. Their presence does not prove that a host installed, enabled, or executed them.

## Core and child installation

The root package is the portable core. Nine child packages are independent roots. `clonamic-market` can select a matching child from `catalog/plugins.json`, but Agent Plugins 1.0.0 does not define portable cross-plugin installation. The host or user installs and enables the selected child.

Removing one child does not remove the core or another child. Missing children return unavailable; the core does not substitute a neighboring capability.

## Structural core

The `clonamic` binary supplies deterministic approval, completion, and router install/rollback operations. Skills can preserve the behavioral contract without the binary, but that is a model-side fallback. Documentation and reports must say so when structural enforcement matters.

## External executors

`clonamic-grok`, `clonamic-gpt`, `clonamic-claude`, and `clonamic-hermes` call only the named installed CLI. They use provider defaults plus explicit user options. They do not choose a model ID, read provider sessions, access memory, retry, or switch executors.

CLI availability and authentication are host conditions. Repository tests can use local fakes to verify argv, timeout, process cleanup, recursion blocking, redaction, and JSON output without making a provider request.

## Known host differences

- Host progress messages remain host output. Clonamic does not patch system prompts to hide them.
- Hook, command, and marketplace semantics vary by host release.
- Password, OAuth, biometric, and operating-system prompts remain platform actions.
- Unsupported hooks are never reported as active.
- A marketplace entry is inventory or selection metadata, not proof of installation.
