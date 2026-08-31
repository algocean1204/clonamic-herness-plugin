use clonamic_core::approval::{
    ApprovalDecision, ApprovalRequest, Grant, approve as approve_in_set, issue as issue_in_set,
    normalize_approval,
};
use clonamic_core::automation::{
    AutomationGrant, AutomationRunRequest, CredentialPolicy, RunStatus, claim_run, initialize_grant,
};
use clonamic_core::completion::{CompletionItem, CompletionManifest, verify_completion};
use clonamic_core::installation::{InstallRequest, install_router, uninstall_router};
use clonamic_core::plugin_config::{
    ResolutionStatus, ResolvePaths, reduce_automation_scope, resolve_plugins,
};
use clonamic_core::provenance::{
    AutomationPrompt, DerivedAuthority, HostSource, PromptEnvelope, PromptSource, ScopeAuthority,
    authorize_automation, classify_prompt, parse_envelope, sha256_hex,
};
use clonamic_core::session::{SessionUpdate, update_session};
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Arc, Barrier};
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};
use tempfile::tempdir;

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_secs()
}

fn issue(path: &Path, request: ApprovalRequest) -> clonamic_core::Result<Grant> {
    issue_in_set(path.parent().expect("approval state parent"), path, request)
}

fn approve(
    path: &Path,
    session_id: &str,
    input: &str,
    now: u64,
) -> clonamic_core::Result<ApprovalDecision> {
    approve_in_set(
        path.parent().expect("approval state parent"),
        path,
        session_id,
        input,
        now,
    )
}

fn plugin_root_with_guidance(root: &Path) -> PathBuf {
    let plugin_root = root.join("plugin");
    fs::create_dir_all(&plugin_root).unwrap();
    fs::write(
        plugin_root.join("clonamic-herness-plugin.md"),
        b"guidance\n",
    )
    .unwrap();
    plugin_root
}

#[test]
fn approval_input_accepts_human_format_variants() {
    for input in [
        "승인:6F0FF3",
        "`승인:6F0FF3`",
        " 승인：6F0FF3 ",
        "승인 : 6f0ff3",
    ] {
        assert_eq!(normalize_approval(input).unwrap(), "6F0FF3");
    }
}

#[test]
fn approval_is_session_bound_idempotent_and_expiring() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("grant.json");
    let request = ApprovalRequest {
        session_id: "session-a".into(),
        scope_digest: "a".repeat(64),
        expires_at: now() + 60,
    };
    let grant = issue(&state, request).unwrap();

    assert_eq!(
        approve(&state, "session-b", &format!("승인:{}", grant.code), now()).unwrap(),
        ApprovalDecision::SessionMismatch
    );
    assert_eq!(
        approve(&state, "session-a", &format!("승인:{}", grant.code), now()).unwrap(),
        ApprovalDecision::Activated
    );
    assert_eq!(
        approve(&state, "session-a", &format!("승인:{}", grant.code), now()).unwrap(),
        ApprovalDecision::AlreadyActive
    );

    let expired = dir.path().join("expired.json");
    let grant = issue(
        &expired,
        ApprovalRequest {
            session_id: "session-a".into(),
            scope_digest: "b".repeat(64),
            expires_at: now() - 1,
        },
    )
    .unwrap();
    assert_eq!(
        approve(
            &expired,
            "session-a",
            &format!("승인:{}", grant.code),
            now()
        )
        .unwrap(),
        ApprovalDecision::Expired
    );
}

#[test]
fn sole_pending_approval_accepts_plain_owner_input() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("approval.json");
    let grant = issue(
        &state,
        ApprovalRequest {
            session_id: "session-a".into(),
            scope_digest: "a".repeat(64),
            expires_at: now() + 60,
        },
    )
    .unwrap();
    let decision = approve(&state, "session-a", "승인", now()).unwrap();
    assert_eq!(decision, ApprovalDecision::Activated);
    assert_eq!(grant.session_id, "session-a");
}

#[test]
fn plain_approval_rejects_multiple_pending_packets_atomically() {
    let dir = tempdir().unwrap();
    let first_state = dir.path().join("first.json");
    let second_state = dir.path().join("second.json");
    let first = issue(
        &first_state,
        ApprovalRequest {
            session_id: "session-a".into(),
            scope_digest: "a".repeat(64),
            expires_at: now() + 60,
        },
    )
    .unwrap();
    issue(
        &second_state,
        ApprovalRequest {
            session_id: "session-a".into(),
            scope_digest: "b".repeat(64),
            expires_at: now() + 60,
        },
    )
    .unwrap();

    let barrier = Arc::new(Barrier::new(3));
    let mut handles = Vec::new();
    for state in [first_state.clone(), second_state.clone()] {
        let barrier = Arc::clone(&barrier);
        handles.push(thread::spawn(move || {
            barrier.wait();
            approve(&state, "session-a", "승인", now()).unwrap()
        }));
    }
    barrier.wait();
    assert_eq!(
        handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect::<Vec<_>>(),
        vec![
            ApprovalDecision::MultiplePending,
            ApprovalDecision::MultiplePending,
        ]
    );
    assert_eq!(
        approve(
            &first_state,
            "session-a",
            &format!("승인:{}", first.code),
            now(),
        )
        .unwrap(),
        ApprovalDecision::Activated
    );
    assert_eq!(
        approve(&second_state, "session-a", "`승인`", now()).unwrap(),
        ApprovalDecision::Activated
    );
}

#[test]
fn explicit_approval_set_rejects_concurrent_cross_directory_state() {
    let dir = tempdir().unwrap();
    let set_root = dir.path().join("approval-set");
    let outside = dir.path().join("outside");
    fs::create_dir_all(&set_root).unwrap();
    fs::create_dir_all(&outside).unwrap();
    let valid = set_root.join("valid.json");
    let invalid = outside.join("invalid.json");
    let barrier = Arc::new(Barrier::new(3));
    let mut handles = Vec::new();
    for (state, digest) in [(valid.clone(), 'a'), (invalid.clone(), 'b')] {
        let barrier = Arc::clone(&barrier);
        let set_root = set_root.clone();
        handles.push(thread::spawn(move || {
            barrier.wait();
            issue_in_set(
                &set_root,
                &state,
                ApprovalRequest {
                    session_id: "session-a".into(),
                    scope_digest: digest.to_string().repeat(64),
                    expires_at: now() + 60,
                },
            )
            .is_ok()
        }));
    }
    barrier.wait();
    let outcomes = handles
        .into_iter()
        .map(|handle| handle.join().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(outcomes, vec![true, false]);
    assert!(!invalid.exists());
    assert_eq!(
        approve_in_set(&set_root, &valid, "session-a", "승인", now()).unwrap(),
        ApprovalDecision::Activated
    );
}

#[test]
fn approval_cli_requires_and_uses_the_explicit_set_root() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("grant.json");
    let expires = (now() + 60).to_string();
    let issued = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "issue",
            dir.path().to_str().unwrap(),
            state.to_str().unwrap(),
            "session-a",
            &"a".repeat(64),
            &expires,
        ])
        .output()
        .unwrap();
    assert!(issued.status.success(), "{:?}", issued.stderr);
    let grant: Grant = serde_json::from_slice(&issued.stdout).unwrap();
    assert_eq!(grant.session_id, "session-a");

    let approved = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "approve",
            dir.path().to_str().unwrap(),
            state.to_str().unwrap(),
            "session-a",
            "`승인`",
            &now().to_string(),
        ])
        .output()
        .unwrap();
    assert!(approved.status.success(), "{:?}", approved.stderr);
    assert_eq!(
        String::from_utf8(approved.stdout).unwrap().trim(),
        "\"activated\""
    );
}

#[test]
fn concurrent_approval_has_one_activation() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("grant.json");
    let grant = issue(
        &state,
        ApprovalRequest {
            session_id: "session-a".into(),
            scope_digest: "c".repeat(64),
            expires_at: now() + 60,
        },
    )
    .unwrap();
    let barrier = Arc::new(Barrier::new(3));
    let mut handles = Vec::new();
    for _ in 0..2 {
        let barrier = Arc::clone(&barrier);
        let state = state.clone();
        let input = format!("승인:{}", grant.code);
        handles.push(thread::spawn(move || {
            barrier.wait();
            approve(&state, "session-a", &input, now()).unwrap()
        }));
    }
    barrier.wait();
    let mut decisions: Vec<_> = handles.into_iter().map(|h| h.join().unwrap()).collect();
    decisions.sort();
    assert_eq!(
        decisions,
        vec![ApprovalDecision::Activated, ApprovalDecision::AlreadyActive]
    );
}

#[test]
fn completion_requires_every_required_item_and_evidence() {
    let complete = CompletionManifest {
        items: vec![
            CompletionItem::required("W1", true, "cargo test: OK"),
            CompletionItem::required("A1", true, "11/11"),
            CompletionItem::optional("O1", false, ""),
        ],
    };
    assert!(verify_completion(&complete).is_complete());

    let false_done = CompletionManifest {
        items: vec![CompletionItem::required("W1", true, "")],
    };
    let verdict = verify_completion(&false_done);
    assert!(!verdict.is_complete());
    assert_eq!(verdict.unmet, vec!["W1"]);
}

#[test]
fn completion_rejects_an_empty_manifest() {
    let verdict = verify_completion(&CompletionManifest { items: Vec::new() });

    assert!(!verdict.is_complete());
    assert_eq!(verdict.unmet, vec!["manifest.required"]);
}

#[test]
fn completion_rejects_optional_only_duplicate_and_blank_ids_deterministically() {
    let optional_only = CompletionManifest {
        items: vec![CompletionItem::optional("O1", true, "observed")],
    };
    assert_eq!(
        verify_completion(&optional_only).unmet,
        vec!["manifest.required"]
    );

    let invalid = CompletionManifest {
        items: vec![
            CompletionItem::required("W1", true, "observed"),
            CompletionItem::required("W1", true, "observed"),
            CompletionItem::required(" ", true, "observed"),
            CompletionItem::required("W2", true, ""),
        ],
    };
    assert_eq!(
        verify_completion(&invalid).unmet,
        vec!["duplicate:W1", "items[2].id", "W2"]
    );
}

#[test]
fn doctor_accepts_the_root_agent_plugin_layout() {
    let dir = tempdir().unwrap();
    for relative in [
        "plugin.json",
        "clonamic.json",
        "schemas/clonamic-config.schema.json",
        "clonamic-herness-plugin.md",
        "skills/clonamic-router/SKILL.md",
        "skills/clonamic-router/references/prompt-envelope.json",
        "skills/clonamic-intent-guard/SKILL.md",
        "skills/clonamic-intent-guard/references/session-contract.json",
        "skills/clonamic-team-control/SKILL.md",
        "skills/clonamic-write-control/SKILL.md",
        "skills/clonamic-write-control/references/automation-contract.json",
        "skills/clonamic-completion-check/SKILL.md",
        "skills/clonamic-report/SKILL.md",
        "skills/clonamic-market/SKILL.md",
    ] {
        let path = dir.path().join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, b"fixture").unwrap();
    }

    let output = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .arg("doctor")
        .arg(dir.path())
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stdout: {}\nstderr: {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn doctor_rejects_each_missing_canonical_team_requirement() {
    let required = [
        "plugin.json",
        "clonamic.json",
        "schemas/clonamic-config.schema.json",
        "clonamic-herness-plugin.md",
        "skills/clonamic-router/SKILL.md",
        "skills/clonamic-router/references/prompt-envelope.json",
        "skills/clonamic-intent-guard/SKILL.md",
        "skills/clonamic-intent-guard/references/session-contract.json",
        "skills/clonamic-team-control/SKILL.md",
        "skills/clonamic-write-control/SKILL.md",
        "skills/clonamic-write-control/references/automation-contract.json",
        "skills/clonamic-completion-check/SKILL.md",
        "skills/clonamic-report/SKILL.md",
        "skills/clonamic-market/SKILL.md",
    ];
    for missing in [
        "clonamic-herness-plugin.md",
        "clonamic.json",
        "schemas/clonamic-config.schema.json",
        "skills/clonamic-router/references/prompt-envelope.json",
        "skills/clonamic-intent-guard/SKILL.md",
        "skills/clonamic-intent-guard/references/session-contract.json",
        "skills/clonamic-team-control/SKILL.md",
        "skills/clonamic-write-control/references/automation-contract.json",
    ] {
        let dir = tempdir().unwrap();
        for relative in required.into_iter().filter(|relative| *relative != missing) {
            let path = dir.path().join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, b"fixture").unwrap();
        }

        let output = Command::new(env!("CARGO_BIN_EXE_clonamic"))
            .arg("doctor")
            .arg(dir.path())
            .output()
            .unwrap();

        assert!(
            !output.status.success(),
            "doctor accepted missing {missing}"
        );
        let payload: Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(payload["missing"], serde_json::json!([missing]));
    }
}

#[test]
fn root_manifest_uses_the_agent_plugins_1_0_contract() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let manifest: Value = serde_json::from_slice(&fs::read(root.join("plugin.json")).unwrap())
        .expect("root plugin.json must be valid JSON");
    let object = manifest.as_object().expect("manifest must be an object");
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = [
        "$schema",
        "author",
        "description",
        "homepage",
        "keywords",
        "license",
        "name",
        "repository",
        "version",
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();

    assert_eq!(actual, expected);
    assert_eq!(
        object["$schema"],
        "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    );
    assert_eq!(object["version"], "1.0.0");
}

#[test]
fn install_and_uninstall_restore_original_router_bytes() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    fs::write(&router, b"existing user rules\n").unwrap();
    let original = fs::read(&router).unwrap();

    install_router(InstallRequest {
        router: router.clone(),
        state: state.clone(),
        plugin_root: plugin_root_with_guidance(dir.path()),
    })
    .unwrap();
    let installed = fs::read_to_string(&router).unwrap();
    assert!(installed.contains("clonamic:begin"));
    assert!(installed.contains("existing user rules"));

    uninstall_router(&router, &state).unwrap();
    assert_eq!(fs::read(&router).unwrap(), original);
}

#[test]
fn router_install_references_canonical_guidance_once_without_copying_policy() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    let plugin_root = plugin_root_with_guidance(dir.path());
    fs::write(&router, b"existing user rules\n").unwrap();
    let original = fs::read(&router).unwrap();

    install_router(InstallRequest {
        router: router.clone(),
        state: state.clone(),
        plugin_root,
    })
    .unwrap();

    let installed = fs::read_to_string(&router).unwrap();
    assert_eq!(installed.matches("clonamic-herness-plugin.md").count(), 1);
    assert!(!installed.contains("For persistent writes"));
    assert!(!installed.contains("Before reporting completion"));
    assert!(!installed.contains("External AI executors"));

    uninstall_router(&router, &state).unwrap();
    assert_eq!(fs::read(&router).unwrap(), original);
}

#[test]
fn router_install_rejects_missing_guidance_without_writes() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    let backup = state.with_extension("backup");
    fs::write(&router, b"existing user rules\n").unwrap();
    let original = fs::read(&router).unwrap();

    assert!(
        install_router(InstallRequest {
            router: router.clone(),
            state: state.clone(),
            plugin_root: dir.path().join("plugin"),
        })
        .is_err()
    );

    assert_eq!(fs::read(&router).unwrap(), original);
    assert!(!state.exists());
    assert!(!backup.exists());
}

#[cfg(unix)]
#[test]
fn router_install_rejects_symlinked_guidance_without_writes() {
    use std::os::unix::fs::symlink;

    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    let backup = state.with_extension("backup");
    let plugin_root = dir.path().join("plugin");
    fs::create_dir(&plugin_root).unwrap();
    fs::write(dir.path().join("guidance.md"), b"guidance\n").unwrap();
    symlink(
        dir.path().join("guidance.md"),
        plugin_root.join("clonamic-herness-plugin.md"),
    )
    .unwrap();
    fs::write(&router, b"existing user rules\n").unwrap();
    let original = fs::read(&router).unwrap();

    assert!(
        install_router(InstallRequest {
            router: router.clone(),
            state: state.clone(),
            plugin_root,
        })
        .is_err()
    );

    assert_eq!(fs::read(&router).unwrap(), original);
    assert!(!state.exists());
    assert!(!backup.exists());
}

#[test]
fn approval_replaces_existing_state_with_latest_valid_json() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("grant.json");
    issue(
        &state,
        ApprovalRequest {
            session_id: "first".into(),
            scope_digest: "a".repeat(64),
            expires_at: now() + 60,
        },
    )
    .unwrap();
    issue(
        &state,
        ApprovalRequest {
            session_id: "second".into(),
            scope_digest: "b".repeat(64),
            expires_at: now() + 120,
        },
    )
    .unwrap();

    let grant: Grant = serde_json::from_slice(&fs::read(&state).unwrap()).unwrap();
    assert_eq!(grant.session_id, "second");
    assert_eq!(grant.scope_digest, "b".repeat(64));
}

#[cfg(unix)]
#[test]
fn approval_does_not_follow_a_precreated_predictable_temp_symlink() {
    use std::os::unix::fs::symlink;

    let dir = tempdir().unwrap();
    let state = dir.path().join("grant.json");
    let outside = dir.path().join("outside.json");
    let legacy_temp = state.with_extension(format!("tmp.{}", std::process::id()));
    fs::write(&outside, b"outside\n").unwrap();
    symlink(&outside, &legacy_temp).unwrap();

    issue(
        &state,
        ApprovalRequest {
            session_id: "session-a".into(),
            scope_digest: "a".repeat(64),
            expires_at: now() + 60,
        },
    )
    .unwrap();

    assert_eq!(fs::read(&outside).unwrap(), b"outside\n");
    assert!(
        fs::symlink_metadata(&legacy_temp)
            .unwrap()
            .file_type()
            .is_symlink()
    );
    assert!(
        !fs::symlink_metadata(&state)
            .unwrap()
            .file_type()
            .is_symlink()
    );
}

#[test]
fn approval_cleans_temporary_file_when_replace_fails() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("state-is-a-directory");
    fs::create_dir(&state).unwrap();

    assert!(
        issue(
            &state,
            ApprovalRequest {
                session_id: "session-a".into(),
                scope_digest: "a".repeat(64),
                expires_at: now() + 60,
            },
        )
        .is_err()
    );
    assert_eq!(
        fs::read_dir(dir.path()).unwrap().count(),
        1,
        "failed replacement left a temporary file"
    );
}

#[cfg(unix)]
#[test]
fn atomic_outputs_are_private_on_unix() {
    use std::os::unix::fs::PermissionsExt;

    let dir = tempdir().unwrap();
    let state = dir.path().join("grant.json");
    issue(
        &state,
        ApprovalRequest {
            session_id: "session-a".into(),
            scope_digest: "a".repeat(64),
            expires_at: now() + 60,
        },
    )
    .unwrap();
    assert_eq!(
        fs::metadata(&state).unwrap().permissions().mode() & 0o777,
        0o600
    );

    let router = dir.path().join("AGENTS.md");
    let install_state = dir.path().join("install.json");
    fs::write(&router, b"existing\n").unwrap();
    install_router(InstallRequest {
        router: router.clone(),
        state: install_state.clone(),
        plugin_root: plugin_root_with_guidance(dir.path()),
    })
    .unwrap();
    for path in [
        router,
        install_state.clone(),
        install_state.with_extension("backup"),
    ] {
        assert_eq!(
            fs::metadata(path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
}

#[test]
fn installation_does_not_consume_a_precreated_temp_collision() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    let collision = dir
        .path()
        .join(format!(".AGENTS.md.tmp.{}", std::process::id()));
    fs::write(&router, b"existing\n").unwrap();
    fs::write(&collision, b"collision\n").unwrap();

    install_router(InstallRequest {
        router,
        state,
        plugin_root: plugin_root_with_guidance(dir.path()),
    })
    .unwrap();

    assert_eq!(fs::read(&collision).unwrap(), b"collision\n");
}

#[test]
fn corrupted_state_fails_without_changing_router() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    fs::write(&router, b"existing\n").unwrap();
    fs::write(&state, b"not-json").unwrap();
    let before = fs::read(&router).unwrap();
    assert!(uninstall_router(&router, &state).is_err());
    assert_eq!(fs::read(&router).unwrap(), before);
}

#[test]
fn reinstall_is_idempotent_and_does_not_duplicate_router_block() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    fs::write(&router, b"existing\n").unwrap();
    let request = || InstallRequest {
        router: router.clone(),
        state: state.clone(),
        plugin_root: plugin_root_with_guidance(dir.path()),
    };
    install_router(request()).unwrap();
    let first = fs::read(&router).unwrap();
    install_router(request()).unwrap();
    let second = fs::read(&router).unwrap();
    assert_eq!(first, second);
    assert_eq!(
        String::from_utf8(second)
            .unwrap()
            .matches("clonamic:begin")
            .count(),
        1
    );
}

#[test]
fn failed_state_write_rolls_router_back() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("state-is-a-directory");
    fs::write(&router, b"existing\n").unwrap();
    fs::create_dir(&state).unwrap();
    let before = fs::read(&router).unwrap();
    assert!(
        install_router(InstallRequest {
            router: router.clone(),
            state,
            plugin_root: plugin_root_with_guidance(dir.path()),
        })
        .is_err()
    );
    assert_eq!(fs::read(&router).unwrap(), before);
}

#[test]
fn uninstall_preserves_user_edits_after_install() {
    let dir = tempdir().unwrap();
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    fs::write(&router, b"existing\n").unwrap();
    install_router(InstallRequest {
        router: router.clone(),
        state: state.clone(),
        plugin_root: plugin_root_with_guidance(dir.path()),
    })
    .unwrap();
    let mut edited = fs::read_to_string(&router).unwrap();
    edited.push_str("user edit after install\n");
    fs::write(&router, edited).unwrap();
    uninstall_router(&router, &state).unwrap();
    assert_eq!(
        fs::read_to_string(&router).unwrap(),
        "existing\nuser edit after install\n"
    );
}

#[cfg(unix)]
#[test]
fn symlink_router_is_rejected_without_touching_target() {
    use std::os::unix::fs::symlink;

    let dir = tempdir().unwrap();
    let target = dir.path().join("real-agents.md");
    let router = dir.path().join("AGENTS.md");
    let state = dir.path().join("install.json");
    fs::write(&target, b"outside\n").unwrap();
    symlink(&target, &router).unwrap();
    assert!(
        install_router(InstallRequest {
            router,
            state,
            plugin_root: plugin_root_with_guidance(dir.path()),
        })
        .is_err()
    );
    assert_eq!(fs::read(&target).unwrap(), b"outside\n");
}

#[cfg(unix)]
#[test]
fn symlink_parent_is_rejected_before_creating_router() {
    use std::os::unix::fs::symlink;

    let dir = tempdir().unwrap();
    let real = dir.path().join("real-home");
    let alias = dir.path().join("alias-home");
    fs::create_dir(&real).unwrap();
    symlink(&real, &alias).unwrap();
    let router = alias.join("AGENTS.md");
    assert!(
        install_router(InstallRequest {
            router,
            state: dir.path().join("install.json"),
            plugin_root: plugin_root_with_guidance(dir.path()),
        })
        .is_err()
    );
    assert!(!real.join("AGENTS.md").exists());
}

#[cfg(unix)]
#[test]
fn symlink_parent_is_rejected_when_router_already_exists() {
    use std::os::unix::fs::symlink;

    let dir = tempdir().unwrap();
    let real = dir.path().join("real-home");
    let alias = dir.path().join("alias-home");
    let target = real.join("AGENTS.md");
    fs::create_dir(&real).unwrap();
    fs::write(&target, b"outside\n").unwrap();
    symlink(&real, &alias).unwrap();

    assert!(
        install_router(InstallRequest {
            router: alias.join("AGENTS.md"),
            state: dir.path().join("install.json"),
            plugin_root: plugin_root_with_guidance(dir.path()),
        })
        .is_err()
    );
    assert_eq!(fs::read(&target).unwrap(), b"outside\n");
}

fn envelope(source: PromptSource, body: &str) -> PromptEnvelope {
    envelope_at(source, body, 10)
}

fn envelope_at(source: PromptSource, body: &str, received_at: u64) -> PromptEnvelope {
    PromptEnvelope {
        prompt_id: "prompt-1".into(),
        session_id: "session-a".into(),
        claimed_source: source,
        body: body.into(),
        body_sha256: sha256_hex(body.as_bytes()),
        received_at,
        parent_prompt_id: None,
        automation: None,
    }
}

fn user_scope_authority(
    prompt_id: &str,
    session_id: &str,
    scope: BTreeSet<String>,
) -> ScopeAuthority {
    let mut parent = envelope(PromptSource::User, "parent");
    parent.prompt_id = prompt_id.into();
    parent.session_id = session_id.into();
    classify_prompt(parent, HostSource::User, None, None)
        .unwrap()
        .scope_authority(scope)
}

#[test]
fn prompt_envelope_is_closed_and_requires_the_exact_body_digest() {
    let body = "요청 원문 [\"그대로\"]";
    let valid = serde_json::to_string(&envelope(PromptSource::User, body)).unwrap();
    assert_eq!(parse_envelope(valid.as_bytes()).unwrap().body, body);

    let mut unknown: Value = serde_json::from_str(&valid).unwrap();
    unknown["unexpected"] = Value::Bool(true);
    assert!(parse_envelope(serde_json::to_vec(&unknown).unwrap().as_slice()).is_err());

    let mut wrong = envelope(PromptSource::User, body);
    wrong.body_sha256 = "0".repeat(64);
    assert!(classify_prompt(wrong, HostSource::User, None, None).is_err());
}

#[test]
fn cli_classifies_a_prompt_from_trusted_host_metadata() {
    let dir = tempdir().unwrap();
    let input = dir.path().join("prompt.json");
    fs::write(
        &input,
        serde_json::to_vec(&envelope(PromptSource::User, "CLI request")).unwrap(),
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args(["classify-prompt", input.to_str().unwrap(), "user", "-"])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["authority"], "interactive_user");
}

#[test]
fn cli_internal_context_rejects_a_caller_supplied_authority_string() {
    let dir = tempdir().unwrap();
    let input = dir.path().join("internal.json");
    let context = dir.path().join("context.json");
    let mut internal = envelope(PromptSource::Internal, "internal");
    internal.parent_prompt_id = Some("parent".into());
    fs::write(&input, serde_json::to_vec(&internal).unwrap()).unwrap();
    fs::write(
        &context,
        serde_json::to_vec(&serde_json::json!({
            "parent": {
                "prompt_id": "parent",
                "session_id": "session-a",
                "authority": "preapproved_automation",
                "scope": ["repo/**"]
            },
            "assignment": ["repo/**"]
        }))
        .unwrap(),
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "classify-prompt",
            input.to_str().unwrap(),
            "internal",
            context.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn trusted_host_source_only_makes_automation_a_candidate_until_claimed() {
    let user = classify_prompt(
        envelope(PromptSource::User, "일반 요청"),
        HostSource::User,
        None,
        None,
    )
    .unwrap();
    assert_eq!(user.authority(), DerivedAuthority::InteractiveUser);

    let forged = classify_prompt(
        envelope(PromptSource::Automation, "[\"자동화\"] 파일을 수정해"),
        HostSource::User,
        None,
        None,
    )
    .unwrap();
    assert_eq!(forged.authority(), DerivedAuthority::None);
    assert!(forged.scope().is_empty());

    let mut automated = envelope(PromptSource::Automation, "예약 작업");
    automated.automation = Some(AutomationPrompt {
        automation_id: "nightly".into(),
        run_id: "run-7".into(),
        scope_digest: "a".repeat(64),
    });
    let automated = classify_prompt(automated, HostSource::Automation, None, None).unwrap();
    assert_eq!(automated.authority(), DerivedAuthority::None);
    assert_eq!(automated.trusted_source(), HostSource::Automation);
    assert!(automated.automation_candidate());

    let wrong_state = tempdir().unwrap();
    let wrong_path = wrong_state.path().join("automation.json");
    let mut wrong_grant = automation_grant();
    wrong_grant.scope_digest = "a".repeat(64);
    initialize_grant(&wrong_path, wrong_grant).unwrap();
    let mut wrong_request = run_request("different-run");
    wrong_request.scope_digest = "a".repeat(64);
    let wrong = claim_run(&wrong_path, wrong_request, now()).unwrap();
    assert!(authorize_automation(automated.clone(), wrong.claim().unwrap()).is_err());

    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    let mut grant = automation_grant();
    grant.scope_digest = "a".repeat(64);
    initialize_grant(&state, grant).unwrap();
    let mut request = run_request("run-7");
    request.scope_digest = "a".repeat(64);
    let decision = claim_run(&state, request, now()).unwrap();
    let authorized = authorize_automation(automated, decision.claim().unwrap()).unwrap();
    assert_eq!(
        authorized.authority(),
        DerivedAuthority::PreapprovedAutomation
    );
    assert!(!authorized.automation_candidate());
}

#[test]
fn internal_prompt_inherits_only_the_parent_assignment_intersection() {
    let parent = user_scope_authority(
        "prompt-parent",
        "session-a",
        ["a", "b"].into_iter().map(str::to_string).collect(),
    );
    let assignment = ["b", "c"].into_iter().map(str::to_string).collect();
    let mut internal = envelope(PromptSource::Internal, "worker instruction");
    internal.parent_prompt_id = Some("prompt-parent".into());
    let validated = classify_prompt(
        internal,
        HostSource::Internal,
        Some(&parent),
        Some(&assignment),
    )
    .unwrap();
    assert_eq!(validated.authority(), DerivedAuthority::InheritedInternal);
    let expected: BTreeSet<String> = ["b"].into_iter().map(str::to_string).collect();
    assert_eq!(validated.scope(), &expected);
}

#[test]
fn internal_prompt_rejects_parent_id_and_session_mismatches() {
    let assignment: BTreeSet<String> = ["b"].into_iter().map(str::to_string).collect();
    let mut internal = envelope(PromptSource::Internal, "worker instruction");
    internal.parent_prompt_id = Some("prompt-parent".into());
    for parent in [
        user_scope_authority("different-parent", "session-a", assignment.clone()),
        user_scope_authority("prompt-parent", "different-session", assignment.clone()),
    ] {
        let validated = classify_prompt(
            internal.clone(),
            HostSource::Internal,
            Some(&parent),
            Some(&assignment),
        )
        .unwrap();
        assert_eq!(validated.authority(), DerivedAuthority::None);
        assert!(validated.scope().is_empty());
    }
}

fn automation_grant() -> AutomationGrant {
    AutomationGrant {
        automation_id: "nightly".into(),
        definition_digest: "d".repeat(64),
        scope_digest: "b".repeat(64),
        targets: ["repo/**"].into_iter().map(str::to_string).collect(),
        operations: ["read", "write", "verify", "rollback"]
            .into_iter()
            .map(str::to_string)
            .collect(),
        external_effects: ["git_push"].into_iter().map(str::to_string).collect(),
        verification: ["cargo test"].into_iter().map(str::to_string).collect(),
        rollback: ["git revert"].into_iter().map(str::to_string).collect(),
        expires_at: now() + 60,
        max_runs: 2,
        initial_sequence: 7,
        credential_policy: CredentialPolicy::PlatformAction,
    }
}

fn run_request(run_id: &str) -> AutomationRunRequest {
    AutomationRunRequest {
        automation_id: "nightly".into(),
        run_id: run_id.into(),
        definition_digest: "d".repeat(64),
        scope_digest: "b".repeat(64),
        targets: ["repo/**"].into_iter().map(str::to_string).collect(),
        operations: ["write", "verify"]
            .into_iter()
            .map(str::to_string)
            .collect(),
        external_effects: ["git_push"].into_iter().map(str::to_string).collect(),
        verification: ["cargo test"].into_iter().map(str::to_string).collect(),
        rollback: ["git revert"].into_iter().map(str::to_string).collect(),
        sequence: 7,
        platform_action_required: false,
    }
}

#[test]
fn automation_enforces_verification_rollback_and_validates_optional_effects() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    initialize_grant(&state, automation_grant()).unwrap();

    let mut verification = run_request("verification");
    verification.verification.insert("unapproved check".into());
    assert_eq!(
        claim_run(&state, verification, now()).unwrap().reason,
        "verification_out_of_scope"
    );

    let mut rollback = run_request("rollback");
    rollback.rollback.insert("unapproved rollback".into());
    assert_eq!(
        claim_run(&state, rollback, now()).unwrap().reason,
        "rollback_out_of_scope"
    );

    let mut invalid = run_request("invalid-effect");
    invalid.external_effects.insert("bad\neffect".into());
    assert!(claim_run(&state, invalid, now()).is_err());

    let mut no_effect = run_request("no-effect");
    no_effect.external_effects.clear();
    assert_eq!(
        claim_run(&state, no_effect, now()).unwrap().status,
        RunStatus::Claimed
    );
}

#[test]
fn grant_initialization_is_idempotent_and_never_resets_run_state() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    let grant = automation_grant();
    initialize_grant(&state, grant.clone()).unwrap();
    assert_eq!(
        claim_run(&state, run_request("run-1"), now())
            .unwrap()
            .status,
        RunStatus::Claimed
    );

    initialize_grant(&state, grant.clone()).unwrap();
    assert_eq!(
        claim_run(&state, run_request("run-1"), now())
            .unwrap()
            .status,
        RunStatus::ReplayRejected
    );

    let mut widened = grant;
    widened.targets.insert("outside/**".into());
    assert!(initialize_grant(&state, widened).is_err());
    let mut next = run_request("run-2");
    next.sequence = 8;
    assert_eq!(
        claim_run(&state, next, now()).unwrap().status,
        RunStatus::Claimed
    );
}

#[test]
fn concurrent_different_grant_initialization_has_one_winner() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    let barrier = Arc::new(Barrier::new(3));
    let mut handles = Vec::new();
    for suffix in ["a", "b"] {
        let state = state.clone();
        let barrier = Arc::clone(&barrier);
        let mut grant = automation_grant();
        grant.targets.insert(format!("repo/{suffix}"));
        handles.push(thread::spawn(move || {
            barrier.wait();
            initialize_grant(&state, grant).is_ok()
        }));
    }
    barrier.wait();
    assert_eq!(
        handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .filter(|won| *won)
            .count(),
        1
    );
}

#[test]
fn automation_claim_is_noninteractive_and_rejects_replay_and_scope_changes() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    initialize_grant(&state, automation_grant()).unwrap();

    let claimed = claim_run(&state, run_request("run-1"), now()).unwrap();
    assert_eq!(claimed.status, RunStatus::Claimed);
    assert!(claimed.write_authorized);
    assert!(!claimed.interactive);
    assert!(claimed.claim().is_some());

    let replay = claim_run(&state, run_request("run-1"), now()).unwrap();
    assert_eq!(replay.status, RunStatus::ReplayRejected);
    assert!(!replay.write_authorized);
    assert!(!replay.interactive);
    assert!(replay.claim().is_none());

    let mut widened = run_request("run-2");
    widened.sequence = 8;
    widened.targets.insert("outside/**".into());
    let rejected = claim_run(&state, widened, now()).unwrap();
    assert_eq!(rejected.status, RunStatus::NeedsAuthorization);
    assert_eq!(rejected.reason, "targets_out_of_scope");
    assert!(!rejected.interactive);
}

#[test]
fn automation_waits_for_platform_credentials_without_consuming_the_run() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    initialize_grant(&state, automation_grant()).unwrap();
    let mut request = run_request("run-1");
    request.platform_action_required = true;

    let waiting = claim_run(&state, request, now()).unwrap();
    assert_eq!(waiting.status, RunStatus::WaitingPlatformAction);
    assert!(!waiting.write_authorized);
    assert!(!waiting.interactive);
    assert!(waiting.claim().is_none());

    let claimed = claim_run(&state, run_request("run-1"), now()).unwrap();
    assert_eq!(claimed.status, RunStatus::Claimed);
}

#[test]
fn cli_initializes_and_claims_an_automation_run() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    let grant = dir.path().join("grant.json");
    let request = dir.path().join("run.json");
    fs::write(&grant, serde_json::to_vec(&automation_grant()).unwrap()).unwrap();
    fs::write(
        &request,
        serde_json::to_vec(&run_request("run-cli")).unwrap(),
    )
    .unwrap();

    let initialized = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "automation-init",
            state.to_str().unwrap(),
            grant.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(
        initialized.status.success(),
        "{}",
        String::from_utf8_lossy(&initialized.stderr)
    );

    let claimed = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "automation-claim",
            state.to_str().unwrap(),
            request.to_str().unwrap(),
            &now().to_string(),
        ])
        .output()
        .unwrap();
    assert!(
        claimed.status.success(),
        "{}",
        String::from_utf8_lossy(&claimed.stderr)
    );
    let payload: Value = serde_json::from_slice(&claimed.stdout).unwrap();
    assert_eq!(payload["status"], "claimed");
    assert_eq!(payload["interactive"], false);

    let mut widened = automation_grant();
    widened.targets.insert("outside/**".into());
    fs::write(&grant, serde_json::to_vec(&widened).unwrap()).unwrap();
    let rejected = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "automation-init",
            state.to_str().unwrap(),
            grant.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(!rejected.status.success());
    assert_eq!(
        claim_run(&state, run_request("run-cli"), now())
            .unwrap()
            .status,
        RunStatus::ReplayRejected
    );
}

#[test]
fn concurrent_automation_claim_has_exactly_one_winner() {
    let dir = tempdir().unwrap();
    let state = dir.path().join("automation.json");
    initialize_grant(&state, automation_grant()).unwrap();
    let barrier = Arc::new(Barrier::new(3));
    let mut handles = Vec::new();
    for _ in 0..2 {
        let state = state.clone();
        let barrier = Arc::clone(&barrier);
        handles.push(thread::spawn(move || {
            barrier.wait();
            claim_run(&state, run_request("run-1"), now())
                .unwrap()
                .status
        }));
    }
    barrier.wait();
    let statuses = handles
        .into_iter()
        .map(|handle| handle.join().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(
        statuses
            .iter()
            .filter(|status| **status == RunStatus::Claimed)
            .count(),
        1
    );
    assert_eq!(
        statuses
            .iter()
            .filter(|status| **status == RunStatus::ReplayRejected)
            .count(),
        1
    );
}

fn validated(
    source: PromptSource,
    host: HostSource,
    body: &str,
) -> clonamic_core::provenance::ValidatedPrompt {
    let mut value = envelope(source, body);
    if source == PromptSource::Automation {
        value.automation = Some(AutomationPrompt {
            automation_id: "nightly".into(),
            run_id: "run-1".into(),
            scope_digest: "a".repeat(64),
        });
    }
    if source == PromptSource::Internal {
        value.parent_prompt_id = Some("prompt-parent".into());
        let assignment: BTreeSet<String> = ["repo/**"].into_iter().map(str::to_string).collect();
        let parent = user_scope_authority("prompt-parent", "session-a", assignment.clone());
        classify_prompt(value, host, Some(&parent), Some(&assignment)).unwrap()
    } else {
        let candidate = classify_prompt(value, host, None, None).unwrap();
        if source != PromptSource::Automation || host != HostSource::Automation {
            return candidate;
        }
        let dir = tempdir().unwrap();
        let state = dir.path().join("automation.json");
        let mut grant = automation_grant();
        grant.scope_digest = "a".repeat(64);
        initialize_grant(&state, grant).unwrap();
        let mut request = run_request("run-1");
        request.scope_digest = "a".repeat(64);
        let decision = claim_run(&state, request, now()).unwrap();
        authorize_automation(candidate, decision.claim().unwrap()).unwrap()
    }
}

#[test]
fn session_markdown_preserves_the_last_external_prompt_across_internal_updates() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("session.md");
    let raw = "[\"자동화\"]\n두 번째 줄은 원문 그대로";
    let automated = validated(PromptSource::Automation, HostSource::Automation, raw);
    update_session(&path, SessionUpdate::new(automated), None).unwrap();
    let first = fs::read_to_string(&path).unwrap();
    assert!(first.contains("last_user_prompt_label: \"[\\\"자동화\\\"]\""));
    assert!(first.ends_with(raw));

    let internal = validated(PromptSource::Internal, HostSource::Internal, "worker step");
    update_session(&path, SessionUpdate::new(internal), None).unwrap();
    let second = fs::read_to_string(&path).unwrap();
    assert!(second.contains("active_source: \"internal\""));
    assert!(second.contains("last_user_prompt_source: \"automation\""));
    assert!(second.ends_with(raw));
}

#[test]
fn cli_writes_a_bounded_session_from_a_classified_prompt() {
    let dir = tempdir().unwrap();
    let input = dir.path().join("prompt.json");
    let session = dir.path().join("session.md");
    fs::write(
        &input,
        serde_json::to_vec(&envelope(PromptSource::User, "session request")).unwrap(),
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "session-update",
            session.to_str().unwrap(),
            input.to_str().unwrap(),
            "user",
            "-",
            "-",
        ])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        fs::read_to_string(session)
            .unwrap()
            .ends_with("session request")
    );
}

#[test]
fn cli_claims_automation_before_writing_its_session_label() {
    let dir = tempdir().unwrap();
    let input = dir.path().join("prompt.json");
    let grant_path = dir.path().join("grant.json");
    let request_path = dir.path().join("run.json");
    let state = dir.path().join("automation.json");
    let session = dir.path().join("session.md");
    let mut prompt = envelope(PromptSource::Automation, "automation session");
    prompt.automation = Some(AutomationPrompt {
        automation_id: "nightly".into(),
        run_id: "run-cli-session".into(),
        scope_digest: "b".repeat(64),
    });
    fs::write(&input, serde_json::to_vec(&prompt).unwrap()).unwrap();
    fs::write(
        &grant_path,
        serde_json::to_vec(&automation_grant()).unwrap(),
    )
    .unwrap();
    fs::write(
        &request_path,
        serde_json::to_vec(&run_request("run-cli-session")).unwrap(),
    )
    .unwrap();
    let initialized = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "automation-init",
            state.to_str().unwrap(),
            grant_path.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(initialized.status.success());

    let output = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args([
            "automation-session-update",
            session.to_str().unwrap(),
            input.to_str().unwrap(),
            state.to_str().unwrap(),
            request_path.to_str().unwrap(),
            &now().to_string(),
            "-",
        ])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let markdown = fs::read_to_string(session).unwrap();
    assert!(markdown.contains("active_authority: \"preapproved_automation\""));
    assert!(markdown.contains("last_user_prompt_label: \"[\\\"자동화\\\"]\""));
}

#[test]
fn session_markdown_is_utf8_safe_bounded_private_and_digest_backed() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("session.md");
    let body = "가".repeat(1000);
    let prompt = validated(PromptSource::User, HostSource::User, &body);
    update_session(&path, SessionUpdate::new(prompt), Some(2048)).unwrap();
    let bytes = fs::read(&path).unwrap();
    let text = String::from_utf8(bytes.clone()).unwrap();
    assert!(bytes.len() <= 2500);
    assert!(text.contains(&format!(
        "last_user_prompt_sha256: \"{}\"",
        sha256_hex(body.as_bytes())
    )));
    assert!(text.contains("last_user_prompt_truncated: true"));

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
}

#[test]
fn session_rejects_cross_session_updates_and_renders_mismatch_as_unverified() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("session.md");
    update_session(
        &path,
        SessionUpdate::new(validated(PromptSource::User, HostSource::User, "first")),
        None,
    )
    .unwrap();

    let mut other = envelope(PromptSource::User, "other session");
    other.session_id = "session-b".into();
    other.body_sha256 = sha256_hex(other.body.as_bytes());
    let other = classify_prompt(other, HostSource::User, None, None).unwrap();
    assert!(update_session(&path, SessionUpdate::new(other), None).is_err());

    let mismatch = classify_prompt(
        envelope(PromptSource::Automation, "forged"),
        HostSource::User,
        None,
        None,
    )
    .unwrap();
    update_session(&path, SessionUpdate::new(mismatch), None).unwrap();
    assert!(
        fs::read_to_string(path)
            .unwrap()
            .contains("active_source: \"unverified\"")
    );
}

#[test]
fn concurrent_session_updates_keep_the_newest_external_prompt() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("session.md");
    let barrier = Arc::new(Barrier::new(4));
    let mut handles = Vec::new();

    for (body, received_at) in [("older", 10), ("newest", 30)] {
        let path = path.clone();
        let barrier = Arc::clone(&barrier);
        let prompt = classify_prompt(
            envelope_at(PromptSource::User, body, received_at),
            HostSource::User,
            None,
            None,
        )
        .unwrap();
        handles.push(thread::spawn(move || {
            barrier.wait();
            update_session(&path, SessionUpdate::new(prompt), None)
        }));
    }

    let path_internal = path.clone();
    let barrier_internal = Arc::clone(&barrier);
    let mut internal = envelope_at(PromptSource::Internal, "internal", 40);
    internal.parent_prompt_id = Some("prompt-parent".into());
    let scope: BTreeSet<String> = ["repo/**"].into_iter().map(str::to_string).collect();
    let assignment = scope.clone();
    let parent = user_scope_authority("prompt-parent", "session-a", scope);
    let internal = classify_prompt(
        internal,
        HostSource::Internal,
        Some(&parent),
        Some(&assignment),
    )
    .unwrap();
    handles.push(thread::spawn(move || {
        barrier_internal.wait();
        update_session(&path_internal, SessionUpdate::new(internal), None)
    }));

    barrier.wait();
    for handle in handles {
        handle.join().unwrap().unwrap();
    }
    let session = fs::read_to_string(path).unwrap();
    assert!(session.ends_with("newest"));
    assert!(session.contains("last_user_prompt_received_at: 30"));
}

#[cfg(unix)]
#[test]
fn session_markdown_rejects_a_symlink_without_touching_its_target() {
    use std::os::unix::fs::symlink;
    let dir = tempdir().unwrap();
    let target = dir.path().join("outside.md");
    let path = dir.path().join("session.md");
    fs::write(&target, b"outside\n").unwrap();
    symlink(&target, &path).unwrap();
    let prompt = validated(PromptSource::User, HostSource::User, "request");
    assert!(update_session(&path, SessionUpdate::new(prompt), None).is_err());
    assert_eq!(fs::read(&target).unwrap(), b"outside\n");
}

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn all_installed() -> BTreeSet<String> {
    [
        "clonamic-code-plugin",
        "clonamic-writing-plugin",
        "clonamic-design-plugin",
        "clonamic-data-plugin",
        "clonamic-documents-plugin",
        "clonamic-ppt",
        "clonamic-preprocessing",
        "clonamic-memory",
        "clonamic-grok",
        "clonamic-gpt",
        "clonamic-claude",
        "clonamic-hermes",
    ]
    .into_iter()
    .map(str::to_string)
    .collect()
}

fn resolve_paths(
    default_config: Option<PathBuf>,
    user_config: Option<PathBuf>,
    project_config: Option<PathBuf>,
) -> ResolvePaths {
    let root = repository_root();
    ResolvePaths {
        catalog: root.join("catalog/plugins.json"),
        manifest_root: root,
        default_config,
        user_config,
        project_config,
    }
}

#[test]
fn plugin_resolution_without_runtime_evidence_fails_closed_for_runtime_packages() {
    for invalid in [
        "Invalid Platform",
        ".",
        "-",
        "..",
        "--",
        ".bad",
        "bad.",
        "bad..id",
        "bad--id",
        "bad/id",
    ] {
        assert!(
            resolve_plugins(&resolve_paths(None, None, None), invalid, &all_installed(),).is_err(),
            "accepted invalid platform id: {invalid}"
        );
    }
    let resolution =
        resolve_plugins(&resolve_paths(None, None, None), "codex", &all_installed()).unwrap();
    assert_eq!(resolution.status, ResolutionStatus::Ok);
    assert!(resolution.configuration.is_none());
    let core = resolution.plugin("clonamic-herness-plugin").unwrap();
    assert!(
        core.configured
            && core.installed
            && core.platform_supported
            && core.dependencies_ready
            && core.effective
    );
    assert_eq!(core.reason, "required");
    assert!(resolution.plugin("clonamic-memory").unwrap().effective);
    let self_host = resolution.plugin("clonamic-gpt").unwrap();
    assert!(!self_host.platform_supported);
    assert!(!self_host.effective);
    assert_eq!(self_host.reason, "enabled_but_unavailable");

    let portable = resolve_plugins(
        &resolve_paths(None, None, None),
        "agent-plugins",
        &all_installed(),
    )
    .unwrap();
    assert!(
        portable
            .plugins
            .iter()
            .all(|plugin| plugin.platform_supported)
    );
    assert!(
        portable
            .plugins
            .iter()
            .filter(|plugin| plugin.name != "clonamic-ppt")
            .all(|plugin| plugin.effective)
    );
    let ppt = portable.plugin("clonamic-ppt").unwrap();
    assert!(!ppt.runtime_ready);
    assert!(!ppt.effective);
    assert_eq!(ppt.reason, "enabled_but_unavailable");
}

#[cfg(unix)]
#[test]
fn plugin_resolution_rejects_symlinked_manifest_outside_root() {
    use std::os::unix::fs::symlink;

    let dir = tempdir().unwrap();
    let root = dir.path().join("root");
    fs::create_dir_all(root.join("plugins/child")).unwrap();
    fs::write(root.join("plugin.json"), r#"{"name":"root"}"#).unwrap();
    let outside = dir.path().join("outside.json");
    fs::write(&outside, r#"{"name":"escaped"}"#).unwrap();
    symlink(&outside, root.join("plugins/child/plugin.json")).unwrap();
    fs::write(
        root.join("catalog.json"),
        r#"{"plugins":[{"manifest":"plugin.json","required":true,"category":"core","platforms":["codex"],"dependencies":[]},{"manifest":"plugins/child/plugin.json","required":false,"category":"test","platforms":["codex"],"dependencies":[]}]}"#,
    )
    .unwrap();
    let result = resolve_plugins(
        &ResolvePaths {
            catalog: root.join("catalog.json"),
            manifest_root: root,
            default_config: None,
            user_config: None,
            project_config: None,
        },
        "codex",
        &BTreeSet::new(),
    );
    assert!(result.is_err());
}

#[test]
fn plugin_resolution_uses_project_then_user_then_default_without_discovery() {
    let root = repository_root();
    let fixtures = root.join("tests/fixtures/plugin-config");
    let dir = tempdir().unwrap();
    fs::create_dir(dir.path().join("nested")).unwrap();
    fs::write(
        dir.path().join("nested/clonamic.json"),
        fs::read(fixtures.join("memory-disabled.json")).unwrap(),
    )
    .unwrap();
    let resolution = resolve_plugins(
        &resolve_paths(
            Some(fixtures.join("all-enabled.json")),
            Some(fixtures.join("memory-disabled.json")),
            None,
        ),
        "codex",
        &all_installed(),
    )
    .unwrap();
    assert!(!resolution.plugin("clonamic-memory").unwrap().configured);
    let expected_configuration = fixtures
        .join("memory-disabled.json")
        .to_string_lossy()
        .into_owned();
    assert_eq!(
        resolution.configuration.as_deref(),
        Some(expected_configuration.as_str())
    );

    let project_wins = resolve_plugins(
        &resolve_paths(
            Some(fixtures.join("all-enabled.json")),
            Some(fixtures.join("memory-disabled.json")),
            Some(fixtures.join("all-enabled.json")),
        ),
        "codex",
        &all_installed(),
    )
    .unwrap();
    assert!(project_wins.plugin("clonamic-memory").unwrap().configured);

    let undiscovered =
        resolve_plugins(&resolve_paths(None, None, None), "codex", &all_installed()).unwrap();
    assert!(undiscovered.plugin("clonamic-memory").unwrap().configured);
}

#[test]
fn invalid_highest_config_fails_closed_without_lower_fallback() {
    let root = repository_root();
    let fixtures = root.join("tests/fixtures/plugin-config");
    for invalid in [
        "invalid-missing-toggle.json",
        "invalid-core-toggle.json",
        "invalid-wrong-type.json",
        "invalid-json.json",
    ] {
        let resolution = resolve_plugins(
            &resolve_paths(
                Some(fixtures.join("all-enabled.json")),
                Some(fixtures.join("memory-disabled.json")),
                Some(fixtures.join(invalid)),
            ),
            "codex",
            &all_installed(),
        )
        .unwrap();
        assert_eq!(resolution.status, ResolutionStatus::InvalidConfig);
        assert!(
            resolution
                .plugin("clonamic-herness-plugin")
                .unwrap()
                .effective
        );
        for plugin in resolution.plugins.iter().filter(|plugin| !plugin.required) {
            assert!(!plugin.effective);
            assert_eq!(plugin.reason, "invalid_config");
        }
    }
}

#[test]
fn plugin_resolution_distinguishes_installation_dependencies_and_effective_scope() {
    let root = repository_root();
    let fixtures = root.join("tests/fixtures/plugin-config");
    let installed = ["clonamic-memory"]
        .into_iter()
        .map(str::to_string)
        .collect();
    let resolution = resolve_plugins(
        &resolve_paths(Some(fixtures.join("all-enabled.json")), None, None),
        "codex",
        &installed,
    )
    .unwrap();
    assert!(resolution.plugin("clonamic-memory").unwrap().installed);
    let development = resolution.plugin("clonamic-code-plugin").unwrap();
    assert!(development.configured && development.platform_supported);
    assert!(!development.installed || !development.effective);
    assert_eq!(development.reason, "enabled_but_unavailable");

    let dir = tempdir().unwrap();
    let mut catalog: Value =
        serde_json::from_slice(&fs::read(root.join("catalog/plugins.json")).unwrap()).unwrap();
    catalog["plugins"][1]["dependencies"] =
        serde_json::json!(["plugins/clonamic-preprocessing/plugin.json"]);
    let catalog_path = dir.path().join("catalog.json");
    fs::write(&catalog_path, serde_json::to_vec(&catalog).unwrap()).unwrap();
    let mut config: Value =
        serde_json::from_slice(&fs::read(fixtures.join("all-enabled.json")).unwrap()).unwrap();
    config["plugins"]["clonamic-preprocessing"] = Value::Bool(false);
    let config_path = dir.path().join("config.json");
    fs::write(&config_path, serde_json::to_vec(&config).unwrap()).unwrap();
    let dependency_resolution = resolve_plugins(
        &ResolvePaths {
            catalog: catalog_path,
            manifest_root: root,
            default_config: Some(config_path),
            user_config: None,
            project_config: None,
        },
        "codex",
        &all_installed(),
    )
    .unwrap();
    let development = dependency_resolution
        .plugin("clonamic-code-plugin")
        .unwrap();
    assert_eq!(development.dependencies, vec!["clonamic-preprocessing"]);
    assert!(!development.dependencies_ready);
    assert!(!development.effective);
    assert_eq!(development.reason, "enabled_but_unavailable");
}

#[test]
fn disabled_plugins_only_reduce_existing_automation_scope() {
    let root = repository_root();
    let fixtures = root.join("tests/fixtures/plugin-config");
    let disabled = resolve_plugins(
        &resolve_paths(
            Some(fixtures.join("all-enabled.json")),
            Some(fixtures.join("memory-disabled.json")),
            None,
        ),
        "codex",
        &all_installed(),
    )
    .unwrap();
    let current: BTreeSet<String> = ["clonamic-code-plugin", "clonamic-memory"]
        .into_iter()
        .map(str::to_string)
        .collect();
    assert_eq!(
        reduce_automation_scope(&disabled, &current),
        ["clonamic-code-plugin"]
            .into_iter()
            .map(str::to_string)
            .collect()
    );
    let enabled = resolve_plugins(
        &resolve_paths(Some(fixtures.join("all-enabled.json")), None, None),
        "codex",
        &all_installed(),
    )
    .unwrap();
    let narrow = ["clonamic-memory"]
        .into_iter()
        .map(str::to_string)
        .collect();
    assert_eq!(reduce_automation_scope(&enabled, &narrow), narrow);
}

#[test]
fn resolve_plugins_cli_is_reproducible_and_reports_each_dimension() {
    let root = repository_root();
    let dir = tempdir().unwrap();
    let installed = dir.path().join("installed.json");
    fs::write(
        &installed,
        serde_json::to_vec(&serde_json::json!({"installed": all_installed()})).unwrap(),
    )
    .unwrap();
    let args = vec![
        "resolve-plugins".to_string(),
        root.join("catalog/plugins.json")
            .to_string_lossy()
            .into_owned(),
        root.to_string_lossy().into_owned(),
        root.join("clonamic.json").to_string_lossy().into_owned(),
        "-".to_string(),
        "-".to_string(),
        "codex".to_string(),
        installed.to_string_lossy().into_owned(),
    ];
    let first = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args(&args)
        .output()
        .unwrap();
    let second = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args(&args)
        .output()
        .unwrap();
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    assert_eq!(first.stdout, second.stdout);
    let payload: Value = serde_json::from_slice(&first.stdout).unwrap();
    let row = &payload["plugins"][0];
    for field in [
        "configured",
        "installed",
        "platform_supported",
        "dependencies",
        "dependencies_ready",
        "runtime_ready",
        "effective",
        "reason",
        "manifest",
    ] {
        assert!(row.get(field).is_some(), "missing {field}");
    }
    let ppt = payload["plugins"]
        .as_array()
        .unwrap()
        .iter()
        .find(|plugin| plugin["name"] == "clonamic-ppt")
        .unwrap();
    assert_eq!(ppt["runtime_ready"], false);
    assert_eq!(ppt["effective"], false);

    fs::write(
        &installed,
        serde_json::to_vec(&serde_json::json!({
            "installed": all_installed(),
            "runtime_ready": all_installed(),
        }))
        .unwrap(),
    )
    .unwrap();
    let ready = Command::new(env!("CARGO_BIN_EXE_clonamic"))
        .args(&args)
        .output()
        .unwrap();
    assert!(ready.status.success());
    let ready_payload: Value = serde_json::from_slice(&ready.stdout).unwrap();
    let ready_ppt = ready_payload["plugins"]
        .as_array()
        .unwrap()
        .iter()
        .find(|plugin| plugin["name"] == "clonamic-ppt")
        .unwrap();
    assert_eq!(ready_ppt["runtime_ready"], true);
    assert_eq!(ready_ppt["effective"], true);
}
