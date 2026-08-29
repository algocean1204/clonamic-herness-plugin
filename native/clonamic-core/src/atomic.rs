use crate::{Error, Result};
use std::fs;
use std::io::Write;
use std::path::Path;
use tempfile::{Builder, NamedTempFile};

#[cfg(unix)]
use std::fs::File;
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

#[cfg(unix)]
fn sync_parent(parent: &Path) -> Result<()> {
    File::open(parent)?.sync_all()?;
    Ok(())
}

#[cfg(not(unix))]
fn sync_parent(_parent: &Path) -> Result<()> {
    Ok(())
}
