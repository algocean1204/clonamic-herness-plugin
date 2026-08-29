use crate::atomic::{LockGuard, reject_symlink_components, replace};
use crate::provenance::{DerivedAuthority, HostSource, ValidatedPrompt};
use crate::{Error, Result};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

const DEFAULT_EXCERPT_BYTES: usize = 1024;
const MAX_EXCERPT_BYTES: usize = 2048;
const MAX_FILE_BYTES: usize = 2500;

pub struct SessionUpdate {
    pub prompt: ValidatedPrompt,
}

impl SessionUpdate {
    pub fn new(prompt: ValidatedPrompt) -> Self {
        Self { prompt }
    }
}

#[derive(Default)]
struct SessionState {
    session_id: String,
    active_prompt_id: String,
    active_source: String,
    active_authority: String,
    last_user_prompt_id: Option<String>,
    last_user_prompt_source: Option<String>,
    last_user_prompt_label: Option<String>,
    last_user_prompt_sha256: Option<String>,
    last_user_prompt_received_at: Option<u64>,
    last_user_prompt_truncated: bool,
    automation_id: Option<String>,
    automation_run_id: Option<String>,
    scope_digest: Option<String>,
    excerpt: String,
}

pub fn update_session(
    path: &Path,
    update: SessionUpdate,
    excerpt_limit: Option<usize>,
) -> Result<()> {
    reject_symlink_components(path)?;
    let limit = excerpt_limit.unwrap_or(DEFAULT_EXCERPT_BYTES);
    if limit == 0 || limit > MAX_EXCERPT_BYTES {
        return Err(Error::Invalid(
            "excerpt limit must be between 1 and 2048".into(),
        ));
    }
    let prompt = update.prompt;
    let _lock = LockGuard::acquire(path)?;
    reject_symlink_components(path)?;
    let mut state = if path.exists() {
        parse_session(&fs::read_to_string(path)?)?
    } else {
        SessionState::default()
    };
    if !state.session_id.is_empty() && state.session_id != prompt.envelope.session_id {
        return Err(Error::Invalid(
            "session_id does not match existing session".into(),
        ));
    }
    state.session_id = prompt.envelope.session_id.clone();
    state.active_prompt_id = prompt.envelope.prompt_id.clone();
    state.active_source = source_name(prompt.trusted_source).into();
    state.active_authority = authority_name(prompt.authority).into();

    match prompt.authority {
        DerivedAuthority::InteractiveUser => {
            set_last_prompt(&mut state, &prompt, limit);
            state.automation_id = None;
            state.automation_run_id = None;
            state.scope_digest = None;
        }
        DerivedAuthority::PreapprovedAutomation => {
            set_last_prompt(&mut state, &prompt, limit);
            let automation =
                prompt.envelope.automation.as_ref().ok_or_else(|| {
                    Error::Invalid("trusted automation metadata is missing".into())
                })?;
            state.automation_id = Some(automation.automation_id.clone());
            state.automation_run_id = Some(automation.run_id.clone());
            state.scope_digest = Some(automation.scope_digest.clone());
        }
        DerivedAuthority::InheritedInternal | DerivedAuthority::None => {}
    }

    let data = render_bounded(&mut state)?;
    replace(path, data.as_bytes())
}

fn set_last_prompt(state: &mut SessionState, prompt: &ValidatedPrompt, limit: usize) {
    if state
        .last_user_prompt_received_at
        .is_some_and(|received_at| received_at >= prompt.envelope.received_at)
    {
        return;
    }
    state.last_user_prompt_id = Some(prompt.envelope.prompt_id.clone());
    state.last_user_prompt_source = Some(source_name(prompt.trusted_source).into());
    state.last_user_prompt_label = match prompt.authority {
        DerivedAuthority::PreapprovedAutomation => Some("[\"자동화\"]".into()),
        _ => None,
    };
    state.last_user_prompt_sha256 = Some(prompt.envelope.body_sha256.clone());
    state.last_user_prompt_received_at = Some(prompt.envelope.received_at);
    state.excerpt = utf8_prefix(&prompt.envelope.body, limit).into();
    state.last_user_prompt_truncated = state.excerpt.len() < prompt.envelope.body.len();
}

fn render_bounded(state: &mut SessionState) -> Result<String> {
    loop {
        let rendered = render(state)?;
        if rendered.len() <= MAX_FILE_BYTES {
            return Ok(rendered);
        }
        let overflow = rendered.len() - MAX_FILE_BYTES;
        if state.excerpt.is_empty() {
            return Err(Error::Invalid("session metadata exceeds 2500 bytes".into()));
        }
        let next = state.excerpt.len().saturating_sub(overflow.max(1));
        state.excerpt = utf8_prefix(&state.excerpt, next).into();
        state.last_user_prompt_truncated = true;
    }
}

fn render(state: &SessionState) -> Result<String> {
    let string = |value: &str| serde_json::to_string(value).map_err(Error::from);
    let optional = |value: &Option<String>| -> Result<String> {
        value
            .as_ref()
            .map_or_else(|| Ok("null".into()), |value| string(value))
    };
    Ok(format!(
        "---\nsession_id: {}\nactive_prompt_id: {}\nactive_source: {}\nactive_authority: {}\nlast_user_prompt_id: {}\nlast_user_prompt_source: {}\nlast_user_prompt_label: {}\nlast_user_prompt_sha256: {}\nlast_user_prompt_received_at: {}\nlast_user_prompt_truncated: {}\nautomation_id: {}\nautomation_run_id: {}\nscope_digest: {}\n---\n\n# Last User Prompt\n{}",
        string(&state.session_id)?,
        string(&state.active_prompt_id)?,
        string(&state.active_source)?,
        string(&state.active_authority)?,
        optional(&state.last_user_prompt_id)?,
        optional(&state.last_user_prompt_source)?,
        optional(&state.last_user_prompt_label)?,
        optional(&state.last_user_prompt_sha256)?,
        state
            .last_user_prompt_received_at
            .map_or_else(|| "null".into(), |value| value.to_string()),
        state.last_user_prompt_truncated,
        optional(&state.automation_id)?,
        optional(&state.automation_run_id)?,
        optional(&state.scope_digest)?,
        state.excerpt,
    ))
}

fn parse_session(text: &str) -> Result<SessionState> {
    let rest = text
        .strip_prefix("---\n")
        .ok_or_else(|| Error::Invalid("session frontmatter is missing".into()))?;
    let (header, body) = rest
        .split_once("\n---\n\n# Last User Prompt\n")
        .ok_or_else(|| Error::Invalid("session body is malformed".into()))?;
    let mut fields = BTreeMap::new();
    for line in header.lines() {
        let (key, value) = line
            .split_once(": ")
            .ok_or_else(|| Error::Invalid("session frontmatter is malformed".into()))?;
        if fields.insert(key, value).is_some() {
            return Err(Error::Invalid("duplicate session field".into()));
        }
    }
    let required = [
        "session_id",
        "active_prompt_id",
        "active_source",
        "active_authority",
        "last_user_prompt_id",
        "last_user_prompt_source",
        "last_user_prompt_label",
        "last_user_prompt_sha256",
        "last_user_prompt_received_at",
        "last_user_prompt_truncated",
        "automation_id",
        "automation_run_id",
        "scope_digest",
    ];
    if fields.len() != required.len() || required.iter().any(|key| !fields.contains_key(key)) {
        return Err(Error::Invalid("session fields are not closed".into()));
    }
    Ok(SessionState {
        session_id: parse_string(&fields, "session_id")?,
        active_prompt_id: parse_string(&fields, "active_prompt_id")?,
        active_source: parse_string(&fields, "active_source")?,
        active_authority: parse_string(&fields, "active_authority")?,
        last_user_prompt_id: parse_optional(&fields, "last_user_prompt_id")?,
        last_user_prompt_source: parse_optional(&fields, "last_user_prompt_source")?,
        last_user_prompt_label: parse_optional(&fields, "last_user_prompt_label")?,
        last_user_prompt_sha256: parse_optional(&fields, "last_user_prompt_sha256")?,
        last_user_prompt_received_at: parse_optional_u64(&fields, "last_user_prompt_received_at")?,
        last_user_prompt_truncated: fields["last_user_prompt_truncated"]
            .parse()
            .map_err(|_| Error::Invalid("invalid truncated flag".into()))?,
        automation_id: parse_optional(&fields, "automation_id")?,
        automation_run_id: parse_optional(&fields, "automation_run_id")?,
        scope_digest: parse_optional(&fields, "scope_digest")?,
        excerpt: body.into(),
    })
}

fn parse_string(fields: &BTreeMap<&str, &str>, key: &str) -> Result<String> {
    Ok(serde_json::from_str(fields[key])?)
}

fn parse_optional(fields: &BTreeMap<&str, &str>, key: &str) -> Result<Option<String>> {
    Ok(serde_json::from_str(fields[key])?)
}

fn parse_optional_u64(fields: &BTreeMap<&str, &str>, key: &str) -> Result<Option<u64>> {
    if fields[key] == "null" {
        return Ok(None);
    }
    Ok(Some(
        fields[key]
            .parse()
            .map_err(|_| Error::Invalid(format!("invalid {key}")))?,
    ))
}

fn utf8_prefix(value: &str, limit: usize) -> &str {
    if value.len() <= limit {
        return value;
    }
    let mut end = limit;
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    &value[..end]
}

fn source_name(source: HostSource) -> &'static str {
    match source {
        HostSource::User => "user",
        HostSource::Automation => "automation",
        HostSource::Internal => "internal",
        HostSource::Unverified => "unverified",
    }
}

fn authority_name(authority: DerivedAuthority) -> &'static str {
    match authority {
        DerivedAuthority::InteractiveUser => "interactive_user",
        DerivedAuthority::PreapprovedAutomation => "preapproved_automation",
        DerivedAuthority::InheritedInternal => "inherited_internal",
        DerivedAuthority::None => "none",
    }
}
