use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
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
    let parent = path
        .parent()
        .ok_or_else(|| Error::Invalid("state path has no parent".into()))?;
    fs::create_dir_all(parent)?;
    let temp = path.with_extension(format!("tmp.{}", std::process::id()));
    let data = serde_json::to_vec_pretty(value)?;
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&temp)?;
    file.write_all(&data)?;
    file.sync_all()?;
    fs::rename(&temp, path)?;
    Ok(())
}

struct LockGuard {
    path: PathBuf,
}

impl LockGuard {
    fn acquire(state: &Path) -> Result<Self> {
        let path = state.with_extension("lock");
        for _ in 0..200 {
            match OpenOptions::new().create_new(true).write(true).open(&path) {
                Ok(_) => return Ok(Self { path }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    thread::sleep(Duration::from_millis(5));
                }
                Err(error) => return Err(error.into()),
            }
        }
        Err(Error::Invalid("approval state is busy".into()))
    }
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}
