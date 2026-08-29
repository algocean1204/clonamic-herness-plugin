use clonamic_core::approval::{
    ApprovalDecision, ApprovalRequest, Grant, approve, issue, normalize_approval,
};
use clonamic_core::completion::{CompletionItem, CompletionManifest, verify_completion};
use clonamic_core::installation::{InstallRequest, install_router, uninstall_router};
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
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
        "skills/clonamic-router/SKILL.md",
        "skills/clonamic-write-control/SKILL.md",
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
    assert_eq!(object["version"], "0.2.0");
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
        plugin_root: dir.path().join("plugin"),
    })
    .unwrap();
    let installed = fs::read_to_string(&router).unwrap();
    assert!(installed.contains("clonamic:begin"));
    assert!(installed.contains("existing user rules"));

    uninstall_router(&router, &state).unwrap();
    assert_eq!(fs::read(&router).unwrap(), original);
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
        plugin_root: dir.path().join("plugin"),
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
        plugin_root: dir.path().join("plugin"),
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
        plugin_root: dir.path().join("plugin"),
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
            plugin_root: dir.path().join("plugin"),
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
        plugin_root: dir.path().join("plugin"),
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
            plugin_root: dir.path().join("plugin"),
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
            plugin_root: dir.path().join("plugin"),
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
            plugin_root: dir.path().join("plugin"),
        })
        .is_err()
    );
    assert_eq!(fs::read(&target).unwrap(), b"outside\n");
}
