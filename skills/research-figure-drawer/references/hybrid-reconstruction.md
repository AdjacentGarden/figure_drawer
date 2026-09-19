# Reference-guided hybrid reconstruction

Use this policy only for figures authored from research text, TeX, TikZ, or a scientific specification. Keep the accepted GPT reference image as the composition and style target. Do not reduce it to a disposable OCR source, and do not copy it into the final slide as a full-page raster.

## Why reference-to-PPT conversions degrade

The generated reference and the editable slide solve different problems. An image model can paint a convincing whole without producing exact object bounds, shared vertices, font metrics, or routing lanes. During reconstruction, native fonts reflow, SVG formulas acquire different bounding boxes, and connector endpoints are approximated from pixels. If the workflow validates only that objects exist, a deck can pass while text overlaps borders, arrows cross labels, formulas remain pictures, and regular geometry is visibly inconsistent.

Treat these as pipeline defects, not isolated drawing mistakes:

- **representation mismatch:** raster pixels do not encode which items must be editable or geometrically exact;
- **metric drift:** PowerPoint/WPS font, formula, and SVG metrics differ from the generated PNG;
- **missing keep-out zones:** labels and equations have boxes, but connectors are not routed around them;
- **weak acceptance tests:** package validity and font size do not prove collision-free layout;
- **wrong primitive choice:** a simple cube or tensor grid reconstructed as an image preserves generated imperfections instead of enforcing canonical geometry.

The repair is constraint-first reconstruction. Keep the GPT result for composition, palette, hierarchy, and illustration quality, while rebuilding semantic primitives from explicit constraints and rejecting the result when the post-render geometry audit fails.

## Object-source decision

Choose the final representation by what the object is, not by how it happened to appear in the generated PNG:

| Object | Preferred final source |
|---|---|
| Titles, labels, annotations | Native PowerPoint text |
| Containers, cards, queues, timelines, arrows, braces, grids | Native PowerPoint shapes and paths |
| Simple geometric icons and scientific motifs | Native PowerPoint geometry first; SVG only when the motif cannot be expressed cleanly with native primitives |
| Formulas supplied by the scientific spec | Editable OfficeMath object when supported; LaTeX-rendered SVG as an explicit non-editable fallback |
| Photos, scene thumbnails, textures, complex illustrations | Independent high-resolution raster |

Simple vector candidates include locks, filmstrip frames, feature cubes, tensor stacks, magnifiers, gears, database cylinders, checkmarks, crosses, operator nodes, and small modality symbols. Rebuild these from the reference's geometry, palette, stroke width, and proportions. They are authored visual vocabulary, not source-image evidence that must remain raster.

For regular geometry, encode invariants rather than tracing pixels. A three-face isometric cube uses three native parallelograms with shared seam vertices, one shared center vertex, parallel opposite edges, and a single consistent projection. Repeated cells use exact spacing. Grids share baselines. The manifest may mark cube faces with `geometry_role: "isometric-cube-face"`, `cube_id`, and `face: top|left|right`; `audit_layout_geometry.py` validates those relationships.

## Constraint-first build order

1. **Budget the canvas.** Lay out groups, modules, formula lanes, and connector corridors before decorating anything. If labels cannot fit at the minimum font size with padding, reduce density or enlarge the figure; do not shrink text until it happens to fit.
2. **Classify by semantics.** Decide native text, native geometry, native equation, vector fallback, or raster illustration before cropping assets.
3. **Build structural primitives.** Create panels, module boxes, canonical icons, and text boxes with stable IDs. Use optional `container_id` relationships when containment matters.
4. **Reserve keep-out boxes.** Every text box and formula entry must have `box_px`. Connectors must avoid the inset interior of these boxes.
5. **Route connectors last.** Use orthogonal lanes and attach to module boundaries. A line may enter a node boundary but must not pass through title, label, or formula ink.
6. **Render and audit.** Run manifest collision/geometry checks, render through PowerPoint/WPS, inspect at full resolution, and revise. One successful package build is not visual acceptance.

Do not trace the irregular outline of a generated simple icon merely to match pixels. Preserve its color and visual role while normalizing its geometry.

## Editable equations

On Windows with Word, PowerPoint, and `pywin32`, use `scripts/insert_native_equations.py` after the deterministic base deck is built. It creates professional OfficeMath in Word and pastes it into PowerPoint as a `Word.Document` OLE object. The object is independently movable and remains editable by opening the embedded equation document. Record each entry in `formula_inventory` with `decision: "native-office-math-ole"`, `editable: true`, `linear`, `box_px`, and `font_size`, then run `scripts/audit_native_equations.py` against the final PPTX.

PowerPoint's object model does not expose Word's `OMaths.Add`/`BuildUp` API directly, so this route is capability-gated. If it is unavailable or the target environment cannot edit Word OLE objects, render the exact LaTeX as SVG, record `editable: false`, and state the limitation. Never label an SVG formula as editable.

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

For each visible non-text motif in the reference (for example a filmstrip, tensor cube, document, state grid, histogram, or timeline), record its reference box and its intended output object(s) before building the page. A single `native-structure` inventory entry for an entire figure is not sufficient: it hides missing motifs and lets generic bars or blank cards substitute for the generated illustration. When a motif is simplified for editability, retain its visual role, scale, and placement, and record the simplification. This is an object correspondence check, not permission to trace scientifically incorrect image details.

Compare the first PowerPoint/WPS render with the accepted reference **before recording the page**, at the same aspect ratio. Check major panel bounds, occupied space within each module, icon count and identity, typography levels, and connector lanes. If a visually important reference object is absent or replaced by a placeholder, repair that page even if `editppt page validate` and the collision audit pass. `compare_renders.py` provides a drift signal; its scores do not by themselves decide acceptance because scientifically necessary changes may differ from generated pixels.

## Quality policy

Copy the `figure_spec.json.reconstruction` values into the page manifest as `quality_policy`. Mark intentionally tiny annotations with `text_role: "micro"`; ordinary labels default to `body`. Mark simple SVG/native icon inventory entries with `vector_required: true`. Formula inventory should prefer a native OfficeMath decision when the capability check succeeds and otherwise point to the explicit SVG fallback.

Run both `audit_figure_quality.py` and `audit_layout_geometry.py` after building the page. The latter rejects overlapping content boxes, connectors through text/formula keep-outs, out-of-bounds content, and malformed canonical cubes. Fix failures rather than adding broad `allow_overlap`/`allow_text_crossing` exemptions. A narrow exception must identify the exact object and explain why the overlap is semantic rather than accidental.

Render the final slide at the same aspect ratio as the accepted reference and run `compare_renders.py`. Its pixel metrics help detect large composition or palette drift, but they never override the scientific specification or visual inspection.
