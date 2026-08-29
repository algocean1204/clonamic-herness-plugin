# Contributing

Small fixes may go straight to a pull request. Open an issue before changing a public contract, moving responsibility between packages, or adding a child package.

## Choose the owner first

The core owns routing, write approval, completion, reports, and market selection. Optional packages own domain behavior. Platform adapters only translate discovery and registration formats.

Do not copy policy into an adapter or neighboring package. Do not add automatic executor selection, implicit memory, telemetry, credentials, provider sessions, model IDs, private paths, or source-provenance banners.

## Split gate

Add a child package only when all five conditions hold:

1. It has an independent trigger.
2. It has one public responsibility with a closed input/output contract.
3. It has independent tests and failure behavior.
4. Independent installation and removal are useful.
5. The split creates no policy duplication or dependency cycle.

Keep the behavior in its current owner when one condition fails. A helper or convenience wrapper is not a package.

## Required package shape

Every Agent Plugins 1.0.0 package needs:

```text
plugin.json
LICENSE
skills/<matching-id>/SKILL.md
tests or a package-local deterministic verification command
```

The outer directory, manifest `name`, and canonical skill ID must match. Optional scripts, references, and assets stay inside the owning skill unless the runtime has a real package-level reason to place them elsewhere.

Generated platform manifests and marketplace files are not hand-edited. Change the canonical manifest or catalog, regenerate, then verify zero drift.

## Behavioral changes

Write the smallest test that fails for the intended reason, apply the change, and rerun the package-local suite. A behavior-preserving file move may reuse existing tests, but path and package-boundary assertions must cover the new layout.

Core checks:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --all-targets
python3 scripts/validate-public.py
```

Child checks run from the child root. Most Python children use:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

The PPT package keeps its engine tests under `skills/clonamic-ppt/tests/` and requires its declared Node dependency. Run the package's preserved test entry point after installing dependencies.

## Pull request checklist

- Responsibility stayed with one owner.
- Root and child manifests remain closed and parseable.
- Skill names match package IDs.
- No model, credential, session, user path, or telemetry default was added.
- Explicit state paths and rollback behavior are tested.
- Generated adapters match canonical inputs.
- Public docs distinguish repository checks, live host measurements, and fallbacks.
- Changelog and compatibility notes describe user-visible changes without claiming unrun validation.
