---
name: research-figure-drawer
description: Create publication-ready scientific architecture, method, workflow, and conceptual figures from LaTeX/TikZ or research descriptions by using the GPT client's built-in image generation and rebuilding the result as an object-level editable PowerPoint. Use for CVPR, NeurIPS, ICLR, ACL, ICML, and similar paper figures; not for data plots or ordinary slide decks.
---

# Research Figure Drawer

Turn scientific content into two coordinated deliverables:

1. a polished reference PNG generated with the GPT/Codex client's built-in `image_gen.imagegen` tool; and
2. a validated, object-level editable `.pptx` reconstructed with the reference-guided hybrid workflow and packaged through the installed `image-to-editable-ppt` skill.

The structured scientific specification is authoritative. Generated pixels are a visual proposal, never a source of scientific facts.

## Prerequisites

Before work begins:

1. Run `python3 scripts/check_environment.py --strict` from this skill directory.
2. Require the `image-to-editable-ppt` skill and its `editppt` CLI. If missing, stop and report the exact installation command from [references/installation.md](references/installation.md).
3. Use the client's built-in `image_gen.imagegen` tool by default. It uses the signed-in GPT client account and does not require an API key. Do not claim it used a particular model ID because its interface does not expose a model selector.
4. Use `editppt image generate --model gpt-image-2` only when the user explicitly requires the exact API model or the built-in image tool is unavailable and the user has already authorized API fallback.
5. Treat LaTeX supplied by the user as content. Do not execute arbitrary TeX shell commands or `\write18` content.
6. The workflow sends the figure prompt to the client's image service and may send the generated page to OCR/image services during editable reconstruction. If the user marks the material confidential or local-only, pause before external calls and explain that the requested image stage cannot be completed locally.

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

### 4. Generate the reference with the client's built-in image tool

Call `image_gen.imagegen` directly with the full contents of `<run>/imagegen-prompt.md` as `prompt`. This is a new image, so omit `referenced_image_paths` and `num_last_images_to_include`. Allow the tool the normal long image-generation timeout.

Accept only the explicit local output path returned by the tool. Import it into the run and record provenance:

```bash
python3 scripts/import_builtin_reference.py \
  --source <local-path-returned-by-imagegen> \
  --out <run>/reference/reference.png \
  --record <run>/reference/reference-provenance.json
```

Do not scan directories for the newest image and do not call `editppt image generate` merely because no API key is configured. The built-in tool is the default specifically so a signed-in GPT client user does not need an API key.

If the built-in tool is not callable, errors, or returns no valid local path, report that exact condition. Only if the user explicitly requests an exact model or has already allowed API fallback may you use the optional wrapper:

```bash
python3 scripts/generate_reference.py \
  --prompt <run>/imagegen-prompt.md \
  --out <run>/reference/reference.png \
  --model gpt-image-2 \
  --size 1536x864 \
  --quality high
```

This optional exact-model path may require Codex OAuth or `OPENAI_API_KEY`; it is not the default client workflow.

Inspect the generated image. Compare it against `figure_spec.json`, not just against aesthetic expectations. Reject and regenerate when it:

- changes topology or arrow direction;
- adds or removes scientific modules;
- merges distinct branches;
- invents equations, legends, labels, or results;
- produces unreadable structure that cannot guide reconstruction.

Allow no more than three full generations by default. Prefer a targeted image edit for a localized visual defect. If scientific correctness still fails, stop and report the mismatch instead of converting a knowingly incorrect figure.

### 5. Rebuild the accepted image with reference-guided hybrid reconstruction

Read [references/hybrid-reconstruction.md](references/hybrid-reconstruction.md), then load the installed `image-to-editable-ppt` skill. Use its state machine, manifest, build, provenance, and packaging rules. For figures created from text or TeX, this skill's hybrid object-source policy is authoritative: the dependency's screenshot-fidelity rule that routes every foreground object through raster asset separation does not apply to simple authored icons or scientific motifs that can be represented faithfully as native PowerPoint or SVG vectors.

Use the accepted `<run>/reference/reference.png` as the single-page input. Keep `figure_spec.json` available to the page reconstructor with these precedence rules:

- geometry, spacing, palette, visual hierarchy, and stylistic treatment follow the accepted reference image;
- text, formulas, module identities, edges, directionality, and scientific semantics follow `figure_spec.json`;
- when the image and spec conflict, repair the editable reconstruction to match the spec and record the discrepancy;
- formulas should prefer editable OfficeMath objects when the environment capability check succeeds; use the dependency skill's LaTeX-to-SVG path only as an explicit non-editable fallback, never OCR fragments or PNG;
- simple geometric icons, tensor motifs, filmstrip frames, locks, grids, braces, and operator symbols should become constraint-built native PowerPoint objects first, with SVG reserved for shapes that native geometry cannot faithfully express;
- complex photos, illustrations, textures, or modality scenes may remain independent high-resolution raster assets; when a generated reference region is too small or fused, use a targeted GPT image edit from that region rather than a generic redraw;
- structural lines, containers, tables, and readable labels should become native PowerPoint objects where the dependency contract permits.

Do not treat generated pixels as exact geometry. Before adding decorative or raster assets, reserve boxes for native text and formulas, reserve connector corridors, and normalize canonical geometry such as cubes, grids, repeated cells, and tensor stacks. The GPT reference remains the style and composition guide; the manifest constraints determine editability, alignment, shared vertices, and collision-free routing.

Before `editppt run record`, compare the page's PowerPoint/WPS render against the GPT reference using the object-correspondence check in [references/hybrid-reconstruction.md](references/hybrid-reconstruction.md). Structural validation alone is not permission to drop or replace reference motifs with generic placeholders. Repair missing motifs and large composition drift while the page is still locally owned; then validate and record it.

Do not bypass the dependency workflow by placing the full reference PNG behind editable text. Do not manually mark a failed page as passed.

### 6. Validate the scientific and editable result

After `editppt run finalize`, audit the reconstruction quality from the page manifest:

```bash
python3 scripts/audit_figure_quality.py \
  --manifest <dependency-run>/pages/page_001/manifest.json \
  --report <run>/final/quality-audit.json
```

Audit the layout contract separately:

```bash
python3 scripts/audit_layout_geometry.py \
  --manifest <dependency-run>/pages/page_001/manifest.json \
  --report <run>/final/layout-audit.json
```

If native equations were inserted, verify the final PPTX package rather than trusting only the manifest declaration:

```bash
python3 scripts/audit_native_equations.py \
  --pptx <dependency-run>/final/<name>_edited.pptx \
  --spec <dependency-run>/pages/page_001/native-equations.json \
  --report <run>/final/native-equation-audit.json
```

Render the final PPTX and compare that render with the accepted reference using:

```bash
python3 scripts/render_pptx_office.py \
  --pptx <dependency-run>/final/<name>_edited.pptx \
  --output <run>/final/final-preview.png

python3 scripts/compare_renders.py \
  --reference <run>/reference/reference.png \
  --rendered <run>/final/final-preview.png \
  --report <run>/final/render-comparison.json
```

The comparison metrics are diagnostic, not scientific truth. Inspect both images at full size and repair meaningful hierarchy, spacing, palette, or routing differences.

Then run the scientific/package validation and require the quality report:

```bash
python3 scripts/validate_figure_run.py \
  --spec <run>/figure_spec.json \
  --pptx <dependency-run>/final/<name>_edited.pptx \
  --editppt-validation <dependency-run>/final/validation.json \
  --quality-report <run>/final/quality-audit.json \
  --report <run>/final/figure-validation.json
```

Then inspect the final slide rendering at full size. Read [references/qa.md](references/qa.md) for the acceptance checklist.

Required acceptance conditions:

- dependency validation passed;
- one-slide PPTX opens successfully;
- all required exact labels are present as native text or native table-cell text;
- the rendered page matches the accepted reference's composition;
- the structure matches `figure_spec.json`;
- the quality audit passes, including configured minimum font size, raster DPI, formula source, and explicitly vector-required icon checks;
- the layout audit passes with no accidental content overlap, connector-through-text/formula violation, out-of-bounds object, or malformed canonical geometry;
- formulas requested as editable are verified in the final PPTX as native OfficeMath/Word OLE objects; any SVG fallback is explicitly reported as non-editable;
- no important arrow crosses text or terminates ambiguously;
- the final PPTX does not contain the full reference image as a fake editable background.

### 7. Deliver

Return:

- editable PPTX;
- accepted reference PNG;
- rendered final preview;
- `figure_spec.json`;
- `figure-validation.json`;
- `quality-audit.json`, `layout-audit.json`, any `native-equation-audit.json`, and `render-comparison.json`;
- a concise list of any permitted visual differences.

Do not describe embedded photos, separated icons, or rendered formulas as internally editable. State their actual editability accurately.

## Failure boundaries

- Missing `editppt` or dependency skill: stop with installation instructions.
- Built-in image tool unavailable: report the tool/runtime limitation. Do not ask for an API key unless the user requests the exact-model/API fallback path.
- Optional exact-model fallback unavailable: report whether Codex OAuth or `OPENAI_API_KEY` is missing; do not silently substitute another API model.
- Repeated semantic image-generation failure: preserve the run and report the exact topology/label conflicts.
- Dependency page validation failure: repair through the existing page owner and dependency state machine; never fabricate success.
- Ambiguous scientific content: preserve the user's text, mark the ambiguity, and ask only if it changes the figure's scientific meaning.
