# Compatibility

Compatibility claims use three labels:

- **Repository-checked:** local schemas, files, deterministic behavior, or generated-output consistency are covered by repository checks.
- **Host-measured:** the package was installed and exercised on a named host release with recorded evidence.
- **Fallback:** portable skill behavior remains available, but the host-specific structural feature is not asserted.

## Platform matrix

| Surface | Canonical package | Repository-checked contract | Host-measured claim | Declared fallback |
|---|---|---|---|---|
| Agent Plugins 1.0.0 | Root `plugin.json`; immediate `skills/*/SKILL.md`; optional root `mcp.json`; each child `plugins/*/plugin.json` as a separate root | Closed manifest and package-local contract | Depends on the client implementation | Load the matching skill directory directly when supported |
| Codex | Generated Codex marketplace and manifest outputs | Artifact shape and core contracts | No blanket live-install claim | Model-side skill contract when a structural hook is unavailable |
| Claude Code | Generated Claude marketplace and plugin outputs | Artifact shape and core contracts | No blanket live-install claim | Skills remain usable without claiming hook enforcement |
| Grok Build | Generated Grok marketplace and plugin outputs | Artifact shape only unless a release record says otherwise | No Grok validation success is claimed | Skills remain usable; missing commands or hooks are reported unavailable |
| Hermes | Generated registration output | Registration and package contracts can be checked locally | Remote monorepo install was blocked by the community-plugin scanner; no files installed | Direct review and skill loading only when the host permits it; never bypass the scanner |

Generated files are compatibility outputs. Their presence does not prove that a host installed, enabled, or executed them.

Agent Plugins 1.0.0 does not automatically load arbitrary root Markdown, recursively discover nested skills or plugin roots, define marketplaces, or define team/subagent execution. `clonamic-herness-plugin.md` is therefore reached through `clonamic-router` for non-trivial mutation or team decisions, or through the optional reversible router installer. See the [Agent Plugins 1.0.0 specification](https://agent-plugins.org/specification).

## Core and child installation

The root package is the portable core. Twelve child packages are independent roots. `clonamic-market` can select a matching child from `catalog/plugins.json`, but Agent Plugins 1.0.0 does not define portable cross-plugin installation. The host or user installs and enables the selected child.

Removing one child does not remove the core or another child. Missing children return unavailable; the core does not substitute a neighboring capability.

`clonamic.json` is host-neutral routing input for an integration that calls the native resolver. The resolver accepts explicit shipped, user, and project paths plus an explicit installed-package set. A vendor-neutral or special-purpose client uses platform ID `agent-plugins`. Core remains effective and has no toggle. Optional `false` values prevent invocation only through that integration; optional `true` values do not install or load code. Stock hosts that ignore the resolver and hosts that need process-level unloading must use their own disable or uninstall operation.

## Structural core

The `clonamic` binary supplies deterministic approval, completion, and router install/rollback operations. The installed router block references the canonical root guidance once and does not duplicate it. Skills can preserve the behavioral contract without the binary, but that is a model-side fallback. Documentation and reports must say so when structural enforcement matters.

Team topology is selected prospectively; worker defects, missing evidence, and false completion do not create a team after execution. A pair always runs worker then reviewer, parallelism is only across isolated pairs, and same-file work is serialized. In `main → lead → specialists`, the lead neither executes nor integrates, one specialist owns integration, and no verdict precedes all results plus fresh evidence. Team control depends on native isolated-agent support: without it, `actual_team` is false and a disclosed local sequential second pass is not independent review.

Prompt provenance and automation authority require a host adapter that can attest whether a prompt came from an interactive user, scheduler, or internal worker. Without attestation, authority is `none`; a textual automation label never upgrades it. In-scope claimed automation is noninteractive, while credentials and operating-system prompts remain platform actions.

The optional memory child uses Python's standard `sqlite3` at a caller-supplied path. It creates and migrates state lazily and does not require a server, Docker, vector extension, uv, or a virtual environment. FTS5 is opportunistic; the scan fallback preserves results when FTS5 is unavailable.

The PPT child produces structural and SVG QA artifacts after input validation passes; blocked input produces `qa_report.json` without render artifacts. Raster QA depends on an available office renderer and image tooling. Automatic LibreOffice use is disabled on macOS unless `CLONAMIC_ALLOW_MACOS_SOFFICE=1`; unavailable raster QA is reported as unavailable, not passed. Host-side PowerPoint fidelity still requires visual inspection in the target application.

## External executors

`clonamic-grok`, `clonamic-gpt`, `clonamic-claude`, and `clonamic-hermes` call only the named installed CLI. They use provider defaults plus explicit user options. They do not choose a model ID, read provider sessions, access memory, retry, or switch executors.

CLI availability and authentication are host conditions. Repository tests can use local fakes to verify argv, timeout, process cleanup, recursion blocking, redaction, and JSON output without making a provider request.

## Known host differences

- Host progress messages remain host output. Clonamic does not patch system prompts to hide them.
- Hook, command, and marketplace semantics vary by host release.
- Password, OAuth, biometric, and operating-system prompts remain platform actions.
- Unsupported hooks are never reported as active.
- A marketplace entry is inventory or selection metadata, not proof of installation.
- Hermes currently scans the full repository rather than only the root package surface, so optional executable and bundled-library assets block remote monorepo installation. Generated metadata does not override that host verdict.
