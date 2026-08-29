---
name: clonamic-figma-workflow
description: "ClaudeTalkToFigma MCP procedure — channel join, claude_page conventions, faithful-reproduction rules (no vertical text wrap, no overlapping elements), export-and-verify loop. Use for any Figma design creation or editing via MCP (피그마 작업, 레퍼런스 재현)."
---

# Figma Workflow (ClaudeTalkToFigma MCP)

## 1. Session setup

- Keep ClaudeTalkToFigma on demand, never user-wide, project-wide, or Codex-wide. Start a dedicated Claude session with `claude --mcp-config ~/.claude/figma-mcp.json --strict-mcp-config`. The non-`.mcp.json` filename is deliberate: Claude must not auto-discover it as project config when running inside `~/.claude`. If the tools are absent in the current session, request that one relaunch; never register the server globally or start raw `npx` in the background.
- Channel ID is provided by the user **each session** — ask for it if missing, never guess. `join_channel` first; nothing works before this.
- Work on the `claude_page` page unless the user names another; `get_pages` → `set_current_page` (create it if absent).
- `get_document_info` before creating anything — reuse existing frames/styles when present.

## 2. Faithful reproduction rules (hard requirements from past feedback)

- Reproduce reference images **as-is**: same layout, proportions, hierarchy — no "creative improvements" unless asked.
- **No vertical character stacking**: every text node's width must fit its content (set frame/text width first, then text; after `set_text_content`, check bounds — a 1-character-per-line wrap is a bug, widen the box).
- **No overlapping elements**: after placing nodes, verify x/y/width/height don't collide; prefer `set_auto_layout` for rows/columns/stacks over manual coordinates.
- Load fonts before styling: `load_font_async`, then `set_font_name`/`set_font_size` — never assume a font is available.

## 3. Build procedure

1. Frame first with explicit x/y/size (`create_frame`), name it meaningfully (`rename_node`).
2. Children inside via `insert_child` / auto-layout; group logical clusters (`group_nodes`).
3. Text: create → widen box → set content → set typography → re-check bounds.
4. Colors/effects from the reference's actual values — sample them, don't approximate from memory.

## 4. Export-and-verify loop (mandatory)

After building: `export_node_as_image` on the top frame → **look at the image** → compare against the reference → fix wraps/overlaps/misalignment → re-export. Repeat until clean. Never declare a Figma task done without at least one exported-image inspection.

## 5. Cleanup

Meaningful node names, logical grouping, delete scratch nodes. Report the page + top frame name to the user.

## Offline and source boundary

The reproduction rules and local export checks work offline once the source artifact is available. Live Figma inspection or editing requires an explicitly connected Figma/ClaudeTalkToFigma MCP session and is never silently replaced with guessed values. Do not install the MCP server, register global configuration, or fetch a remote Figma file without the user's request and the exact connection details.

OpenAI's current Figma agent integration lives in the official `openai/plugins` repository and is governed by Figma's developer terms; it is a runtime reference, not vendored public content in this skill.
