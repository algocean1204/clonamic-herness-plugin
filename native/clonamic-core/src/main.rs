use clonamic_core::approval::{ApprovalRequest, approve, issue, normalize_approval};
use clonamic_core::completion::{CompletionManifest, verify_completion};
use clonamic_core::installation::{InstallRequest, install_router, uninstall_router};
use clonamic_core::{Error, Result};
use serde_json::json;
use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    if let Err(error) = run(std::env::args().skip(1).collect()) {
        eprintln!("clonamic: {error}");
        std::process::exit(2);
    }
}

fn run(args: Vec<String>) -> Result<()> {
    match args.as_slice() {
        [command, input] if command == "normalize-approval" => {
            println!("{}", normalize_approval(input)?);
        }
        [command, state, session, digest, expires] if command == "issue" => {
            let grant = issue(
                Path::new(state),
                ApprovalRequest {
                    session_id: session.clone(),
                    scope_digest: digest.clone(),
                    expires_at: parse_u64(expires, "expires_at")?,
                },
            )?;
            println!("{}", serde_json::to_string(&grant)?);
        }
        [command, state, session, input, now] if command == "approve" => {
            let decision = approve(Path::new(state), session, input, parse_u64(now, "now")?)?;
            println!("{}", serde_json::to_string(&decision)?);
        }
        [command, manifest] if command == "verify" => {
            let manifest: CompletionManifest = serde_json::from_slice(&fs::read(manifest)?)?;
            let verdict = verify_completion(&manifest);
            println!("{}", serde_json::to_string(&verdict)?);
            if !verdict.complete {
                std::process::exit(3);
            }
        }
        [command, router, state, plugin_root] if command == "install-router" => {
            install_router(InstallRequest {
                router: PathBuf::from(router),
                state: PathBuf::from(state),
                plugin_root: PathBuf::from(plugin_root),
            })?;
            println!("{}", json!({"installed": true, "router": router}));
        }
        [command, router, state] if command == "uninstall-router" => {
            uninstall_router(Path::new(router), Path::new(state))?;
            println!("{}", json!({"uninstalled": true, "router": router}));
        }
        [command, plugin_root] if command == "doctor" => {
            let root = Path::new(plugin_root);
            let required = [
                "plugin.json",
                "clonamic-herness-plugin.md",
                "skills/clonamic-router/SKILL.md",
                "skills/clonamic-intent-guard/SKILL.md",
                "skills/clonamic-team-control/SKILL.md",
                "skills/clonamic-write-control/SKILL.md",
                "skills/clonamic-completion-check/SKILL.md",
                "skills/clonamic-report/SKILL.md",
                "skills/clonamic-market/SKILL.md",
            ];
            let missing = required
                .iter()
                .filter(|relative| !root.join(relative).is_file())
                .copied()
                .collect::<Vec<_>>();
            println!("{}", json!({"ok": missing.is_empty(), "missing": missing}));
            if !missing.is_empty() {
                std::process::exit(4);
            }
        }
        _ => return Err(Error::Invalid(usage().into())),
    }
    Ok(())
}

fn parse_u64(value: &str, name: &str) -> Result<u64> {
    value
        .parse()
        .map_err(|_| Error::Invalid(format!("{name} must be an unsigned integer")))
}

fn usage() -> &'static str {
    "usage: clonamic <normalize-approval|issue|approve|verify|install-router|uninstall-router|doctor> ..."
}
