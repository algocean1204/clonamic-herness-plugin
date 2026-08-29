# Compatibility

| Platform | Native package | Skills | Commands | Hooks | Structural core |
|---|---|---:|---:|---:|---:|
| Codex | `.codex-plugin/plugin.json` | yes | host-dependent | optional adapter | `clonamic` |
| Claude Code | `.claude-plugin/plugin.json` | yes | yes | native plugin hooks | `clonamic` |
| Grok Build | `.grok-plugin/plugin.json` | yes | yes | native plugin hooks | `clonamic` |
| Hermes | `plugin.yaml` + `register(ctx)` | yes | adapter-capable | Python plugin hooks | `clonamic` |

The plugin never reports an unsupported hook as active. Skills remain usable without the native core; write enforcement is then a declared model-only fallback.

Known product behavior remains visible: Claude Code and Grok Build may display their own built-in progress messages; Clonamic does not patch platform system prompts.
