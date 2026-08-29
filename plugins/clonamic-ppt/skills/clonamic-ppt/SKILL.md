---
name: clonamic-ppt
description: Create or revise editable PPTX presentations with a structured brief, outline, slide specifications, deterministic rendering, and QA. Use for deck, slide, presentation, PowerPoint, or PPTX requests.
---

# Presentation Engine

Work directly in this skill. Do not delegate or select an external runtime.

1. Read [references/specialist.md](references/specialist.md) and the purpose-specific guidance it names.
2. Resolve the skill root as the directory containing this `SKILL.md`; all scripts and references are relative to it.
3. Create `brief.json`, then `outline.json`, then `slide_specs.json` in the chosen output directory.
4. Validate and render with the scripts in `scripts/`.
5. Repair specification or content defects, rerun the engine, and return the final artifact paths with the QA findings.

Use only facts and numeric series supplied by the user. Do not hand-edit generated coordinates or presentation XML.
Image inputs are unsupported. Do not pass ICNS, JXL, HEIF, HEIC, or any other image file to the renderer.
