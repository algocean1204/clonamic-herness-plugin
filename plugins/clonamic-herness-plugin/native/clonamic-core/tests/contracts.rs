use clonamic_core::approval::{
    ApprovalDecision, ApprovalRequest, approve, issue, normalize_approval,
};
use clonamic_core::completion::{CompletionItem, CompletionManifest, verify_completion};
use clonamic_core::installation::{InstallRequest, install_router, uninstall_router};
use std::fs;
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
