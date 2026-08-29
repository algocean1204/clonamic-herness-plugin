use crate::atomic::{LockGuard, reject_symlink_components, replace};
use crate::provenance::ClaimedAutomation;
use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CredentialPolicy {
    None,
    PlatformAction,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AutomationGrant {
    pub automation_id: String,
    pub definition_digest: String,
    pub scope_digest: String,
    pub targets: BTreeSet<String>,
    pub operations: BTreeSet<String>,
    pub external_effects: BTreeSet<String>,
    pub verification: BTreeSet<String>,
    pub rollback: BTreeSet<String>,
    pub expires_at: u64,
    pub max_runs: u64,
    pub initial_sequence: u64,
    pub credential_policy: CredentialPolicy,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AutomationRunRequest {
    pub automation_id: String,
    pub run_id: String,
    pub definition_digest: String,
    pub scope_digest: String,
    pub targets: BTreeSet<String>,
    pub operations: BTreeSet<String>,
    pub external_effects: BTreeSet<String>,
    pub verification: BTreeSet<String>,
    pub rollback: BTreeSet<String>,
    pub sequence: u64,
    pub platform_action_required: bool,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RunStatus {
    Claimed,
    ReplayRejected,
    NeedsAuthorization,
    WaitingPlatformAction,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RunDecision {
    pub status: RunStatus,
    pub reason: String,
    pub interactive: bool,
    pub write_authorized: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    claim: Option<ClaimedAutomation>,
}

impl RunDecision {
    pub fn claim(&self) -> Option<&ClaimedAutomation> {
        self.claim.as_ref()
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct AutomationState {
    grant: AutomationGrant,
    runs_claimed: u64,
    next_sequence: u64,
    used_run_ids: BTreeSet<String>,
}

pub fn initialize_grant(path: &Path, grant: AutomationGrant) -> Result<()> {
    validate_grant(&grant)?;
    reject_symlink_components(path)?;
    let _lock = LockGuard::acquire(path)?;
    if path.exists() {
        let state: AutomationState = serde_json::from_slice(&fs::read(path)?)?;
        validate_grant(&state.grant)?;
        return if state.grant == grant {
            Ok(())
        } else {
            Err(Error::Invalid("automation grant already exists".into()))
        };
    }
    let state = AutomationState {
        next_sequence: grant.initial_sequence,
        grant,
        runs_claimed: 0,
        used_run_ids: BTreeSet::new(),
    };
    write_state(path, &state)
}

pub fn claim_run(path: &Path, request: AutomationRunRequest, now: u64) -> Result<RunDecision> {
    validate_request(&request)?;
    let _lock = LockGuard::acquire(path)?;
    let mut state: AutomationState = serde_json::from_slice(&fs::read(path)?)?;
    validate_grant(&state.grant)?;

    if state.used_run_ids.contains(&request.run_id) {
        return Ok(decision(RunStatus::ReplayRejected, "run_id_replayed", None));
    }
    if request.automation_id != state.grant.automation_id {
        return Ok(needs("automation_id_mismatch"));
    }
    if request.definition_digest != state.grant.definition_digest {
        return Ok(needs("definition_digest_mismatch"));
    }
    if request.scope_digest != state.grant.scope_digest {
        return Ok(needs("scope_digest_mismatch"));
    }
    if !request.targets.is_subset(&state.grant.targets) {
        return Ok(needs("targets_out_of_scope"));
    }
    if !request.operations.is_subset(&state.grant.operations) {
        return Ok(needs("operations_out_of_scope"));
    }
    if !request
        .external_effects
        .is_subset(&state.grant.external_effects)
    {
        return Ok(needs("external_effects_out_of_scope"));
    }
    if !request.verification.is_subset(&state.grant.verification) {
        return Ok(needs("verification_out_of_scope"));
    }
    if !request.rollback.is_subset(&state.grant.rollback) {
        return Ok(needs("rollback_out_of_scope"));
    }
    if request.sequence != state.next_sequence {
        return Ok(needs("sequence_mismatch"));
    }
    if now > state.grant.expires_at {
        return Ok(needs("grant_expired"));
    }
    if state.runs_claimed >= state.grant.max_runs {
        return Ok(needs("run_limit_reached"));
    }
    if request.platform_action_required {
        return Ok(match state.grant.credential_policy {
            CredentialPolicy::PlatformAction => decision(
                RunStatus::WaitingPlatformAction,
                "platform_action_required",
                None,
            ),
            CredentialPolicy::None => needs("credential_not_granted"),
        });
    }

    let claim = ClaimedAutomation::new(
        request.automation_id.clone(),
        request.run_id.clone(),
        request.scope_digest.clone(),
    );
    state.used_run_ids.insert(request.run_id);
    state.runs_claimed += 1;
    state.next_sequence = state
        .next_sequence
        .checked_add(1)
        .ok_or_else(|| Error::Invalid("automation sequence overflow".into()))?;
    write_state(path, &state)?;
    Ok(decision(RunStatus::Claimed, "claimed", Some(claim)))
}

fn decision(status: RunStatus, reason: &str, claim: Option<ClaimedAutomation>) -> RunDecision {
    RunDecision {
        status,
        reason: reason.into(),
        interactive: false,
        write_authorized: claim.is_some(),
        claim,
    }
}

fn needs(reason: &str) -> RunDecision {
    decision(RunStatus::NeedsAuthorization, reason, None)
}

fn validate_grant(grant: &AutomationGrant) -> Result<()> {
    validate_id(&grant.automation_id, "automation_id")?;
    validate_digest(&grant.definition_digest, "definition_digest")?;
    validate_digest(&grant.scope_digest, "scope_digest")?;
    validate_set(&grant.targets, "targets")?;
    validate_set(&grant.operations, "operations")?;
    validate_set(&grant.verification, "verification")?;
    validate_set(&grant.rollback, "rollback")?;
    validate_optional_set(&grant.external_effects, "external_effects")?;
    if grant.max_runs == 0 {
        return Err(Error::Invalid("max_runs must be positive".into()));
    }
    Ok(())
}

fn validate_request(request: &AutomationRunRequest) -> Result<()> {
    validate_id(&request.automation_id, "automation_id")?;
    validate_id(&request.run_id, "run_id")?;
    validate_digest(&request.definition_digest, "definition_digest")?;
    validate_digest(&request.scope_digest, "scope_digest")?;
    validate_set(&request.targets, "targets")?;
    validate_set(&request.operations, "operations")?;
    validate_set(&request.verification, "verification")?;
    validate_set(&request.rollback, "rollback")?;
    validate_optional_set(&request.external_effects, "external_effects")
}

fn validate_id(value: &str, name: &str) -> Result<()> {
    if value.is_empty() || value.len() > 128 || value.chars().any(char::is_control) {
        return Err(Error::Invalid(format!("{name} is invalid")));
    }
    Ok(())
}

fn validate_digest(value: &str, name: &str) -> Result<()> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(Error::Invalid(format!("{name} must be a SHA-256 digest")));
    }
    Ok(())
}

fn validate_set(values: &BTreeSet<String>, name: &str) -> Result<()> {
    if values.is_empty() {
        return Err(Error::Invalid(format!("{name} is invalid")));
    }
    validate_optional_set(values, name)
}

fn validate_optional_set(values: &BTreeSet<String>, name: &str) -> Result<()> {
    if values
        .iter()
        .any(|value| value.is_empty() || value.len() > 256 || value.chars().any(char::is_control))
    {
        return Err(Error::Invalid(format!("{name} is invalid")));
    }
    Ok(())
}

fn write_state(path: &Path, state: &AutomationState) -> Result<()> {
    replace(path, &serde_json::to_vec_pretty(state)?)
}
