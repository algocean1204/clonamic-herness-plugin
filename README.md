# Clonamic Agent Plugins

[![CI](https://github.com/algocean1204/clonamic-herness-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/algocean1204/clonamic-herness-plugin/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Clonamic keeps read-only and small precise work on the native path, bounds non-trivial work against user intent, creates a worker-and-verifier team only when its value exceeds its coordination cost, puts one proportional gate in front of persistent writes, and verifies required outcomes before reporting completion. The repository ships one required Core Harness package and nine optional Agent Plugins 1.0.0 capability packages.

한국어 요약: 질문과 읽기는 바로 처리합니다. 실제 쓰기는 범위에 맞는 승인 한 번만 받고, 승인된 수정·검증 루프는 필요한 결과가 나올 때까지 자율적으로 이어갑니다. 완료 보고는 결과와 증거를 먼저 보여 주는 평면 목록입니다.

## Packages

| Package | Owns | Does not own |
|---|---|---|
| `clonamic-herness-plugin` | Routing, intent guard, proportional team control, write control, completion checks, outcome-first reports, market selection | Domain work, child installation |
| `clonamic-development` | Modular design, conservative patching, native gated Ultracode review | Approval, completion, external executors |
| `clonamic-preprocessing` | Input normalization, clarification packets, explicit queues and `loop_auto` | Scope inference, final execution |
| `clonamic-korean` | Korean prose-document clarity | Chat, work reports, code, spreadsheets, slides, email |
| `clonamic-ppt` | Editable presentation rendering and QA | General document editing, external execution |
| `clonamic-memory` | Explicit local store, recall, forget, link, and graph operations | Automatic context injection, hidden storage |
| `clonamic-grok` | One explicit bounded Grok CLI call | Automatic routing, retries, completion claims |
| `clonamic-gpt` | One explicit bounded Codex CLI call | Automatic routing, retries, completion claims |
| `clonamic-claude` | One explicit bounded Claude CLI call | Automatic routing, retries, completion claims |
| `clonamic-hermes` | One explicit bounded Hermes CLI call | Automatic routing, retries, completion claims |

Every child has its own root `plugin.json`, skill directory, MIT license, tests, and removal boundary. Core has no off switch in `clonamic.json`. In a host that calls the resolver, optional toggles control routing eligibility; they neither install a missing package nor unload a package from the host process.

## Operating contract

| Request | Route |
|---|---|
| Question, explanation, inspection, review, or status | Direct host response. No specification or approval. |
| Small precise mutation | Direct native execution with write control. No team or root-guidance load. |
| Non-trivial mutation or real team decision | Load the canonical root guidance once, bound intent, then choose native or team execution. |
| Clear persistent write | One compact development specification and one approval. |
| Materially ambiguous persistent write | Work specification to lock intent, then one development specification before mutation. |
| Approved inspect/fix/retest/apply/deploy/backup loop | Continue autonomously inside the approved scope. |
| Completion claim | Compare every required item with current artifacts and fresh evidence. |
| Team execution | Choose the topology before execution; then require delivered results and fresh evidence before a verdict. |
| Optional capability lookup | Market selects the narrowest matching package. Installation remains a platform action. |
| External executor | Only the executor explicitly named by the user. No substitution. |
| Trusted automation | Use its preapproved grant without conversational approval; scope drift returns noninteractive `needs_authorization`. |

Approval codes correlate a decision with its write packet. They are not passwords or authentication factors. Password, OAuth, biometric, operating-system, and platform prompts remain outside Clonamic.

Team selection is prospective. A later worker defect, missing evidence, or false completion rejects the result but never retroactively creates a team. Within each pair, the worker finishes before its reviewer starts; only two or more isolated pairs may run in parallel, and same-file work is serialized. A second tier is `main → lead → specialists`: the lead assigns and reviews but neither executes nor integrates, one assigned specialist owns integration, and the verdict waits for every specialist result plus fresh evidence. Without native subagents, `actual_team` remains false and the host may perform only a disclosed local sequential second pass, not independent review.

Prompt origin comes from trusted host metadata, not prompt text. `["자동화"]` is a visible compatibility label only. A trusted automation run must first claim a persisted grant bound to its automation, run, definition, scope, verification, rollback, expiry, and run limit. In-scope runs do not pause for chat approval. Internal prompts inherit only the intersection of the exact parent assignment and parent scope.

## Runtime flow

```mermaid
flowchart TB
    U[User request] --> R{Core router}
    R -->|Read-only| N[Native host path]
    R -->|Small persistent write| W[Write control]
    R -->|Non-trivial mutation or team decision| I[Intent guard]
    I --> T{Team control}
    T -->|Native is cheaper| W
    T -->|Independent verification pays| W
    W --> A[One proportional approval]
    A --> L{Selected mode}
    L -->|Native| X[Native worker]
    X --> C[Completion check]
    L -->|Pair| PW[Worker]
    PW --> V[Reviewer after result and fresh evidence]
    V -->|REJECT with evidence| PW
    V -->|ACCEPT| C
    L -->|Second tier| D[Lead assigns and reviews only]
    D --> S[Specialists; one integrates]
    S -->|All results and fresh evidence| D
    D -->|ACCEPT| C
    C -->|Required item unmet| B[Bounded rework in the same mode]
    B --> L
    C -->|Complete or blocked| P[Outcome-first flat report]
    R -->|Capability lookup| M[Market selector]
    F[clonamic.json layers] --> Q[Deterministic resolver]
    J[Installed package set] --> Q
    Q --> M
    M --> K[(Plugin catalog)]
    K -. selection only .-> O[Optional child package]
    U -. explicit executor request .-> E[Selected executor child]
```

## Install and selection

Install the core marketplace or package with the current host CLI:

```text
# Codex
codex plugin marketplace add algocean1204/clonamic-herness-plugin
codex plugin add clonamic-herness-plugin@clonamic

# Claude Code
claude plugin marketplace add algocean1204/clonamic-herness-plugin
claude plugin install clonamic-herness-plugin@clonamic

# Grok Build
grok plugin install algocean1204/clonamic-herness-plugin --trust

# Hermes
hermes plugins install algocean1204/clonamic-herness-plugin --enable
```

Review source before using `--trust` or `--enable`. Codex and Claude can install an optional child by its catalog name. Grok accepts a repository subdirectory selector such as `algocean1204/clonamic-herness-plugin#plugins/clonamic-development`. Hermes installs the portable root; child-package availability depends on the installed Hermes release and is not claimed without a host measurement.

Agent Plugins 1.0.0 clients load the repository root for the core package:

```text
plugin.json
skills/
native/
```

Agent Plugins 1.0.0 portably discovers only immediate `skills/*/SKILL.md` components and root `mcp.json`. It does not automatically load the root `clonamic-herness-plugin.md`, recursively discover the package roots under `plugins/`, or define marketplace installation and team/subagent behavior. The core router loads the canonical guidance only for non-trivial mutations or real team decisions; the optional router installer adds one reference to that file without copying its policy.

Optional packages are separate roots under `plugins/`:

```text
plugins/clonamic-development/
plugins/clonamic-preprocessing/
plugins/clonamic-korean/
plugins/clonamic-ppt/
plugins/clonamic-memory/
plugins/clonamic-grok/
plugins/clonamic-gpt/
plugins/clonamic-claude/
plugins/clonamic-hermes/
```

The root market can identify the package that matches a request. Agent Plugins 1.0.0 does not define portable child-plugin installation, so the host or user still installs and enables each selected child.

`clonamic.json` is the configuration input for hosts that integrate the Clonamic resolver. The shipped file has `schema_version: 1` and enables all nine optional packages. Callers pass the shipped default, user overlay, and project overlay as explicit paths. The resolver merges them in that order, so project values win. User and project files may contain only the toggles they change. An invalid present layer fails closed to Core-only operation.

The resolver reports `configured`, `installed`, `platform_supported`, `dependencies_ready`, `effective`, and `reason` for every package. An optional package becomes effective only when all four dimensions permit it. `enabled_but_unavailable` means the toggle is on but installation, platform support, or a dependency prevents use. A vendor-neutral or special-purpose host uses the `agent-plugins` platform identifier, keeps Core active, passes its installed-package set and configuration layers to `clonamic resolve-plugins`, then exposes only optional roots whose `effective` value is true.

Editing `clonamic.json` alone does not change a stock host that exposes child skills without calling the resolver. Host-native disable or uninstall remains the enforcement path there and the only way to unload package code. `clonamic.json` is a routing integration API, not a replacement for the host package manager.

Build the deterministic core CLI from the repository root:

```bash
cargo build --release --locked --bin clonamic
./target/release/clonamic doctor .
```

`resolve-plugins` uses explicit positional inputs so a host never searches the user's home directory:

```text
clonamic resolve-plugins <catalog.json> <plugin-root> <default.json|-> <user.json|-> <project.json|-> <platform> <installed.json>
```

`installed.json` is a closed object whose `installed` array contains the optional package names already available to that host:

```json
{
  "installed": ["clonamic-development", "clonamic-memory", "clonamic-ppt"]
}
```

A portable special-purpose host can resolve the shipped defaults like this:

```bash
./target/release/clonamic resolve-plugins \
  catalog/plugins.json . clonamic.json - - agent-plugins installed.json
```

The JSON output is the run manifest for that host. Load Core plus only rows with `effective: true`. Release builds use the binary names in `.github/workflows/release.yml`.

Platform manifests and adapter files are generated compatibility outputs. Do not edit `.agents/`, `.claude-plugin/`, `.grok-plugin/`, or generated adapter files by hand. Canonical behavior lives in the root and child `plugin.json` files, skills, native contracts, and catalog.

Structural router installation is optional and reversible:

```text
clonamic install-router <AGENTS.md> <install-state.json> <plugin-root>
clonamic uninstall-router <AGENTS.md> <install-state.json>
```

The installed block contains one reference to `<plugin-root>/clonamic-herness-plugin.md`. Uninstall restores the recorded pre-image while preserving unrelated edits made after installation.

Release binaries include adjacent `.sha256` files. Verify the checksum before adding `clonamic` to `PATH`.

## Privacy and control

Clonamic has no telemetry. It does not copy credentials, user profiles, provider sessions, browser state, model settings, private paths, or implicit memory into the package. Runtime model IDs are not hardcoded. Executor wrappers use the selected provider CLI's default configuration plus options the user explicitly supplied.

Memory and preprocessing state always use caller-supplied paths. Recalled text and executor output are untrusted data, not instructions. Generated adapters translate discovery formats; they do not contain policy.

Session Markdown stores one bounded view of the latest trusted user or successfully claimed automation prompt with its derived source and SHA-256. Unverified and internal prompts cannot replace it. SQLite remains optional and owned by `clonamic-memory`: it is created lazily at an explicit data path and needs no Docker, vector database, uv, or virtual environment. Provenance rows store hashes and byte counts rather than prompt bodies or authority. Explicit memory rows store the caller-supplied `content`, which may be sensitive and should use a protected path.

The PPT child measures reference-deck colors, fonts, geometry, and word density from bounded OOXML, extracts semantic template contracts, renders an editable PPTX, and writes a dependency-free SVG QA view for every slide. Template inspection is extraction-only; the blank-canvas renderer does not apply or preserve a supplied master. Third-party method sources and pinned MIT revisions are listed in [PPT third-party notices](plugins/clonamic-ppt/THIRD_PARTY_NOTICES.md). On macOS, automatic LibreOffice rendering is disabled unless `CLONAMIC_ALLOW_MACOS_SOFFICE=1`; unavailable raster rendering is reported explicitly and never substituted with an SVG visual-pass claim.

## Local verification

Core checks:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --all-targets
python3 scripts/validate-public.py
```

Each child also owns package-local tests. See [Contributing](CONTRIBUTING.md) for the split gate and child verification rules.

## Compatibility limits

Repository checks prove local contracts, manifest shape, deterministic code paths, and generated-file consistency. They do not prove that a particular host release installed, enabled, or enforced an adapter. Unsupported hooks use a declared model-side fallback. No live Grok validation success is claimed.

See [Compatibility](docs/COMPATIBILITY.md) for the measured-versus-fallback matrix.

## Documentation

- [Architecture](DESIGN.md)
- [Philosophy](docs/PHILOSOPHY.md)
- [Compatibility](docs/COMPATIBILITY.md)
- [Plugin boundaries](docs/plugin-boundaries.md)
- [Adapter generation](docs/adapters.md)
- [Migration and rollback](docs/migration.md)
- [Benchmark method](docs/BENCHMARKS.md)
- [Measured performance](docs/PERFORMANCE.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Status

Version 0.1.0 is an early public release. A release is ready only when the core, every included child, generated adapters, public-data scan, and rollback checks pass together.
