# Migration and rollback

## Migration

1. Preserve the existing installation and record hashes for router files that may change.
2. Validate the core and every selected child as separate Agent Plugins roots.
3. Generate adapters and inspect the diff. Do not edit generated files by hand.
4. Test discovery in an isolated host home before changing an active configuration.
5. Install the core first. Install a child only after the user selects its capability.
6. Compare direct reads, a small write without team activation, intent-drift rejection, a justified worker/verifier run, reviewer rejection and rework, one approved correction loop, completion rejection, and uninstall behavior.
7. Remove superseded rules only after equivalent behavior is measured.

## Rollback

Remove children independently, disable their adapter entries, and uninstall the core router last. The router block contains one reference to the canonical root guidance, not a policy copy. `clonamic uninstall-router` restores its recorded pre-image only when unrelated user edits can be preserved.

Tagged release `v0.1.0` remains the pre-marketplace baseline, and `0.2.0` is the prior main-branch version and commit. Reverting a published migration uses a normal Git revert and push; no forced history rewrite is required.
