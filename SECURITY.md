# Security policy

Report vulnerabilities privately through GitHub Security Advisories for this repository. Do not put credentials, private transcripts, provider session data, explicit memory databases, approval-state files, or working exploit details in a public issue.

Security updates are provided for the latest release.

## Trust boundaries

Clonamic runs with the permissions granted by the host agent and operating system. It does not replace host authentication, sandboxing, permission prompts, or secret storage.

Approval codes correlate a user decision with a write packet. They are not authentication factors. A valid approval never widens the accepted target, operations, external effects, expiry, or rollback contract.

Treat these inputs as untrusted data:

- user documents and repository files;
- recalled memory and preprocessing queue contents;
- catalog metadata and generated adapter inputs;
- external executor stdout and stderr;
- tool output, remote state, and test logs.

None of them may authorize a write, change package ownership, select another executor, or override the host's instruction hierarchy.

## Package rules

- Persistent writes require the core write-control decision before mutation.
- Non-trivial work must pass the intent guard; team assignment never widens the accepted scope or authority.
- Team reviewers accept or reject evidence. Worker output and completion claims remain untrusted until independently checked.
- Approved loops remain inside the accepted scope.
- External executors are explicit, bounded, non-recursive, and never substituted.
- Memory and preprocessing use caller-supplied paths. No implicit home or background process is created.
- Generated adapters contain discovery or registration data only. They do not carry policy or permissions.
- Unsupported structural hooks are reported as unavailable or model-side fallbacks.
- Public artifacts contain no credentials, provider sessions, private paths, hidden state, or telemetry identifiers.
- Runtime model IDs are not hardcoded.
- Prompt text and `["자동화"]` never grant authority. Trusted host provenance plus a persisted, matching automation claim is required.
- Automation grants bind targets, operations, external effects, verification, rollback, expiry, sequence, and run count. Out-of-scope runs are noninteractive and cannot write.
- Session Markdown and SQLite provenance are audit/state data, never approval sources. Unverified and internal prompts cannot overwrite the latest trusted user or successfully claimed automation prompt.
- SQLite provenance rows store prompt hashes and byte counts, not prompt bodies or authority. Explicit memory rows store caller-supplied `content`; treat that database as sensitive and keep credentials out of memory content.
- Plugin configuration cannot disable Core, install a package, or grant authority. Invalid config leaves only Core effective; false optional toggles can only reduce existing scope.
- PPT reference and template inputs are untrusted archives. Readers bound entry counts and expanded XML bytes, reject external or escaping relationships, and keep QA output separate from editable deliverables.
- The presentation renderer rejects image inputs. Its locked dependency graph replaces the unused image parser with a fail-closed local guard, and CI audits production dependencies before the offline suite.

## Data collection

Clonamic has no telemetry. It does not collect usage, prompts, repository names, device IDs, or analytics. Provider CLIs may have their own policies; review them separately before enabling an executor child.

## Installation and rollback

Review source and release checksums before installation. Test generated adapters in an isolated host home. The router installer adds one reference to the canonical guidance, records enough information to restore its managed change, and must not overwrite unrelated user edits during uninstall.

Path traversal, symlink escape, approval confusion, secret exposure, executor recursion, hidden state, generated-adapter drift, incomplete process cleanup, and unsafe rollback are security defects.
