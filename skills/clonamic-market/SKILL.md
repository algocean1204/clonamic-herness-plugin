---
name: clonamic-market
description: Match a requested capability to the smallest optional catalog plugin. Use for availability questions, not installation or activation.
---

# Clonamic Market

Read `../../catalog/plugins.json`; use `clonamic resolve-plugins` with explicit config paths and host installation state, then select the narrowest effective capability.

- Prefer one plugin; add another only for a distinct uncovered capability.
- Report configured, installed, platform_supported, dependencies_ready, effective, reason, and manifest separately.
- Never infer installation or authority. A disabled plugin is unavailable; enabling grants nothing.
- If no catalog or match exists, state that without inventing a fallback.

Return the plugin name, match, and resolver reason. Installation stays a platform action.
