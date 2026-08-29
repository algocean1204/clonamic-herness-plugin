use clonamic_core::approval::{ApprovalRequest, approve, issue, normalize_approval};
use clonamic_core::automation::{
    AutomationGrant, AutomationRunRequest, claim_run, initialize_grant,
};
use clonamic_core::completion::{CompletionManifest, verify_completion};
use clonamic_core::installation::{InstallRequest, install_router, uninstall_router};
use clonamic_core::plugin_config::{ResolvePaths, resolve_plugins};
use clonamic_core::provenance::{
    HostSource, PromptEnvelope, ScopeAuthority, authorize_automation, classify_prompt,
    parse_envelope,
};
use clonamic_core::session::{SessionUpdate, update_session};
use clonamic_core::{Error, Result};
use serde::Deserialize;
use serde_json::json;
use std::collections::BTreeSet;
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
        [
            command,
            catalog,
            manifest_root,
            default,
            user,
            project,
            platform,
            installed,
        ] if command == "resolve-plugins" => {
            let installed: InstalledDocument = serde_json::from_slice(&fs::read(installed)?)?;
            let resolution = resolve_plugins(
                &ResolvePaths {
                    catalog: PathBuf::from(catalog),
                    manifest_root: PathBuf::from(manifest_root),
                    default_config: optional_path(default),
                    user_config: optional_path(user),
                    project_config: optional_path(project),
                },
                platform,
                &installed.installed,
            )?;
            println!("{}", serde_json::to_string(&resolution)?);
        }
        [command, input, host, context] if command == "classify-prompt" => {
            let envelope = parse_envelope(&fs::read(input)?)?;
            let (parent, assignment) = prompt_context(context)?;
            let validated = classify_prompt(
                envelope,
                parse_host_source(host)?,
                parent.as_ref(),
                assignment.as_ref(),
            )?;
            println!("{}", serde_json::to_string(&validated)?);
        }
        [command, state, grant] if command == "automation-init" => {
            let grant: AutomationGrant = serde_json::from_slice(&fs::read(grant)?)?;
            initialize_grant(Path::new(state), grant)?;
            println!("{}", json!({"initialized": true}));
        }
        [command, state, request, now] if command == "automation-claim" => {
            let request: AutomationRunRequest = serde_json::from_slice(&fs::read(request)?)?;
            let decision = claim_run(Path::new(state), request, parse_u64(now, "now")?)?;
            println!("{}", serde_json::to_string(&decision)?);
        }
        [command, session, input, state, request, now, limit]
            if command == "automation-session-update" =>
        {
            let envelope = parse_envelope(&fs::read(input)?)?;
            let candidate = classify_prompt(envelope, HostSource::Automation, None, None)?;
            let request: AutomationRunRequest = serde_json::from_slice(&fs::read(request)?)?;
            let decision = claim_run(Path::new(state), request, parse_u64(now, "now")?)?;
            if let Some(claim) = decision.claim() {
                let prompt = authorize_automation(candidate, claim)?;
                update_session(
                    Path::new(session),
                    SessionUpdate::new(prompt),
                    parse_limit(limit)?,
                )?;
            }
            println!("{}", serde_json::to_string(&decision)?);
        }
        [command, session, input, host, context, limit] if command == "session-update" => {
            let envelope = parse_envelope(&fs::read(input)?)?;
            let (parent, assignment) = prompt_context(context)?;
            let prompt = classify_prompt(
                envelope,
                parse_host_source(host)?,
                parent.as_ref(),
                assignment.as_ref(),
            )?;
            update_session(
                Path::new(session),
                SessionUpdate::new(prompt),
                parse_limit(limit)?,
            )?;
            println!("{}", json!({"updated": true, "session": session}));
        }
        [command, input] if command == "normalize-approval" => {
            println!("{}", normalize_approval(input)?);
        }
        [command, set_root, state, session, digest, expires] if command == "issue" => {
            let grant = issue(
                Path::new(set_root),
                Path::new(state),
                ApprovalRequest {
                    session_id: session.clone(),
                    scope_digest: digest.clone(),
                    expires_at: parse_u64(expires, "expires_at")?,
                },
            )?;
            println!("{}", serde_json::to_string(&grant)?);
        }
        [command, set_root, state, session, input, now] if command == "approve" => {
            let decision = approve(
                Path::new(set_root),
                Path::new(state),
                session,
                input,
                parse_u64(now, "now")?,
            )?;
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

fn parse_limit(value: &str) -> Result<Option<usize>> {
    if value == "-" {
        return Ok(None);
    }
    Ok(Some(value.parse().map_err(|_| {
        Error::Invalid("limit must be an unsigned integer".into())
    })?))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PromptContext {
    parent: PromptEnvelope,
    parent_host_source: HostSource,
    parent_scope: BTreeSet<String>,
    assignment: BTreeSet<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InstalledDocument {
    installed: BTreeSet<String>,
}

fn optional_path(value: &str) -> Option<PathBuf> {
    (value != "-").then(|| PathBuf::from(value))
}

fn prompt_context(path: &str) -> Result<(Option<ScopeAuthority>, Option<BTreeSet<String>>)> {
    if path == "-" {
        return Ok((None, None));
    }
    let context: PromptContext = serde_json::from_slice(&fs::read(path)?)?;
    let parent = classify_prompt(context.parent, context.parent_host_source, None, None)?;
    Ok((
        Some(parent.scope_authority(context.parent_scope)),
        Some(context.assignment),
    ))
}

fn parse_host_source(value: &str) -> Result<HostSource> {
    match value {
        "user" => Ok(HostSource::User),
        "automation" => Ok(HostSource::Automation),
        "internal" => Ok(HostSource::Internal),
        "unverified" => Ok(HostSource::Unverified),
        _ => Err(Error::Invalid("invalid host source".into())),
    }
}

fn usage() -> &'static str {
    "usage: clonamic <resolve-plugins|classify-prompt|automation-init|automation-claim|automation-session-update|session-update|normalize-approval|issue|approve|verify|install-router|uninstall-router|doctor> ..."
}
