# Astryx Quickstart (vendored snapshot)

Source: https://github.com/facebook/astryx/blob/main/README.md ,
https://astryx.atmeta.com/docs/getting-started ,
https://astryx.atmeta.com/docs/working-with-ai
Fetched: 2026-07-25
Package version at fetch time: `@astryxdesign/core@0.1.8` (npm registry).
Status at fetch time: **Beta**, MIT license.

This is a point-in-time snapshot for offline reference. Astryx is Beta and
ships breaking changes between minor versions — verify against
`npx astryx manifest --json` and https://astryx.atmeta.com/changelog before
depending on any detail below.

## Install

```bash
npm install @astryxdesign/core @astryxdesign/theme-neutral @astryxdesign/cli
# pnpm / yarn equivalents are documented on the same page
```

Optional local CLI alias for reliable invocation from scripts:

```json
"scripts": {
  "astryx": "node node_modules/@astryxdesign/cli/bin/astryx.mjs"
}
```

## Initialize a project

```bash
npx astryx init
```

Non-interactive — no prompts — so it is safe for AI agents, CI, and scripts.
Installs packages, sets up theming, and (with `--features agents`) adds
AI-agent context docs.

```bash
npx astryx init --features agents
```

As of v0.1.8 this defaults to a root `AGENTS.md` (a tool-agnostic standard
change from the prior `.claude/CLAUDE.md`-only output). Tool-specific outputs
observed in docs: Claude → `.claude/CLAUDE.md` (older behavior, may still be
emitted depending on detected tooling), Cursor → `.cursorrules`, general →
`AGENTS.md`. Confirm actual output against the installed CLI version — this
is exactly the kind of detail that has already changed once.

## Import styles and a theme

```css
@import '@astryxdesign/core/reset.css';
@import '@astryxdesign/core/astryx.css';
@import '@astryxdesign/theme-neutral/theme.css';
```

## First component

Components import from category-specific subpaths to keep bundles small:

```tsx
import {Button} from '@astryxdesign/core/Button';
import {VStack} from '@astryxdesign/core/Layout';
```

## Dev requirements (for contributing to Astryx itself, not consuming it)

Node 22+ (active LTS), pnpm 11.

## Docs / Storybook

- Main docs: https://astryx.atmeta.com
- Storybook: https://facebook.github.io/astryx/storybook/
- Changelog: https://astryx.atmeta.com/changelog
