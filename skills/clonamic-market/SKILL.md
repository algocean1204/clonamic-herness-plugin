---
name: clonamic-market
description: Select the smallest matching optional Clonamic plugin from the repository catalog. Use when the user asks what Clonamic capability or plugin is available; do not use for installation or automatic activation.
---

# Clonamic Market

Read `../../catalog/plugins.json` relative to this skill root and match the request to the narrowest listed capability.

- Treat the catalog as inventory, not installation authority.
- Prefer one plugin; add another only when the request has a distinct uncovered capability.
- Respect declared dependencies and platform support.
- Never infer that a child plugin is installed, enabled, or automatically bundled with this core plugin.
- If the catalog is absent or has no match, state that result without inventing an entry or fallback.

Return the matching plugin name, the capability that matched, and any declared dependency. Installation remains a separate user-authorized platform action.
