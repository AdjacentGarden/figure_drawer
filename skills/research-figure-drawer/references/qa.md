# Acceptance and QA

Evaluate the result in four layers.

## Scientific correctness

- Module and group counts match `figure_spec.json`.
- All edges have the correct endpoints and direction.
- Branches, skip connections, feedback, supervision, and shared weights are represented correctly.
- Exact labels and formulas match the user's source.
- No invented results, datasets, metrics, modules, or causal claims appear.

## Visual quality

- The figure remains legible at typical two-column paper width.
- Visual hierarchy is obvious without reading every label.
- Spacing and alignment are consistent.
- Lines do not cross text or terminate ambiguously.
- Colors remain distinguishable in grayscale and do not carry meaning alone.
- Decorative details do not compete with the method contribution.
- Body labels meet the configured minimum font size; micro-annotations remain a minority and meet their separate minimum.
- Raster assets meet the configured effective DPI at their placed size.
- Simple icons and formulas marked as vector-required are SVG, EMF, or native PowerPoint objects.
- The reopened WPS export is compared with the target. Require the strict numerical gate only for `pixel-identical` mode. For `perceptual-95-blind`, use those metrics to locate repair targets; five independent 95/100-or-higher judgments and inability to identify the original form the perceptual gate. Neither mode waives scientific topology, readable labels, or editability.

## Raster input

For screenshot or flattened-image input, text geometry is measured, not estimated:

- `scripts/solve_text_metrics.py` produced the `text_boxes` geometry, and verified
  solves carry `font_size_source: "measured"` with `fit_text: false`.
- Items the solver marked low confidence, or `hint-only` because the detector returned
  no recognised text, were reviewed by reading the source and keep `fit_text` enabled.
- `scripts/compare_renders.py` passed as a gate (not `--advisory`), and `repair_targets`
  was empty or its regions were repaired and re-verified.
- The font actually used is recorded, and any substitution away from the source font is
  reported as a visual difference rather than passed silently. A run is only glyph-exact
  when the gate was invoked with `--fail-on-recorded-differences` and passed.
- On dense pages the bundled detector will miss lines: the report states how many lines the
  detector found versus how many were solved, and the difference was filled from the source
  (OCR, or the PDF text layer for born-digital input) rather than dropped.

## Editability

- Titles, labels, group headings, and annotations are native PowerPoint text.
- Structural containers, ordinary lines, arrows, paths, and tables are native objects when supported.
- Complex icons or illustrations are independent movable assets with recorded provenance. Photographs in paper figures may be isolated as separate replaceable raster objects; do not include adjacent labels, borders, filmstrip rails or arrows in those crops.
- Formulas are independent LaTeX-rendered assets unless native equation support is explicitly implemented.
- No full-slide raster is used as a hidden or visible substitute for editable reconstruction.

## Packaging

- `editppt` page and deck validation pass.
- The scientific validation script passes.
- The final PPTX opens in WPS, survives save/reopen, and contains exactly one slide for one requested figure.
- A rendered preview has been compared with the accepted reference.
- `quality-audit.json` passes and `render-comparison.json` records the reference-versus-final diagnostic metrics.
- In pixel-identity mode, `render-comparison.json` must pass the strict gate. In reference-guided perceptual mode, retain diagnostic comparison metrics, five raw verdicts and the aggregate perceptual-gate report; never label diagnostic SSIM as a human similarity percentage.
- The run preserves `figure_spec.json`, prompt, reference image, validation reports, and final artifacts.

Minor antialiasing differences may be recorded for normal delivery. They are failures in `--strict-identical` benchmark mode. Scientific mismatches, missing labels, broken topology, unverified WPS rendering, and fake editability are always failures. A failed blind round remains a failure even when the picture looks broadly similar to the author.

Run `audit_pptx_editability.py` against the final OOXML. Strict runs reject a single large picture, tiled page images, off-slide or hidden shape padding, missing expected native text, and insufficient in-bounds native-object coverage. Vector pictures remain picture objects and do not satisfy native-editability coverage.
