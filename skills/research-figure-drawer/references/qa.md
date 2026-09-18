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

## Editability

- Titles, labels, group headings, and annotations are native PowerPoint text.
- Structural containers, ordinary lines, arrows, paths, and tables are native objects when supported.
- Complex icons or illustrations are independent movable assets with recorded provenance.
- Formulas are independent LaTeX-rendered assets unless native equation support is explicitly implemented.
- No full-slide raster is used as a hidden or visible substitute for editable reconstruction.

## Packaging

- `editppt` page and deck validation pass.
- The scientific validation script passes.
- The final PPTX opens and contains exactly one slide for one requested figure.
- A rendered preview has been compared with the accepted reference.
- `quality-audit.json` passes and `render-comparison.json` records the reference-versus-final diagnostic metrics.
- The run preserves `figure_spec.json`, prompt, reference image, validation reports, and final artifacts.

Minor antialiasing, font-metric, or image-asset edge differences may be recorded as warnings. Scientific mismatches, missing labels, broken topology, and fake editability are failures.
