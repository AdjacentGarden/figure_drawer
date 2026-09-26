# WPS-native reconstruction of published mechanism figures

Use this route when the user wants the published visual style and WPS-object editability. The published image is visible construction input. Label the result `reference-guided`, not unseen TeX reconstruction. Record paper title, venue/year, figure number, official paper URL, exact source crop and SHA-256 before drawing.

## Decompose before building

Create an object inventory from the actual figure:

1. Scientific topology: input modalities, intermediate representations, operators, branches/merges, output heads, and training/inference-only paths.
2. Layout: canvas, major zones, repeated modules, frame/sequence slots, local captions, line routing, arrows and legends.
3. Text: exact visible strings, font family/size/weight, rotation, alignment and source bounding boxes.
4. Assets: separate photograph frames or scientifically meaningful complex icons only. A permitted crop must not contain a structural border, native-readable label, connector or another editable module. Record source rectangle and whether it is raster-movable or vector-convertible.

Keep a source-observation versus inference distinction. The diagram's scientific graph is a hard constraint; do not make a prettier but semantically different drawing. Inspect the original and every WPS reopen render at full size and at paper width. If born-digital PDF text/drawing geometry is extractable, use its bounding boxes as a starting point rather than estimating every coordinate by eye.

For a text-bearing PDF, install `pymupdf` in the working environment and import measured text spans after constructing the shapes-only manifest:

```bash
python scripts/import_pdf_text_layer.py --pdf paper.pdf --page 3 \
  --crop X0 Y0 X1 Y1 --scale PDF_TO_SLIDE --origin CROP_X CROP_Y \
  --font-scale CALIBRATED_RATIO --manifest shapes.json \
  --output manifest-with-text.json --replace-text
```

The PDF page/crop is in PDF points; `origin` is the crop's top-left in slide units. `font-scale` must be calibrated by rendering a few unambiguous labels in WPS. The text layer can contain fragments or substituted fonts, so inspect every imported span, especially rotated labels and equations. This process retains live editable text but does not solve the connector geometry.

## Manifest and builder

`scripts/wps_native_builder.py` runs on Windows with WPS Presentation and `pywin32`. Its JSON manifest has a `figure_id`, `canvas: {width,height}` in WPS slide points, and an ordered `elements` array. The object types are:

- `shape`: `shape` (`rect`, `roundrect`, `ellipse`, `triangle`), `x,y,w,h`, optional `fill`, `stroke`, `stroke_width`, `dash`.
- `path`: at least two `[x,y]` `points`, or four `[x,y]` `bezier` control/end points, plus `stroke`, `stroke_width`, optional `arrow` and `dash`. The cubic route is approximated by short editable WPS line segments because WPS can omit native freeform-curve strokes from its own PNG export.
- `text`: `x,y,w,h,text`, `font,size,bold,italic,color,align,valign`, optional `rotation`. It remains live editable text.
- `image`: `file,x,y,w,h`. Use only for isolated photographs or complex motifs, never the whole figure.

Order elements back-to-front: zones, connectors, frames/photos, borders/modules, then text. Give important objects stable IDs for the WPS Selection Pane. The builder rejects missing assets, empty live text, off-canvas boxes and page-sized picture objects. Run `--validate-only` before copying the manifest to Windows.

```powershell
python scripts/wps_native_builder.py manifest.json figure.pptx --assets-dir assets
python scripts/wps_export.py --input figure.pptx --out-dir wps-render --width 1600
```

WPS may fail transiently after closing one automation process; the builder retries an unsuccessful new file up to three times. Never overwrite an existing user PPTX. Use the reopened WPS PNG as the visual evidence, not the local Pillow or LibreOffice preview.

## Acceptance

Run `scripts/audit_pptx_editability.py` on the actual PPTX. Count live text, native shapes/connectors and isolated pictures; no background reference image or tiled image substitute. Check WPS first-open/reopened pixel hashes. Use `scripts/compare_renders.py` to locate text/geometry/asset defects, but do not call SSIM a human 95% style score. In `perceptual-95-blind` mode, collect five independent origin-blind judgments using `references/benchmark-protocol.md` and aggregate with `scripts/evaluate_perceptual_benchmark.py`. Every reviewer must score at least 95 and report no reliable ability to identify the original. Report failures and original-guess accuracy honestly; do not cherry-pick reviewers or scenes.
