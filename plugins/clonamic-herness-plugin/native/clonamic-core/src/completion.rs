use serde::{Deserialize, Serialize};

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
    let unmet = manifest
        .items
        .iter()
        .filter(|item| item.required && (!item.complete || item.evidence.trim().is_empty()))
        .map(|item| item.id.clone())
        .collect::<Vec<_>>();
    CompletionVerdict {
        complete: unmet.is_empty(),
        unmet,
    }
}
