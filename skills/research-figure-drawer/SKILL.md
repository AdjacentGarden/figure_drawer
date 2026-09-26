---
name: research-figure-drawer
description: Create publication-ready ML/AI architecture, method, workflow, and mechanism figures from paper content, code paths, dataset evidence, TeX, or reference images. For paper/code/dataset inputs, first generate a GPT visual reference, then reconstruct it as an object-level editable WPS/PPTX. Use for CVPR, NeurIPS, ICLR, ACL, ICML, ICCV and similar research figures; not for data plots or ordinary slide decks.
---

# Research Figure Drawer

Turn scientific content or an existing mechanism figure into two coordinated deliverables: a documented visual reference and a validated, object-level editable `.pptx`.

For a new figure whose inputs are a paper, manuscript text, implementation paths, configuration files, or dataset paths, the mandatory default is **image-first**:

```text
paper + code + dataset evidence
  -> curated scientific specification
  -> GPT-generated PNG reference
  -> reference-guided editable PPT reconstruction
  -> WPS reopen render and editability audit
```

Do not draw the final WPS/PPT geometry directly from research text merely because that is possible. The GPT-generated reference establishes the composition and visual style; `figure_spec.json` remains authoritative for modules, topology, formulas, and labels. Skip GPT image generation only when the user explicitly asks to skip it, supplies an existing image to reconstruct, or requests exact deterministic reconstruction of complete TikZ/PGF geometry.

Local paths are not directly accessible to the image model. Inspect the supplied paper, code, configuration, and dataset paths locally; place concise figure-relevant facts plus source paths and hashes in `source_evidence`; then send the generated prompt to GPT. Read [references/research-source-ingestion.md](references/research-source-ingestion.md) for this required source-bundling procedure.

This skill is self-contained: it does not require the separate `image-to-editable-ppt` skill, nor any network fetch of its code. The hybrid reconstruction runtime, its contract, its references, and its page-worker template ship inside this skill directory and are pinned to an upstream commit (see `cli/VENDOR.json`). The native WPS route additionally needs Windows WPS Presentation and `pywin32`.

For an existing published figure, declare the evaluation task before drawing: **unseen TeX reconstruction** (gold image withheld) or **reference-guided image-to-editable-PPT reconstruction** (published image visible). The latter is appropriate for complex figures whose TeX only contains an external-image placeholder. Never report a reference-guided result as TeX-only generation. Also choose `pixel-identical` or `perceptual-95-blind` acceptance up front.

## Prerequisites

Before work begins, select the renderer from the source type. Research-source authoring uses GPT image generation first and then WPS-native or hybrid reconstruction. Existing-image and deterministic TikZ tasks may start from their supplied reference instead:

1. Run `python3 scripts/check_environment.py --strict` from this skill directory.
2. Require the bundled `editppt` runtime at `<skill-root>/cli`. If `editppt --help` fails, install the bundled package (`python3 -m pip install -e <skill-root>/cli`) or use the bundled no-install launcher `python3 scripts/run_editppt.py --help`; the exact commands and dependency list are in [references/installation.md](references/installation.md). Do not substitute an unrelated installation of the same tool.
3. For a new figure from a paper, code, dataset, or semantic description, use the client's built-in `image_gen.imagegen` tool. This image stage is mandatory unless the user explicitly opts out. It uses the signed-in GPT client account and does not require an API key. Do not claim it used a particular model ID because its interface does not expose a model selector. Do not generate a replacement reference when the task is to reconstruct an existing published image exactly.
4. Use `editppt image generate --model gpt-image-2` only when the user explicitly requires the exact API model or the built-in image tool is unavailable and the user has already authorized API fallback.
5. Treat LaTeX supplied by the user as content. Do not execute arbitrary TeX shell commands or `\write18` content.
6. Before sending source-derived content to the image service, confirm that the run has user authorization for external generation and record that fact in the run metadata. If the user marks the material confidential or local-only, pause before external calls and explain that the mandatory image stage cannot be completed locally. Authorization for one paper does not cover unrelated projects.

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

### 2. Ingest research sources and classify exact visual evidence

For paper/code/dataset-driven authoring, read [references/research-source-ingestion.md](references/research-source-ingestion.md). Inspect the supplied paths locally and build `source_evidence` entries with a path, SHA-256, role, and concise figure-relevant summary. Do not paste whole repositories, raw datasets, checkpoints, credentials, or binary assets into the GPT prompt. The remote image model receives the curated prompt, not filesystem access.

Classify TeX only when the input contains TeX or TikZ evidence:

Run:

```bash
python3 scripts/classify_tex_source.py \
  --input <run>/request.md \
  --report <run>/source-classification.json
```

The result has three actionable modes:

- `deterministic-vector`: TikZ/PGF/PGFPlots geometry is present. Compile it with `scripts/compile_tex_reference.py`; do **not** send it through image generation.
- `external-image-placeholder`: the TeX only names `\includegraphics` assets. Without those assets the original pixels are not recoverable. If a public published original is available and the request permits using it, use the explicitly labeled reference-guided route. Otherwise ask for the image when exact reconstruction is required, or label the result semantic-only.
- `semantic-description`: the input contains concepts but no unique visual geometry. For research-source authoring, generate the GPT reference before reconstruction. It cannot honestly be evaluated as a pixel-identical reconstruction of an unseen original.

Known file/system primitives produce `unsafe-tex`; do not compile them. Read [references/benchmark-protocol.md](references/benchmark-protocol.md) before making any exact-match claim.

Real paper projects often contain unrelated `\input` and `\includegraphics` commands even when one target figure is self-contained. In that case isolate the target first:

```bash
python3 scripts/extract_tex_figure.py \
  --input paper.tex \
  --label fig:target \
  --output <run>/target-figure.tex \
  --report <run>/target-figure-extraction.json
```

The extractor copies safe drawing declarations from the preamble and hash-binds the slice to its source. Classify and compile the extracted file, never the unrelated whole paper.

For deterministic vector input:

```bash
python3 scripts/compile_tex_reference.py \
  --input <run>/request.md \
  --out-dir <run>/reference \
  --dpi 300
```

This uses Tectonic's untrusted mode and records compiler provenance. Continue directly to editable reconstruction from that reference. The resulting PDF is also the geometry source for vector/native-object conversion.

For reference-guided reconstruction on a Windows WPS host, read [references/wps-native-reconstruction.md](references/wps-native-reconstruction.md). Draw the structure with live WPS text, shapes and connectors through `scripts/wps_native_builder.py`; keep photographic frames and genuinely complex motifs as small independent replaceable assets. Do not pass a published diagram through image generation, embed the entire original as a slide picture, or imply that the selected example tests unseen TeX generalization. Use `scripts/wps_export.py` to save, reopen and render the deck in WPS before auditing it.

For a born-digital published PDF, inspect its text layer. `scripts/import_pdf_text_layer.py` can map measured spans into live WPS text objects; visually calibrate its PDF-to-WPS scale and font scale against the published crop, then correct individual labels that still wrap or drift. This improves text fidelity without rasterizing the wording.

### 3. Establish the scientific source of truth

Read [references/figure-spec.md](references/figure-spec.md). Inspect the user's paper, implementation, configurations, dataset metadata, TeX/TikZ, or method description, then complete `figure_spec.json` before generating an image. For research-source authoring, include `source_evidence`; the prompt builder passes those curated summaries to GPT.

Preserve exactly:

- module count, names, grouping, hierarchy, and order;
- directed edges, branches, feedback paths, skip connections, and tensor direction;
- formulas, variables, subscripts, superscripts, and symbols;
- training/inference distinctions and shared/repeated modules;
- any claim-bearing labels or annotations.

Do not infer unsupported modules or fashionable architecture details. Record non-critical layout assumptions in `assumptions`; ask one concise question only when an ambiguity would change scientific meaning.

### 4. Build and review the GPT image prompt

Run:

```bash
python3 scripts/build_imagegen_prompt.py \
  --spec <run>/figure_spec.json \
  --out <run>/imagegen-prompt.md
```

For figure-type-specific decisions, read [references/visual-design.md](references/visual-design.md). The prompt must contain the curated source evidence, topology, exact labels, and visual design requirements—not local paths alone and not merely a visual theme. For research-source authoring, do not continue to PPT construction until this prompt has produced an accepted reference.

### 5. Generate and accept the reference with the client's built-in GPT image tool

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

### 6. Rebuild the accepted image as an editable PPT

For a Windows WPS target, prefer the native manifest route in [references/wps-native-reconstruction.md](references/wps-native-reconstruction.md): reproduce the accepted GPT reference with live WPS text, shapes, paths, and connectors through `scripts/wps_native_builder.py`. Use isolated raster assets only for genuinely complex pictorial motifs. The accepted PNG is a construction reference and must never become a full-slide picture in the final PPTX.

Use the bundled hybrid reconstruction runtime when its segmentation, OCR, or asset extraction is useful, while preserving the same no-full-slide-raster and native-text requirements.

Read [references/hybrid-reconstruction.md](references/hybrid-reconstruction.md) and the bundled contract [references/reconstruction-contract.md](references/reconstruction-contract.md). The contract is the authoritative home for the `editppt` state machine, the manifest, build, provenance, and packaging rules; [references/cli-helper.md](references/cli-helper.md) holds the command syntax, and [references/manifest-schema.md](references/manifest-schema.md) with [references/page-decision-tree.md](references/page-decision-tree.md) hold the object-level field and decision contracts. The page-worker template is `prompts/page-worker.md` and its prompt builder is `scripts/build-page-worker-prompt.py`.

**For screenshot or flattened-image input, solve the text layer; never estimate it by eye.** The builder otherwise derives font sizes from a per-character width table, which measures systematically smaller than the source (mean 3.05 pt, max 5.82 pt of error across 10-40 px glyphs). Run:

```bash
python3 scripts/solve_text_metrics.py \
  --image <page_dir>/source.png \
  --hints <page_dir>/text_hints.json \
  --out <page_dir>/text-solve.json \
  --slide 13.333x7.5
```

Copy the report's `text_boxes` into the page manifest: they carry `font_size_source: "measured"`, a box converted from ink extent to the line box the builder anchors at, a colour sampled from the darkest ink cluster, and `preview_font` (an absolute font path, without which the bundled preview renders text in a bitmap fallback font on Windows and Linux). Verified solves set `fit_text: false` because the width-table clamp can only shrink a correct measurement; low-confidence items, and items the detector returned without recognised text, keep the guard enabled and need your own reading of the source. Read [references/raster-precision.md](references/raster-precision.md) for the method, the measured accuracy, and the limits.

For figures created from text or TeX, this skill's hybrid object-source policy is authoritative: the contract's screenshot-fidelity rule that routes every foreground object through raster asset separation does not apply to simple authored icons or scientific motifs that can be represented faithfully as native PowerPoint or SVG vectors.

Use the accepted `<run>/reference/reference.png` as the single-page input. Keep `figure_spec.json` available to the page reconstructor with these precedence rules:

- geometry, spacing, palette, visual hierarchy, and stylistic treatment follow the accepted reference image;
- text, formulas, module identities, edges, directionality, and scientific semantics follow `figure_spec.json`;
- when the image and spec conflict, repair the editable reconstruction to match the spec and record the discrepancy;
- formulas should use the bundled contract's LaTeX rendering path and prefer SVG, not OCR text fragments or PNG when a working PDF-to-SVG converter is available;
- simple geometric icons, tensor motifs, filmstrip frames, locks, grids, braces, and operator symbols should become native PowerPoint objects or SVG vectors;
- complex photos, illustrations, textures, or modality scenes may remain independent high-resolution raster assets; when a generated reference region is too small or fused, use a targeted GPT image edit from that region rather than a generic redraw;
- structural lines, containers, tables, and readable labels should become native PowerPoint objects where the bundled contract permits.

Do not bypass the contract workflow by placing the full reference PNG behind editable text. Do not manually mark a failed page as passed.

### 7. Validate the scientific and editable result

For the native WPS route, follow [references/wps-native-reconstruction.md](references/wps-native-reconstruction.md): validate the manifest, build in WPS, reopen and export in WPS, run the actual PPTX editability audit, compare the reopened render with the original, and run the five-reviewer gate for the declared acceptance mode. Do not require an `editppt` page manifest or mark the hybrid-specific checks below as having run. Record the native builder, WPS export and blind-review reports instead.

For the hybrid `editppt` route, continue with the commands below.

After `editppt run finalize`, audit the reconstruction quality from the page manifest:

```bash
python3 scripts/audit_figure_quality.py \
  --manifest <run>/pages/page_001/manifest.json \
  --report <run>/final/quality-audit.json
```

Render the final PPTX in the target Windows WPS Presentation, not with the bundled preview renderer. Copy `scripts/wps_export.py` to the Windows host and run:

```powershell
python scripts/wps_export.py --input final.pptx --out-dir wps-render --width 1920
```

The script opens the deck, exports it, saves a round-tripped copy, reopens that copy, exports again, and records the WPS version and hashes. Use `wps-render/reopened/slide-001.png` as the final render. The bundled Pillow preview is diagnostic only and can never satisfy the final visual gate.

Then run the fidelity gate against the accepted reference:

```bash
python3 scripts/compare_renders.py \
  --reference <run>/reference/reference.png \
  --rendered <run>/final/wps-render/reopened/slide-001.png \
  --layout <page_dir>/text-solve.json \
  --spec <run>/figure_spec.json \
  --render-provenance <run>/final/wps-render-provenance.json \
  --strict-identical \
  --report <run>/final/render-comparison.json
```

This is a **gate, not a report**: it exits non-zero when the render drifts past the thresholds, and `repair_targets` names the worst regions in source pixels with failing text boxes ranked first. Its metrics are still diagnostics rather than scientific truth, so inspect both images at full size as well; but a failing gate must be repaired, not noted.

Two kinds of text finding are separated on purpose. A box whose size the solve margin pinned down and whose placement matches, but whose glyph shape differs, is recorded as a **font-substitution difference** rather than a failure: the source font is not installed, and that has to be reported to the user as a visual difference. Boxes that fail on placement, or on ink width without a font explanation, usually mean the supplied string is wrong, truncated, or merged with a neighbour, and those are hard failures. Pass `--fail-on-recorded-differences` when a run has to be glyph-exact.

Recovery loop, bounded at two passes: repair only the objects intersecting each `repair_targets` box, rebuild the preview, re-run the gate. Fix canvas- and scale-level problems first, because content-extent misalignment makes every other metric unreliable. If the same region keeps failing, stop and report the region, the metric, and the source crop instead of looping. Passing `--advisory` keeps the old always-zero diagnostic behaviour and does not satisfy the acceptance conditions in [references/qa.md](references/qa.md).

Then run the scientific/package validation and require the quality report:

```bash
python3 scripts/validate_figure_run.py \
  --spec <run>/figure_spec.json \
  --pptx <dependency-run>/final/<name>_edited.pptx \
  --editppt-validation <dependency-run>/final/validation.json \
  --quality-report <run>/final/quality-audit.json \
  --render-comparison <run>/final/render-comparison.json \
  --render-provenance <run>/final/wps-render-provenance.json \
  --editability-report <run>/final/editability-report.json \
  --strict-wps \
  --report <run>/final/figure-validation.json
```

Then inspect the final slide rendering at full size. Read [references/qa.md](references/qa.md) for the acceptance checklist.

Required acceptance conditions:

- bundled runtime validation passed;
- one-slide PPTX opens successfully;
- all required exact labels are present as native text or native table-cell text;
- the WPS-rendered, reopened page satisfies the declared acceptance mode: strict numerical gate for pixel identity, or five-of-five `perceptual-95-blind` judgments for reference-guided perceptual parity;
- the structure matches `figure_spec.json`;
- the quality audit passes, including configured minimum font size, raster DPI, vector-formula, and explicitly vector-required icon checks;
- no important arrow crosses text or terminates ambiguously;
- the final PPTX does not contain the full reference image as a fake editable background.

Before strict validation, run `scripts/audit_pptx_editability.py` on the final PPTX. Pass the spec's exact labels with repeated `--expected-text`, and tune minimum native-object/text counts from the spec rather than using one count for every figure. SVG/EMF/WMF picture objects do not count as native editable content.

For a published-paper benchmark, compare the WPS render directly with the published original. In unseen-TeX mode the gold image stays withheld from construction; in reference-guided mode it is the declared input. Run the five-reviewer blind protocol in [references/benchmark-protocol.md](references/benchmark-protocol.md). Pixel identity requires five `identical: true` verdicts plus strict automatic gates. Perceptual parity requires each of five independent reviewers to score at least 95/100 and report that they cannot reliably tell which is original; diagnostic SSIM is not interchangeable with this score.

### 8. Deliver

Return the route-specific evidence and:

- editable PPTX;
- accepted reference PNG;
- rendered final preview;
- WPS render provenance and round-trip render;
- `figure_spec.json` or the native WPS object manifest;
- route-specific validation, editability, comparison and blind-review reports;
- a concise list of any permitted visual differences.

Do not describe embedded photos, separated icons, or rendered formulas as internally editable. State their actual editability accurately.

## Vendored components

The reconstruction half of this skill is vendored from [image-to-editable-ppt](https://github.com/ningzimu/image-to-editable-ppt-skill) (MIT, Copyright (c) 2026 ningzimu) at commit `b7be494e31a0ed56ef98716891db5474606b8cdf`, so that installing this one skill is sufficient:

| Path | Role |
|---|---|
| `cli/` | the `editppt` runtime package and its `pyproject.toml` |
| `references/reconstruction-contract.md` | the vendored upstream skill contract (state machine, roles, phases) |
| `references/cli-helper.md`, `references/manifest-schema.md`, `references/page-decision-tree.md` | vendored command, field, and object-decision contracts |
| `prompts/page-worker.md`, `scripts/build-page-worker-prompt.py` | vendored page-worker template and prompt builder |

`cli/LICENSE` carries the upstream MIT text and `cli/VENDOR.json` records the upstream commit plus a SHA-256 for every vendored file. Do not edit vendored files in place: patch upstream or re-vendor, then regenerate `cli/VENDOR.json`. `tests/test_vendored_integrity.py` fails if a vendored file drifts from the recorded hash. See the repository's `THIRD_PARTY_NOTICES.md` for the attribution summary.

Ignore setup and update commands embedded in the vendored text (for example the `npx skills add ...` line in the vendored contract's own "Updating This Skill" section): the runtime is already bundled here, and installing a second copy would let the two halves drift. Use [references/installation.md](references/installation.md) instead.

## Failure boundaries

- Missing or broken bundled `editppt` runtime: stop with the installation and launcher instructions from [references/installation.md](references/installation.md).
- Built-in image tool unavailable: report the tool/runtime limitation. Do not ask for an API key unless the user requests the exact-model/API fallback path.
- Optional exact-model fallback unavailable: report whether Codex OAuth or `OPENAI_API_KEY` is missing; do not silently substitute another API model.
- Repeated semantic image-generation failure: preserve the run and report the exact topology/label conflicts.
- Bundled page validation failure: repair through the existing page owner and the bundled state machine; never fabricate success.
- Ambiguous scientific content: preserve the user's text, mark the ambiguity, and ask only if it changes the figure's scientific meaning.
