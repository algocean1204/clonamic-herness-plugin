use crate::{Error, Result};
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tempfile::{Builder, NamedTempFile};

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;

pub(crate) fn replace(path: &Path, data: &[u8]) -> Result<()> {
    reject_symlink_components(path)?;
    let parent = path
        .parent()
        .ok_or_else(|| Error::Invalid("path has no parent".into()))?;
    fs::create_dir_all(parent)?;
    let mut temp = private_temp(parent)?;
    temp.as_file_mut().write_all(data)?;
    temp.as_file().sync_all()?;
    match temp.persist(path) {
        Ok(_) => {}
        Err(error) => {
            let source = error.error;
            drop(error.file);
            return Err(source.into());
        }
    }
    sync_parent(parent)?;
    Ok(())
}

pub(crate) fn private_temp(parent: &Path) -> Result<NamedTempFile> {
    fs::create_dir_all(parent)?;
    let mut builder = Builder::new();
    builder.prefix(".tmp-");
    #[cfg(unix)]
    builder.permissions(fs::Permissions::from_mode(0o600));
    Ok(builder.tempfile_in(parent)?)
}

pub(crate) fn reject_symlink_components(path: &Path) -> Result<()> {
    for candidate in path.ancestors() {
        // Root-level aliases are platform-managed prefixes; inspect every component below them.
        if candidate.is_absolute()
            && candidate
                .parent()
                .is_some_and(|parent| parent.parent().is_none())
        {
            break;
        }
        match fs::symlink_metadata(candidate) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(Error::Invalid(format!(
                    "path component is a symlink: {}",
                    candidate.display()
                )));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

pub(crate) struct LockGuard {
    path: PathBuf,
    token: Vec<u8>,
    file: Option<File>,
}

impl LockGuard {
    pub(crate) fn acquire(state: &Path) -> Result<Self> {
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
        Err(Error::Invalid("state is busy".into()))
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

#[cfg(unix)]
fn sync_parent(parent: &Path) -> Result<()> {
    File::open(parent)?.sync_all()?;
    Ok(())
}

#[cfg(not(unix))]
fn sync_parent(_parent: &Path) -> Result<()> {
    Ok(())
}
