use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PromptSource {
    User,
    Automation,
    Internal,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum HostSource {
    User,
    Automation,
    Internal,
    Unverified,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DerivedAuthority {
    InteractiveUser,
    PreapprovedAutomation,
    InheritedInternal,
    None,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AutomationPrompt {
    pub automation_id: String,
    pub run_id: String,
    pub scope_digest: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PromptEnvelope {
    pub prompt_id: String,
    pub session_id: String,
    pub claimed_source: PromptSource,
    pub body: String,
    pub body_sha256: String,
    pub received_at: u64,
    pub parent_prompt_id: Option<String>,
    pub automation: Option<AutomationPrompt>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScopeAuthority {
    prompt_id: String,
    session_id: String,
    authority: DerivedAuthority,
    scope: BTreeSet<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ValidatedPrompt {
    pub(crate) envelope: PromptEnvelope,
    pub(crate) trusted_source: HostSource,
    pub(crate) authority: DerivedAuthority,
    pub(crate) scope: BTreeSet<String>,
    automation_candidate: bool,
}

impl ValidatedPrompt {
    pub fn envelope(&self) -> &PromptEnvelope {
        &self.envelope
    }

    pub fn trusted_source(&self) -> HostSource {
        self.trusted_source
    }

    pub fn authority(&self) -> DerivedAuthority {
        self.authority
    }

    pub fn scope(&self) -> &BTreeSet<String> {
        &self.scope
    }

    pub fn automation_candidate(&self) -> bool {
        self.automation_candidate
    }

    pub fn scope_authority(&self, scope: BTreeSet<String>) -> ScopeAuthority {
        ScopeAuthority {
            prompt_id: self.envelope.prompt_id.clone(),
            session_id: self.envelope.session_id.clone(),
            authority: self.authority,
            scope,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ClaimedAutomation {
    automation_id: String,
    run_id: String,
    scope_digest: String,
}

impl ClaimedAutomation {
    pub(crate) fn new(automation_id: String, run_id: String, scope_digest: String) -> Self {
        Self {
            automation_id,
            run_id,
            scope_digest,
        }
    }
}

pub fn sha256_hex(data: &[u8]) -> String {
    format!("{:x}", Sha256::digest(data))
}

pub fn parse_envelope(data: &[u8]) -> Result<PromptEnvelope> {
    Ok(serde_json::from_slice(data)?)
}

pub fn classify_prompt(
    envelope: PromptEnvelope,
    host_source: HostSource,
    parent: Option<&ScopeAuthority>,
    assignment: Option<&BTreeSet<String>>,
) -> Result<ValidatedPrompt> {
    validate_envelope(&envelope)?;
    let mut validated = ValidatedPrompt {
        envelope,
        trusted_source: HostSource::Unverified,
        authority: DerivedAuthority::None,
        scope: BTreeSet::new(),
        automation_candidate: false,
    };
    if !source_matches(validated.envelope.claimed_source, host_source) {
        return Ok(validated);
    }
    validated.trusted_source = host_source;

    match validated.envelope.claimed_source {
        PromptSource::User => {
            if validated.envelope.automation.is_some()
                || validated.envelope.parent_prompt_id.is_some()
            {
                return Err(Error::Invalid("user prompt metadata is invalid".into()));
            }
            validated.authority = DerivedAuthority::InteractiveUser;
        }
        PromptSource::Automation => {
            let automation = validated
                .envelope
                .automation
                .as_ref()
                .ok_or_else(|| Error::Invalid("automation metadata is required".into()))?;
            validate_id(&automation.automation_id, "automation_id")?;
            validate_id(&automation.run_id, "run_id")?;
            validate_digest(&automation.scope_digest, "scope_digest")?;
            if validated.envelope.parent_prompt_id.is_some() {
                return Err(Error::Invalid(
                    "automation parent_prompt_id is invalid".into(),
                ));
            }
            validated.automation_candidate = true;
        }
        PromptSource::Internal => {
            if validated.envelope.automation.is_some() {
                return Err(Error::Invalid(
                    "internal automation metadata is invalid".into(),
                ));
            }
            validate_id(
                validated
                    .envelope
                    .parent_prompt_id
                    .as_deref()
                    .ok_or_else(|| Error::Invalid("parent_prompt_id is required".into()))?,
                "parent_prompt_id",
            )?;
            let (Some(parent), Some(assignment)) = (parent, assignment) else {
                return Ok(validated);
            };
            validate_id(&parent.prompt_id, "parent.prompt_id")?;
            validate_id(&parent.session_id, "parent.session_id")?;
            if validated.envelope.parent_prompt_id.as_deref() != Some(parent.prompt_id.as_str())
                || validated.envelope.session_id != parent.session_id
            {
                return Ok(validated);
            }
            validated.scope = parent.scope.intersection(assignment).cloned().collect();
            if parent.authority != DerivedAuthority::None && !validated.scope.is_empty() {
                validated.authority = DerivedAuthority::InheritedInternal;
            }
        }
    }
    Ok(validated)
}

pub fn authorize_automation(
    mut prompt: ValidatedPrompt,
    claim: &ClaimedAutomation,
) -> Result<ValidatedPrompt> {
    if prompt.trusted_source != HostSource::Automation || prompt.authority != DerivedAuthority::None
    {
        return Err(Error::Invalid(
            "prompt is not an automation candidate".into(),
        ));
    }
    let automation = prompt
        .envelope
        .automation
        .as_ref()
        .ok_or_else(|| Error::Invalid("automation metadata is required".into()))?;
    if automation.automation_id != claim.automation_id
        || automation.run_id != claim.run_id
        || automation.scope_digest != claim.scope_digest
    {
        return Err(Error::Invalid(
            "automation claim does not match prompt".into(),
        ));
    }
    prompt.authority = DerivedAuthority::PreapprovedAutomation;
    prompt.automation_candidate = false;
    Ok(prompt)
}

fn validate_envelope(envelope: &PromptEnvelope) -> Result<()> {
    validate_id(&envelope.prompt_id, "prompt_id")?;
    validate_id(&envelope.session_id, "session_id")?;
    validate_digest(&envelope.body_sha256, "body_sha256")?;
    if envelope.body_sha256 != sha256_hex(envelope.body.as_bytes()) {
        return Err(Error::Invalid("body_sha256 mismatch".into()));
    }
    Ok(())
}

fn source_matches(claimed: PromptSource, trusted: HostSource) -> bool {
    matches!(
        (claimed, trusted),
        (PromptSource::User, HostSource::User)
            | (PromptSource::Automation, HostSource::Automation)
            | (PromptSource::Internal, HostSource::Internal)
    )
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
