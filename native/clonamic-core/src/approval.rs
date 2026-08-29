use crate::atomic::{LockGuard, reject_symlink_components, replace};
use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ApprovalRequest {
    pub session_id: String,
    pub scope_digest: String,
    pub expires_at: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Grant {
    pub code: String,
    pub session_id: String,
    pub scope_digest: String,
    pub expires_at: u64,
    pub active: bool,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalDecision {
    Activated,
    AlreadyActive,
    MultiplePending,
    CodeMismatch,
    Expired,
    SessionMismatch,
}

pub fn normalize_approval(input: &str) -> Result<String> {
    let mut value = input.trim();
    if value.starts_with('`') && value.ends_with('`') && value.len() >= 2 {
        value = value[1..value.len() - 1].trim();
    }
    let compact: String = value
        .replace('：', ":")
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect();
    let code = compact
        .strip_prefix("승인:")
        .or_else(|| compact.strip_prefix("APPROVE:"))
        .ok_or_else(|| Error::Invalid("approval must use 승인:CODE".into()))?
        .to_ascii_uppercase();
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(Error::Invalid(
            "approval code must be six hexadecimal characters".into(),
        ));
    }
    Ok(code)
}

pub fn issue(set_root: &Path, path: &Path, request: ApprovalRequest) -> Result<Grant> {
    validate_request(&request)?;
    let set_root = validate_state_location(set_root, path)?;
    let _set_lock = LockGuard::acquire(&set_root.join(".clonamic-approval-set.state"))?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| Error::Invalid("system clock is before the Unix epoch".into()))?
        .as_nanos();
    let mut digest = Sha256::new();
    digest.update(request.session_id.as_bytes());
    digest.update(request.scope_digest.as_bytes());
    digest.update(request.expires_at.to_le_bytes());
    digest.update(nonce.to_le_bytes());
    digest.update(std::process::id().to_le_bytes());
    let code = format!("{:X}", digest.finalize())[..6].to_string();
    let grant = Grant {
        code,
        session_id: request.session_id,
        scope_digest: request.scope_digest,
        expires_at: request.expires_at,
        active: false,
    };
    atomic_json(path, &grant)?;
    Ok(grant)
}

pub fn approve(
    set_root: &Path,
    path: &Path,
    session_id: &str,
    input: &str,
    now: u64,
) -> Result<ApprovalDecision> {
    let set_root = validate_state_location(set_root, path)?;
    let _set_lock = LockGuard::acquire(&set_root.join(".clonamic-approval-set.state"))?;
    let _lock = LockGuard::acquire(path)?;
    let mut grant: Grant = serde_json::from_slice(&fs::read(path)?)?;
    if grant.session_id != session_id {
        return Ok(ApprovalDecision::SessionMismatch);
    }
    if grant.expires_at < now {
        return Ok(ApprovalDecision::Expired);
    }
    let code = if plain_approval(input) {
        if grant.active {
            return Ok(ApprovalDecision::AlreadyActive);
        }
        if pending_count(&set_root, session_id, now)? != 1 {
            return Ok(ApprovalDecision::MultiplePending);
        }
        grant.code.clone()
    } else {
        normalize_approval(input)?
    };
    if grant.code != code {
        return Ok(ApprovalDecision::CodeMismatch);
    }
    if grant.active {
        return Ok(ApprovalDecision::AlreadyActive);
    }
    grant.active = true;
    atomic_json(path, &grant)?;
    Ok(ApprovalDecision::Activated)
}

fn validate_state_location(set_root: &Path, path: &Path) -> Result<PathBuf> {
    reject_symlink_components(set_root)?;
    reject_symlink_components(path)?;
    fs::create_dir_all(set_root)?;
    let set_root = fs::canonicalize(set_root)?;
    let parent = path
        .parent()
        .filter(|candidate| !candidate.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let parent = fs::canonicalize(parent)?;
    if parent != set_root {
        return Err(Error::Invalid(
            "approval state must be a direct child of the declared set root".into(),
        ));
    }
    Ok(set_root)
}

fn pending_count(set_root: &Path, session_id: &str, now: u64) -> Result<usize> {
    let mut count = 0;
    for entry in fs::read_dir(set_root)? {
        let entry = entry?;
        let metadata = entry.file_type()?;
        if !metadata.is_file() {
            continue;
        }
        let Ok(data) = fs::read(entry.path()) else {
            continue;
        };
        let Ok(candidate) = serde_json::from_slice::<Grant>(&data) else {
            continue;
        };
        if candidate.session_id == session_id && !candidate.active && candidate.expires_at >= now {
            count += 1;
        }
    }
    Ok(count)
}

fn plain_approval(input: &str) -> bool {
    let mut value = input.trim();
    if value.starts_with('`') && value.ends_with('`') && value.len() >= 2 {
        value = value[1..value.len() - 1].trim();
    }
    value
        .replace('：', ":")
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect::<String>()
        == "승인"
}

fn validate_request(request: &ApprovalRequest) -> Result<()> {
    if request.session_id.trim().is_empty() {
        return Err(Error::Invalid("session_id is required".into()));
    }
    if request.scope_digest.len() != 64
        || !request
            .scope_digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(Error::Invalid(
            "scope_digest must be a SHA-256 hexadecimal digest".into(),
        ));
    }
    Ok(())
}

fn atomic_json(path: &Path, value: &impl Serialize) -> Result<()> {
    let data = serde_json::to_vec_pretty(value)?;
    replace(path, &data)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    use tempfile::tempdir;

    #[test]
    fn lock_cleanup_preserves_a_replacement_it_did_not_create() {
        let dir = tempdir().unwrap();
        let state = dir.path().join("grant.json");
        let lock = state.with_extension("lock");
        let guard = LockGuard::acquire(&state).unwrap();
        fs::remove_file(&lock).unwrap();
        fs::write(&lock, b"foreign").unwrap();

        drop(guard);

        assert_eq!(fs::read(&lock).unwrap(), b"foreign");
    }

    #[test]
    fn lock_creation_rejects_a_symlink_and_uses_private_permissions() {
        let dir = tempdir().unwrap();
        let state = dir.path().join("grant.json");
        let lock = state.with_extension("lock");
        let target = dir.path().join("target");
        fs::write(&target, b"foreign").unwrap();
        symlink(&target, &lock).unwrap();
        assert!(LockGuard::acquire(&state).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"foreign");

        fs::remove_file(&lock).unwrap();
        let guard = LockGuard::acquire(&state).unwrap();
        assert_eq!(
            fs::metadata(&lock).unwrap().permissions().mode() & 0o777,
            0o600
        );
        drop(guard);
    }
}
