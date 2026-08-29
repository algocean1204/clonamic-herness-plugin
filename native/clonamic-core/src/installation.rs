use crate::atomic::{reject_symlink_components, replace};
use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};

const BEGIN: &str = "<!-- clonamic:begin -->";
const END: &str = "<!-- clonamic:end -->";

#[derive(Clone, Debug)]
pub struct InstallRequest {
    pub router: PathBuf,
    pub state: PathBuf,
    pub plugin_root: PathBuf,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct InstallState {
    router: PathBuf,
    backup: PathBuf,
    installed_hash: String,
}

pub fn install_router(request: InstallRequest) -> Result<()> {
    reject_symlink_components(&request.router)?;
    reject_symlink_components(&request.state)?;
    let original = if request.router.exists() {
        fs::read(&request.router)?
    } else {
        Vec::new()
    };
    let original_text = String::from_utf8(original.clone())
        .map_err(|_| Error::Invalid("router must be UTF-8".into()))?;
    if original_text.contains(BEGIN) || original_text.contains(END) {
        let state: InstallState = serde_json::from_slice(&fs::read(&request.state)?)?;
        if state.router == request.router && state.installed_hash == hash(original_text.as_bytes())
        {
            return Ok(());
        }
        return Err(Error::Invalid(
            "managed router block exists but install state does not match".into(),
        ));
    }
    let state_parent = request
        .state
        .parent()
        .ok_or_else(|| Error::Invalid("state path has no parent".into()))?;
    fs::create_dir_all(state_parent)?;
    if let Some(parent) = request.router.parent() {
        fs::create_dir_all(parent)?;
    }
    let backup = request.state.with_extension("backup");
    atomic_write(&backup, &original)?;
    let block = format!(
        "{BEGIN}\nFor persistent writes, load the installed clonamic-write-control skill. Before reporting completion, load clonamic-completion-check. External AI executors run only after an explicit slash command.\nPlugin root: {}\n{END}\n",
        request.plugin_root.display()
    );
    let separator = if original_text.is_empty() || original_text.ends_with('\n') {
        ""
    } else {
        "\n"
    };
    let installed = format!("{original_text}{separator}{block}");
    let state = InstallState {
        router: request.router.clone(),
        backup,
        installed_hash: hash(installed.as_bytes()),
    };
    if let Err(error) = atomic_write(&request.state, &serde_json::to_vec_pretty(&state)?) {
        let _ = fs::remove_file(&state.backup);
        return Err(error);
    }
    if let Err(error) = atomic_write(&request.router, installed.as_bytes()) {
        let _ = fs::remove_file(&request.state);
        let _ = fs::remove_file(&state.backup);
        return Err(error);
    }
    Ok(())
}

pub fn uninstall_router(router: &Path, state_path: &Path) -> Result<()> {
    reject_symlink_components(router)?;
    reject_symlink_components(state_path)?;
    let state: InstallState = serde_json::from_slice(&fs::read(state_path)?)?;
    if state.router != router {
        return Err(Error::Invalid(
            "router path does not match install state".into(),
        ));
    }
    let current = fs::read(router)?;
    if hash(&current) == state.installed_hash {
        atomic_write(router, &fs::read(&state.backup)?)?;
    } else {
        let text = String::from_utf8(current)
            .map_err(|_| Error::Invalid("router must be UTF-8".into()))?;
        let start = text
            .find(BEGIN)
            .ok_or_else(|| Error::Invalid("managed router block is missing".into()))?;
        let end = text[start..]
            .find(END)
            .map(|offset| start + offset + END.len())
            .ok_or_else(|| Error::Invalid("managed router block is incomplete".into()))?;
        let mut restored = text[..start].to_string();
        restored.push_str(text[end..].strip_prefix('\n').unwrap_or(&text[end..]));
        atomic_write(router, restored.as_bytes())?;
    }
    fs::remove_file(state_path)?;
    let _ = fs::remove_file(state.backup);
    Ok(())
}

fn hash(data: &[u8]) -> String {
    format!("{:x}", Sha256::digest(data))
}

fn atomic_write(path: &Path, data: &[u8]) -> Result<()> {
    replace(path, data)
}
