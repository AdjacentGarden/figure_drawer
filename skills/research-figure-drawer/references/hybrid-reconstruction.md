# Reference-guided hybrid reconstruction

Use this policy only for figures authored from research text, TeX, TikZ, or a scientific specification. Keep the accepted GPT reference image as the composition and style target. Do not reduce it to a disposable OCR source, and do not copy it into the final slide as a full-page raster.

## Object-source decision

Choose the final representation by what the object is, not by how it happened to appear in the generated PNG:

| Object | Preferred final source |
|---|---|
| Titles, labels, annotations | Native PowerPoint text |
| Containers, cards, queues, timelines, arrows, braces, grids | Native PowerPoint shapes and paths |
| Simple geometric icons and scientific motifs | Native PowerPoint or SVG vector |
| Formulas supplied by the scientific spec | LaTeX-rendered SVG |
| Photos, scene thumbnails, textures, complex illustrations | Independent high-resolution raster |

Simple vector candidates include locks, filmstrip frames, feature cubes, tensor stacks, magnifiers, gears, database cylinders, checkmarks, crosses, operator nodes, and small modality symbols. Rebuild these from the reference's geometry, palette, stroke width, and proportions. They are authored visual vocabulary, not source-image evidence that must remain raster.

On Windows, a PDF-to-SVG converter may emit formulas with reusable `<symbol>/<use>` glyphs that PowerPoint does not render reliably. If a full PowerPoint/WPS render shows missing formula glyphs, run `scripts/flatten_svg_uses.py --input <raw.svg> --output <powerpoint.svg>` and use the flattened file. This is a deterministic compatibility transform; verify the PowerPoint-rendered result before accepting it.

Complex raster assets should preserve the GPT reference's identity. If the full reference does not contain enough pixels or the asset is fused with neighbors, make a targeted GPT image edit using the inspected local reference/crop as input. Ask for one isolated object, transparent or chroma-key background, generous margins, no label text, and enough detail for at least 300 effective DPI at the intended placement. Do not regenerate the entire figure merely to improve one asset.

## Reference fidelity

Before reconstruction, record a small style token set from the accepted reference:

- canvas and content bounds;
- group and module boxes;
- dominant fill, stroke, and accent colors;
- typical stroke width and corner radius;
- title, group-heading, body-label, and micro-annotation levels;
- primary, conditioning, residual, and supervision connector styles.

Use these tokens consistently across native and SVG objects. Scientific text and topology still come from `figure_spec.json` when the generated pixels disagree.

## Quality policy

Copy the `figure_spec.json.reconstruction` values into the page manifest as `quality_policy`. Mark intentionally tiny annotations with `text_role: "micro"`; ordinary labels default to `body`. Mark simple SVG/native icon inventory entries with `vector_required: true`. Formula inventory should point to SVG unless the environment has no working PDF-to-SVG path and the failure is recorded.

Run `audit_figure_quality.py` after building the page. Fix failures rather than weakening thresholds for one crowded composition. If many labels do not fit at the minimum size, reduce visual density, shorten non-claim-bearing annotations, or increase the figure's publication footprint.

Render the final slide at the same aspect ratio as the accepted reference and run `compare_renders.py`. Its pixel metrics help detect large composition or palette drift, but they never override the scientific specification or visual inspection.
