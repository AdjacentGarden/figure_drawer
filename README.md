# Research Figure Drawer

An installable Codex/GPT client skill that turns scientific LaTeX, TikZ, architecture descriptions, and method workflows into:

- a publication-ready reference figure generated with `gpt-image-2`; and
- a validated, object-level editable PowerPoint figure.

The workflow uses a structured scientific specification as the source of truth, then delegates object-level PowerPoint reconstruction to [`image-to-editable-ppt`](https://github.com/ningzimu/image-to-editable-ppt-skill).

## Why this is different

Image generators can produce attractive figures but may corrupt labels, formulas, arrows, or module topology. This skill writes `figure_spec.json` before image generation and uses it again during PPT reconstruction and validation. The generated PNG controls appearance; the spec controls scientific meaning.

## Pipeline

```text
TeX / TikZ / method description
        ↓
figure_spec.json — authoritative labels, formulas, modules, and edges
        ↓
GPT Image 2 — polished reference PNG
        ↓
image-to-editable-ppt — native text, shapes, paths, tables, and independent assets
        ↓
scientific validation + editppt validation + rendered visual QA
        ↓
editable one-slide PPTX
```

## Installation

Install this skill and its required conversion skill, then restart the client:

```bash
npx -y skills@latest add AdjacentGarden/figure_drawer \
  --skill research-figure-drawer \
  --agent codex \
  --global

npx -y skills@latest add ningzimu/image-to-editable-ppt-skill \
  --skill image-to-editable-ppt \
  --agent codex \
  --global
```

If the dependency CLI is not available, follow its current setup instructions and verify:

```bash
editppt doctor
```

Exact image-model selection uses `editppt image generate --model gpt-image-2`. It requires supported Codex OAuth or an OpenAI-compatible API credential. The model is documented by [OpenAI](https://developers.openai.com/api/docs/models/gpt-image-2).

## Usage

Attach or paste a method description, LaTeX, or TikZ source and invoke:

```text
$research-figure-drawer Convert this method into a CVPR-style editable PowerPoint architecture figure.
```

Typical outputs include:

- `reference.png`
- editable `.pptx`
- rendered preview
- `figure_spec.json`
- scientific and structural validation reports

## Repository layout

```text
skills/research-figure-drawer/
├── SKILL.md
├── agents/openai.yaml
├── assets/figure-drawer.svg
├── references/
└── scripts/
examples/
tests/
```

## Boundaries

- This is for architecture, workflow, method, conceptual, multimodal, and training/inference figures. It is not a data-plotting or full slide-deck skill.
- Complex illustrations and semantic icons may remain independent raster assets; their internal strokes are not necessarily editable.
- LaTeX-rendered formulas are independently movable but are not automatically native PowerPoint equations.
- The image and OCR stages may use external services. Mark confidential work as local-only before invoking the skill; the GPT Image stage cannot then proceed as specified.

## Development

Validate the skill and run tests:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/research-figure-drawer
python3 -m unittest discover -s tests -v
```

## License

MIT
