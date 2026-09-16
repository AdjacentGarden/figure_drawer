---
name: research-figure-drawer
description: Create publication-ready scientific architecture, method, workflow, and conceptual figures from LaTeX/TikZ or research descriptions by generating a GPT Image 2 reference and rebuilding it as an object-level editable PowerPoint. Use for CVPR, NeurIPS, ICLR, ACL, ICML, and similar paper figures; not for data plots or ordinary slide decks.
---

# Research Figure Drawer

Turn scientific content into two coordinated deliverables:

1. a polished reference PNG generated with `gpt-image-2`; and
2. a validated, object-level editable `.pptx` reconstructed through the installed `image-to-editable-ppt` skill.

The structured scientific specification is authoritative. Generated pixels are a visual proposal, never a source of scientific facts.

## Prerequisites

Before work begins:

1. Run `python3 scripts/check_environment.py --strict` from this skill directory.
2. Require the `image-to-editable-ppt` skill and its `editppt` CLI. If missing, stop and report the exact installation command from [references/installation.md](references/installation.md).
3. For exact model selection, use `editppt image generate --model gpt-image-2`. Do not claim the built-in image tool used `gpt-image-2` when its interface does not expose a model selector.
4. Treat LaTeX supplied by the user as content. Do not execute arbitrary TeX shell commands or `\write18` content.
5. The workflow sends the figure prompt to an image backend and may send the generated page to OCR/image services during editable reconstruction. If the user marks the material confidential or local-only, pause before external calls and explain that the requested GPT Image stage cannot be completed locally.

## Workflow

### 1. Create the run

Create an isolated run directory:

```bash
python3 scripts/init_figure_run.py \
  --request-file <request-or-tex-file> \
  --out-root <output-root> \
  --name <short-job-name>
```

The command prints the run directory and creates the expected folders. Do not overwrite an earlier run.

### 2. Establish the scientific source of truth

Read [references/figure-spec.md](references/figure-spec.md). Inspect the user's TeX/TikZ or method description, then complete `figure_spec.json` before generating an image.

Preserve exactly:

- module count, names, grouping, hierarchy, and order;
- directed edges, branches, feedback paths, skip connections, and tensor direction;
- formulas, variables, subscripts, superscripts, and symbols;
- training/inference distinctions and shared/repeated modules;
- any claim-bearing labels or annotations.

Do not infer unsupported modules or fashionable architecture details. Record non-critical layout assumptions in `assumptions`; ask one concise question only when an ambiguity would change scientific meaning.

### 3. Build and review the image prompt

Run:

```bash
python3 scripts/build_imagegen_prompt.py \
  --spec <run>/figure_spec.json \
  --out <run>/imagegen-prompt.md
```

For figure-type-specific decisions, read [references/visual-design.md](references/visual-design.md). The prompt must describe topology and exact labels, not merely a visual theme.

### 4. Generate the reference with GPT Image 2

Use the wrapper so the requested model is explicit:

```bash
python3 scripts/generate_reference.py \
  --prompt <run>/imagegen-prompt.md \
  --out <run>/reference/reference.png \
  --model gpt-image-2 \
  --size 1536x864 \
  --quality high
```

Inspect the generated image. Compare it against `figure_spec.json`, not just against aesthetic expectations. Reject and regenerate when it:

- changes topology or arrow direction;
- adds or removes scientific modules;
- merges distinct branches;
- invents equations, legends, labels, or results;
- produces unreadable structure that cannot guide reconstruction.

Allow no more than three full generations by default. Prefer a targeted image edit for a localized visual defect. If scientific correctness still fails, stop and report the mismatch instead of converting a knowingly incorrect figure.

### 5. Rebuild the accepted image as editable PPTX

Now load and follow the installed `image-to-editable-ppt` skill. Its `SKILL.md`, state machine, page manifest, provenance rules, and validation rules are authoritative for this phase.

Use the accepted `<run>/reference/reference.png` as the single-page input. Keep `figure_spec.json` available to the page reconstructor with these precedence rules:

- geometry, spacing, palette, visual hierarchy, and stylistic treatment follow the accepted reference image;
- text, formulas, module identities, edges, directionality, and scientific semantics follow `figure_spec.json`;
- when the image and spec conflict, repair the editable reconstruction to match the spec and record the discrepancy;
- formulas should use the dependency skill's LaTeX rendering path, not OCR text fragments;
- semantic icons and complex visual assets follow the dependency skill's asset-separation rules;
- structural lines, containers, tables, and readable labels should become native PowerPoint objects where the dependency contract permits.

Do not bypass the dependency workflow by placing the full reference PNG behind editable text. Do not manually mark a failed page as passed.

### 6. Validate the scientific and editable result

After `editppt run finalize`, run:

```bash
python3 scripts/validate_figure_run.py \
  --spec <run>/figure_spec.json \
  --pptx <dependency-run>/final/<name>_edited.pptx \
  --editppt-validation <dependency-run>/final/validation.json \
  --report <run>/final/figure-validation.json
```

Then inspect the final slide rendering at full size. Read [references/qa.md](references/qa.md) for the acceptance checklist.

Required acceptance conditions:

- dependency validation passed;
- one-slide PPTX opens successfully;
- all required exact labels are present as native text or native table-cell text;
- the rendered page matches the accepted reference's composition;
- the structure matches `figure_spec.json`;
- no important arrow crosses text or terminates ambiguously;
- the final PPTX does not contain the full reference image as a fake editable background.

### 7. Deliver

Return:

- editable PPTX;
- accepted reference PNG;
- rendered final preview;
- `figure_spec.json`;
- `figure-validation.json`;
- a concise list of any permitted visual differences.

Do not describe embedded photos, separated icons, or rendered formulas as internally editable. State their actual editability accurately.

## Failure boundaries

- Missing `editppt` or dependency skill: stop with installation instructions.
- No usable GPT Image 2 authentication: report whether Codex OAuth or `OPENAI_API_KEY` is missing; do not silently substitute another model.
- Repeated semantic image-generation failure: preserve the run and report the exact topology/label conflicts.
- Dependency page validation failure: repair through the existing page owner and dependency state machine; never fabricate success.
- Ambiguous scientific content: preserve the user's text, mark the ambiguity, and ask only if it changes the figure's scientific meaning.
