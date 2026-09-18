# Research Figure Drawer

A self-contained Codex/GPT client skill that turns scientific LaTeX, TikZ, architecture descriptions, and method workflows into:

- a publication-ready reference figure generated with the GPT/Codex client's built-in image tool; and
- a validated, object-level editable PowerPoint figure.

Both halves ship in one skill. The editable-PPT reconstruction runtime (`editppt`), its contract, its references, and its page-worker template are vendored inside `skills/research-figure-drawer/` and pinned to an upstream commit, so installing this skill requires no second skill.

## Why this is different

Image generators can produce attractive figures but may corrupt labels, formulas, arrows, or module topology. This skill writes `figure_spec.json` before image generation and uses it again during PPT reconstruction and validation. The generated PNG controls appearance; the spec controls scientific meaning.

## Pipeline

```text
TeX / TikZ / method description
        ↓
figure_spec.json — authoritative labels, formulas, modules, and edges
        ↓
client built-in image generation — polished reference PNG
        ↓
bundled editppt runtime — native text, shapes, paths, tables, and independent assets
        ↓
scientific validation + quality audit + rendered visual QA
        ↓
editable one-slide PPTX
```

## Installation

Install this skill and restart the client:

```bash
npx -y skills@latest add AdjacentGarden/figure_drawer \
  --skill research-figure-drawer \
  --agent codex \
  --global
```

Then prepare the bundled runtime (dependencies are declared in `skills/research-figure-drawer/cli/pyproject.toml`):

```bash
cd <skill-root>
python3 scripts/check_environment.py --strict
python3 -m pip install -e cli        # gives you the `editppt` command
# or run it with no install step:
python3 scripts/run_editppt.py --help
editppt doctor
```

The default image path uses the client-provided `image_gen.imagegen` tool and therefore does not require an API key. [ChatGPT Pro includes image creation](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro/), subject to separate plan and tool limits. Exact [`gpt-image-2`](https://developers.openai.com/api/docs/models/gpt-image-2) API selection remains available as an optional fallback and may require Codex OAuth or `OPENAI_API_KEY`.

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
- scientific, structural, quality, and render-comparison reports

## Repository layout

```text
skills/research-figure-drawer/
├── SKILL.md
├── agents/openai.yaml
├── assets/figure-drawer.svg
├── cli/              ← vendored editppt runtime (MIT) + VENDOR.json
├── prompts/          ← vendored page-worker template
├── references/       ← this skill's references + vendored contracts
└── scripts/
examples/
tests/
```

## Vendored components and attribution

| Component | Upstream | License |
|---|---|---|
| `skills/research-figure-drawer/cli/` and the vendored reference/prompt files | [ningzimu/image-to-editable-ppt-skill](https://github.com/ningzimu/image-to-editable-ppt-skill) @ `b7be494e31a0ed56ef98716891db5474606b8cdf` | MIT, Copyright (c) 2026 ningzimu |

Vendored files are byte-for-byte upstream and must not be edited in place; `cli/VENDOR.json` records a SHA-256 for each one and `tests/test_vendored_integrity.py` fails on undocumented drift. The upstream license text travels with the code at `skills/research-figure-drawer/cli/LICENSE`; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the full attribution.

## Boundaries

- This is for architecture, workflow, method, conceptual, multimodal, and training/inference figures. It is not a data-plotting or full slide-deck skill.
- Complex illustrations and semantic icons may remain independent raster assets; their internal strokes are not necessarily editable.
- LaTeX-rendered formulas are independently movable but are not automatically native PowerPoint equations.
- The image and OCR stages may use external services. Mark confidential work as local-only before invoking the skill; the GPT Image stage cannot then proceed as specified.
- The built-in image tool does not expose a model selector. The skill accurately records it as client-built-in generation rather than claiming an unverified API model ID.

## Development

Validate the skill and run tests:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/research-figure-drawer
python3 -m unittest discover -s tests -v
```

## License

MIT. Vendored third-party components remain under their own licenses — see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
