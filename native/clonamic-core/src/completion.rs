use serde::{Deserialize, Serialize};
use std::collections::HashSet;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CompletionItem {
    pub id: String,
    pub required: bool,
    pub complete: bool,
    pub evidence: String,
}

impl CompletionItem {
    pub fn required(id: &str, complete: bool, evidence: &str) -> Self {
        Self {
            id: id.into(),
            required: true,
            complete,
            evidence: evidence.into(),
        }
    }

    pub fn optional(id: &str, complete: bool, evidence: &str) -> Self {
        Self {
            id: id.into(),
            required: false,
            complete,
            evidence: evidence.into(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CompletionManifest {
    pub items: Vec<CompletionItem>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CompletionVerdict {
    pub complete: bool,
    pub unmet: Vec<String>,
}

impl CompletionVerdict {
    pub fn is_complete(&self) -> bool {
        self.complete
    }
}

pub fn verify_completion(manifest: &CompletionManifest) -> CompletionVerdict {
    let mut unmet = Vec::new();
    if !manifest.items.iter().any(|item| item.required) {
        unmet.push("manifest.required".into());
    }
    let mut seen = HashSet::new();
    let mut reported_duplicates = HashSet::new();
    for (index, item) in manifest.items.iter().enumerate() {
        if item.id.trim().is_empty() {
            unmet.push(format!("items[{index}].id"));
            continue;
        }
        if !seen.insert(item.id.as_str()) {
            if reported_duplicates.insert(item.id.as_str()) {
                unmet.push(format!("duplicate:{}", item.id));
            }
            continue;
        }
        if item.required && (!item.complete || item.evidence.trim().is_empty()) {
            unmet.push(item.id.clone());
        }
    }
    CompletionVerdict {
        complete: unmet.is_empty(),
        unmet,
    }
}
