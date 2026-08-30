use crate::atomic::reject_symlink_components;
use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
pub struct ResolvePaths {
    pub catalog: PathBuf,
    pub manifest_root: PathBuf,
    pub default_config: Option<PathBuf>,
    pub user_config: Option<PathBuf>,
    pub project_config: Option<PathBuf>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ResolutionStatus {
    Ok,
    InvalidConfig,
}

#[derive(Clone, Debug, Serialize)]
pub struct PluginState {
    pub name: String,
    pub required: bool,
    pub configured: bool,
    pub installed: bool,
    pub platform_supported: bool,
    pub dependencies: Vec<String>,
    pub dependencies_ready: bool,
    pub runtime_ready: bool,
    pub effective: bool,
    pub reason: String,
    pub manifest: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct PluginResolution {
    pub status: ResolutionStatus,
    pub configuration: Option<String>,
    pub plugins: Vec<PluginState>,
}

impl PluginResolution {
    pub fn plugin(&self, name: &str) -> Option<&PluginState> {
        self.plugins.iter().find(|plugin| plugin.name == name)
    }

    pub fn can_invoke_optional(&self, name: &str) -> bool {
        self.plugin(name)
            .is_some_and(|plugin| !plugin.required && plugin.effective)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    plugins: Vec<CatalogEntry>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CatalogEntry {
    manifest: String,
    required: bool,
    category: String,
    platforms: Vec<String>,
    dependencies: Vec<String>,
    #[serde(default)]
    runtime_ready_required: bool,
}

#[derive(Deserialize)]
struct Manifest {
    name: String,
    #[serde(flatten)]
    _rest: BTreeMap<String, serde_json::Value>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ConfigDocument {
    #[serde(rename = "$schema")]
    _schema: Option<String>,
    schema_version: u32,
    plugins: BTreeMap<String, bool>,
}

struct InventoryRow {
    entry: CatalogEntry,
    name: String,
    dependencies: Vec<String>,
}

enum SelectedConfig {
    Implicit,
    Valid(PathBuf, BTreeMap<String, bool>),
    Invalid(PathBuf),
}

pub fn resolve_plugins(
    paths: &ResolvePaths,
    platform: &str,
    installed: &BTreeSet<String>,
) -> Result<PluginResolution> {
    resolve_plugins_with_runtime(paths, platform, installed, &BTreeSet::new())
}

pub fn resolve_plugins_with_runtime(
    paths: &ResolvePaths,
    platform: &str,
    installed: &BTreeSet<String>,
    runtime_ready: &BTreeSet<String>,
) -> Result<PluginResolution> {
    if !valid_platform_id(platform) {
        return Err(Error::Invalid("unsupported platform".into()));
    }
    let rows = load_inventory(paths)?;
    let optional_names: BTreeSet<String> = rows
        .iter()
        .filter(|row| !row.entry.required)
        .map(|row| row.name.clone())
        .collect();
    let selected = select_config(paths, &optional_names);
    let invalid = matches!(selected, SelectedConfig::Invalid(_));
    let configuration = match &selected {
        SelectedConfig::Implicit => None,
        SelectedConfig::Valid(path, _) | SelectedConfig::Invalid(path) => {
            Some(path.to_string_lossy().into_owned())
        }
    };
    let configured = match &selected {
        SelectedConfig::Implicit => optional_names
            .iter()
            .map(|name| (name.clone(), true))
            .collect(),
        SelectedConfig::Valid(_, configured) => configured.clone(),
        SelectedConfig::Invalid(_) => optional_names
            .iter()
            .map(|name| (name.clone(), false))
            .collect(),
    };

    let mut plugins = Vec::with_capacity(rows.len());
    for row in &rows {
        let required = row.entry.required;
        let configured = required || configured.get(&row.name).copied().unwrap_or(false);
        let installed = required || installed.contains(&row.name);
        let supported = row.entry.platforms.iter().any(|value| value == platform);
        let runtime_ready = !row.entry.runtime_ready_required || runtime_ready.contains(&row.name);
        let (effective, reason) = if required {
            (true, "required")
        } else if invalid {
            (false, "invalid_config")
        } else if !configured {
            (false, "disabled_by_config")
        } else if !installed || !supported || !runtime_ready {
            (false, "enabled_but_unavailable")
        } else {
            (true, "enabled")
        };
        plugins.push(PluginState {
            name: row.name.clone(),
            required,
            configured,
            installed,
            platform_supported: supported,
            dependencies: row.dependencies.clone(),
            dependencies_ready: true,
            runtime_ready,
            effective,
            reason: reason.into(),
            manifest: row.entry.manifest.clone(),
        });
    }

    let indexes: BTreeMap<String, usize> = plugins
        .iter()
        .enumerate()
        .map(|(index, plugin)| (plugin.name.clone(), index))
        .collect();
    loop {
        let disabled = plugins
            .iter()
            .enumerate()
            .filter(|(_, plugin)| {
                plugin.effective
                    && plugin
                        .dependencies
                        .iter()
                        .any(|dependency| !plugins[indexes[dependency]].effective)
            })
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        if disabled.is_empty() {
            break;
        }
        for index in disabled {
            plugins[index].effective = false;
            plugins[index].reason = "enabled_but_unavailable".into();
        }
    }
    for index in 0..plugins.len() {
        plugins[index].dependencies_ready = plugins[index]
            .dependencies
            .iter()
            .all(|dependency| plugins[indexes[dependency]].effective);
    }

    Ok(PluginResolution {
        status: if invalid {
            ResolutionStatus::InvalidConfig
        } else {
            ResolutionStatus::Ok
        },
        configuration,
        plugins,
    })
}

fn valid_platform_id(value: &str) -> bool {
    if value.is_empty() || value.len() > 64 {
        return false;
    }
    let mut separator = true;
    for byte in value.bytes() {
        if byte.is_ascii_lowercase() || byte.is_ascii_digit() {
            separator = false;
        } else if matches!(byte, b'.' | b'-') && !separator {
            separator = true;
        } else {
            return false;
        }
    }
    !separator
}

pub fn reduce_automation_scope(
    resolution: &PluginResolution,
    current_scope: &BTreeSet<String>,
) -> BTreeSet<String> {
    current_scope
        .iter()
        .filter(|name| resolution.can_invoke_optional(name))
        .cloned()
        .collect()
}

fn load_inventory(paths: &ResolvePaths) -> Result<Vec<InventoryRow>> {
    reject_symlink_components(&paths.manifest_root)?;
    let manifest_root = fs::canonicalize(&paths.manifest_root)?;
    let catalog: Catalog = serde_json::from_slice(&fs::read(&paths.catalog)?)?;
    if catalog.plugins.is_empty() {
        return Err(Error::Invalid("catalog is empty".into()));
    }
    let manifests: BTreeSet<String> = catalog
        .plugins
        .iter()
        .map(|entry| entry.manifest.clone())
        .collect();
    if manifests.len() != catalog.plugins.len() {
        return Err(Error::Invalid(
            "catalog manifest paths must be unique".into(),
        ));
    }
    let mut names = BTreeMap::new();
    let mut plugin_names = BTreeSet::new();
    for entry in &catalog.plugins {
        validate_relative(&entry.manifest)?;
        if entry.category.is_empty() {
            return Err(Error::Invalid("catalog category is required".into()));
        }
        let manifest_path = manifest_root.join(&entry.manifest);
        reject_symlink_components(&manifest_path)?;
        let canonical = fs::canonicalize(&manifest_path)?;
        if !canonical.starts_with(&manifest_root) {
            return Err(Error::Invalid("catalog manifest path escapes root".into()));
        }
        let manifest: Manifest = serde_json::from_slice(&fs::read(canonical)?)?;
        if !plugin_names.insert(manifest.name.clone())
            || names
                .insert(entry.manifest.clone(), manifest.name)
                .is_some()
        {
            return Err(Error::Invalid("duplicate catalog manifest".into()));
        }
    }
    let required = catalog
        .plugins
        .iter()
        .filter(|entry| entry.required)
        .map(|entry| entry.manifest.as_str())
        .collect::<Vec<_>>();
    if required != ["plugin.json"] {
        return Err(Error::Invalid(
            "only the root plugin may be required".into(),
        ));
    }
    if catalog.plugins[0].manifest != "plugin.json" || !catalog.plugins[0].dependencies.is_empty() {
        return Err(Error::Invalid(
            "root plugin must be first and dependency-free".into(),
        ));
    }
    validate_graph(&catalog.plugins, &manifests)?;
    catalog
        .plugins
        .into_iter()
        .map(|entry| {
            let dependencies = entry
                .dependencies
                .iter()
                .map(|path| names[path].clone())
                .collect();
            Ok(InventoryRow {
                name: names[&entry.manifest].clone(),
                entry,
                dependencies,
            })
        })
        .collect()
}

fn select_config(paths: &ResolvePaths, expected: &BTreeSet<String>) -> SelectedConfig {
    let mut merged = expected
        .iter()
        .map(|name| (name.clone(), true))
        .collect::<BTreeMap<_, _>>();
    let mut selected_path = None;
    for (path, complete) in [
        (paths.default_config.as_ref(), true),
        (paths.user_config.as_ref(), false),
        (paths.project_config.as_ref(), false),
    ] {
        let Some(path) = path else { continue };
        let data = match fs::read(path) {
            Ok(data) => data,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(_) => return SelectedConfig::Invalid(path.clone()),
        };
        let document: ConfigDocument = match serde_json::from_slice(&data) {
            Ok(document) => document,
            Err(_) => return SelectedConfig::Invalid(path.clone()),
        };
        let keys = document.plugins.keys().cloned().collect::<BTreeSet<_>>();
        if document.schema_version != 1
            || !keys.is_subset(expected)
            || (complete && keys != *expected)
        {
            return SelectedConfig::Invalid(path.clone());
        }
        merged.extend(document.plugins);
        selected_path = Some(path.clone());
    }
    selected_path
        .map(|path| SelectedConfig::Valid(path, merged))
        .unwrap_or(SelectedConfig::Implicit)
}

fn validate_relative(value: &str) -> Result<()> {
    let path = Path::new(value);
    if path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(Error::Invalid("catalog manifest path escapes root".into()));
    }
    Ok(())
}

fn validate_graph(entries: &[CatalogEntry], manifests: &BTreeSet<String>) -> Result<()> {
    let graph: BTreeMap<&str, &Vec<String>> = entries
        .iter()
        .map(|entry| (entry.manifest.as_str(), &entry.dependencies))
        .collect();
    for dependencies in graph.values() {
        if dependencies
            .iter()
            .any(|dependency| !manifests.contains(dependency))
        {
            return Err(Error::Invalid("catalog dependency is unknown".into()));
        }
    }
    fn visit<'a>(
        node: &'a str,
        graph: &BTreeMap<&'a str, &'a Vec<String>>,
        visiting: &mut BTreeSet<&'a str>,
        visited: &mut BTreeSet<&'a str>,
    ) -> Result<()> {
        if visited.contains(node) {
            return Ok(());
        }
        if !visiting.insert(node) {
            return Err(Error::Invalid("catalog dependency cycle".into()));
        }
        for dependency in graph[node] {
            visit(dependency, graph, visiting, visited)?;
        }
        visiting.remove(node);
        visited.insert(node);
        Ok(())
    }
    let mut visiting = BTreeSet::new();
    let mut visited = BTreeSet::new();
    for node in graph.keys() {
        visit(node, &graph, &mut visiting, &mut visited)?;
    }
    Ok(())
}
