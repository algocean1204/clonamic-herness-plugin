use crate::atomic::{private_temp, reject_symlink_components, replace};
use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

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

pub fn issue(path: &Path, request: ApprovalRequest) -> Result<Grant> {
    validate_request(&request)?;
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

pub fn approve(path: &Path, session_id: &str, input: &str, now: u64) -> Result<ApprovalDecision> {
    let code = normalize_approval(input)?;
    let _lock = LockGuard::acquire(path)?;
    let mut grant: Grant = serde_json::from_slice(&fs::read(path)?)?;
    if grant.session_id != session_id {
        return Ok(ApprovalDecision::SessionMismatch);
    }
    if grant.expires_at < now {
        return Ok(ApprovalDecision::Expired);
    }
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

struct LockGuard {
    path: PathBuf,
    token: Vec<u8>,
    file: Option<File>,
}

impl LockGuard {
    fn acquire(state: &Path) -> Result<Self> {
        let path = state.with_extension("lock");
        let parent = path
            .parent()
            .ok_or_else(|| Error::Invalid("lock path has no parent".into()))?;
        reject_symlink_components(&path)?;
        let token = lock_token(state);
        for _ in 0..200 {
            let mut temp = private_temp(parent)?;
            temp.as_file_mut().write_all(&token)?;
            temp.as_file().sync_all()?;
            match temp.persist_noclobber(&path) {
                Ok(file) => {
                    return Ok(Self {
                        path,
                        token,
                        file: Some(file),
                    });
                }
                Err(error) if error.error.kind() == std::io::ErrorKind::AlreadyExists => {
                    drop(error.file);
                    if fs::symlink_metadata(&path)
                        .is_ok_and(|metadata| metadata.file_type().is_symlink())
                    {
                        return Err(Error::Invalid(format!(
                            "lock path is a symlink: {}",
                            path.display()
                        )));
                    }
                    thread::sleep(Duration::from_millis(5));
                }
                Err(error) => {
                    let source = error.error;
                    drop(error.file);
                    return Err(source.into());
                }
            }
        }
        Err(Error::Invalid("approval state is busy".into()))
    }
}

fn lock_token(state: &Path) -> Vec<u8> {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_nanos());
    let mut digest = Sha256::new();
    digest.update(state.as_os_str().to_string_lossy().as_bytes());
    digest.update(std::process::id().to_le_bytes());
    digest.update(nonce.to_le_bytes());
    digest.update(NEXT.fetch_add(1, Ordering::Relaxed).to_le_bytes());
    format!("{:x}", digest.finalize()).into_bytes()
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        drop(self.file.take());
        let owned = fs::symlink_metadata(&self.path).is_ok_and(|metadata| {
            metadata.file_type().is_file()
                && fs::read(&self.path).is_ok_and(|content| content == self.token)
        });
        if owned {
            let _ = fs::remove_file(&self.path);
        }
    }
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
