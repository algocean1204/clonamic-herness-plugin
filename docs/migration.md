# Migration and rollback

## Migration

1. Preserve the existing installation and record hashes for router files that may change.
2. Validate the core and every selected child as separate Agent Plugins roots.
3. Generate adapters and inspect the diff. Do not edit generated files by hand.
4. Test discovery in an isolated host home before changing an active configuration.
5. Install the core first. Install a child only after the user selects its capability.
6. Compare direct reads, a small write without team activation, intent-drift rejection, a justified worker/verifier run, reviewer rejection and rework, one approved correction loop, completion rejection, and uninstall behavior.
7. Remove superseded rules only after equivalent behavior is measured.

For Cursor, run `install-cursor.py install` after the isolated staging check.
The installer treats `clonamic.json` plus each `--config` overlay as an ordered
selection layer. Run `doctor` after reloading Cursor. Do not copy rules into
project repositories or edit account User Rules for this integration.

## v1 consolidation decisions

Version 1.0.0 keeps portable, explicit, bounded behavior and does not recreate every historical host runtime.

- Korean document preservation, terminology, links, facts, and consistency checks are retained.
- Design source commits, digests, licenses, and bundled-runtime hashes are retained.
- PPT uses the validated direct runtime; legacy dispatchers, fixed model selectors, previews, and draft material are retired.
- Memory stays explicit. Automatic prompt injection, retention scoring, cold archives, soft forget/unforget, and background pruning are retired.
- Preprocessing keeps normalization, clarification, crash-safe queueing, and explicit bounded loops. Automatic compression, browser automation, local serving, and resource daemons are retired.
- Supercoder and Ultracode use the native bounded contracts. Historical external-model fan-out, private journals, resume loops, and recursive delegation are retired.
- External executor plugins remain one bounded named call. Historical write-capable, resumable, completion-marker, and session-GC wrappers are retired.
- Owner configuration, model registry, backups, and machine trust-root hooks remain private infrastructure and are not copied into the public package.

Retired source history is recoverable from verified private archives. Retirement is deliberate and must not be reported as byte-for-byte parity.

## Rollback

Remove children independently, disable their adapter entries, and uninstall the core router last. The router block contains one reference to the canonical root guidance, not a policy copy. `clonamic uninstall-router` restores its recorded pre-image only when unrelated user edits can be preserved.

Cursor uses `install-cursor.py uninstall`. It first verifies every managed
package and global-rule hash, removes only installer-owned content, and
restores any same-name pre-install content. Claude-provided packages are only
referenced in state and are never removed. A modified managed asset blocks
removal so user edits are not discarded. A failed install or update restores
the full transaction snapshot automatically.

The historical `v0.1.0` and stable `v1.0.0` tags are immutable. Reverting a published change uses a normal Git revert and push; no forced history or tag rewrite is required.
