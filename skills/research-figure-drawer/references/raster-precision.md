# Raster precision

Use this reference when the input is a screenshot, a flattened slide image, or any
raster that has no vector source. Everything here is deterministic and measures the
raster instead of estimating it.

## Why the default path is imprecise for rasters

The deterministic builder derives a text box's font size from a per-character width
table (0.55 em for ASCII, `DEFAULT_TEXT_FIT_SAFETY = 0.9`, `DEFAULT_TEXT_LINE_HEIGHT
= 1.22`). Measured against synthetic ground truth at seven sizes (10–40 px glyphs on a
1280x720 page), that estimate is systematically **smaller** than the source:

| Method | Mean abs error | Max error |
|---|---|---|
| Width-table estimate (default safety) | 3.05 pt | 5.82 pt |
| Width-table estimate with `font_size_source: "measured"` | 1.58 pt | 3.14 pt |
| `solve_text_metrics.py` (real glyph metrics) | **0.01 pt** | 0.05 pt |

This is why text comes out smaller and slightly misplaced, and it is also why the hint
detector inflates every ink box by 0.35/0.30 glyphs to compensate. Measuring removes
both workarounds.

## 1. Solve the text layer before writing the manifest

```bash
python3 scripts/solve_text_metrics.py \
  --image <page_dir>/source.png \
  --hints <page_dir>/text_hints.json \
  --out <page_dir>/text-solve.json \
  --slide 13.333x7.5
```

For each hinted line the solver:

1. binarises the source crop around the hint box into an ink mask;
2. estimates the size from real advance widths for every candidate font, then
   rasterises the string and scores it against the source ink by mask IoU;
3. converts the winning **ink box** into the **line box** the builder anchors at
   (zero insets, top anchor, so ink top = box top + the font's ink offset);
4. samples the text colour from the darkest ink cluster, not a background-blended mean;
5. emits manifest-ready `text_boxes` with `font_size_source: "measured"`.

It also emits `preview_font` as an absolute font path. The bundled preview renderer
resolves fonts from a macOS-only candidate list, so on Windows and Linux its preview
text silently falls back to a bitmap default font unless the manifest supplies a real
path. Passing `preview_font` is what makes the preview usable for visual QA.

Copy `text_boxes` from the report into the page manifest, then continue with the normal
page workflow. Items the solver marks `low` confidence, or `hint-only` because the
detector returned no recognised text, keep `fit_text` enabled so the builder's guard
still protects them; a verified solve sets `fit_text: false`, because the width-table
clamp can only shrink a correct measurement.

Verified accuracy on synthetic ground truth (10–40 px glyphs):

- font size: mean error 0.009 px, max 0.06 px (0.01 pt / 0.05 pt at 96 px per inch);
- ink placement: mean 1.1 px horizontally, 1.0 px vertically, max 2.0 px;
- ink IoU between the solved rendering and the source: 0.80–0.99.

## 2. Close the loop with the fidelity gate

`compare_renders.py` is a **gate**, not a report: it exits non-zero when the render
drifts beyond the thresholds. Run it on the preview (or the exported PNG) and pass the
solved layout so text is checked per box:

```bash
python3 scripts/compare_renders.py \
  --reference <page_dir>/source.png \
  --rendered <page_dir>/preview.png \
  --layout <page_dir>/text-solve.json \
  --report <page_dir>/fidelity.json
```

It reports four independent signals:

| Signal | Catches |
|---|---|
| Global SSIM and per-tile SSIM | structural drift, wrong shapes, missing decoration |
| Content-extent alignment (offset + scale) | canvas, padding, and scale errors — fix these first, everything else is unreliable while they are wrong |
| Lost-ink tiles | source strokes absent from the render, with a 1 px registration tolerance |
| Per-text-box ink check | `missing_text`, `misaligned`, `size_mismatch` per box |

`repair_targets` lists the worst regions in source pixels, ranked with failing text
boxes first. That list is the input to the next pass.

Recovery loop, bounded:

1. repair only the objects intersecting each `repair_targets` box;
2. rebuild the preview;
3. re-run the gate;
4. repeat at most twice. If the same region keeps failing, stop and report the region,
   the metric, and the source crop instead of looping.

Pass `--advisory` to get the old always-exit-zero diagnostic behaviour.

> A mostly-white tile barely moves SSIM when a thin text line is deleted, so tile SSIM
> alone is not a sufficient gate. The lost-ink channel and the per-box text checks exist
> precisely because of that blind spot, and both are covered by tests.

## Limits to state honestly

- **The font must be available.** The solver identifies the closest installed candidate
  by ink IoU and records it. If the true font is missing, the size is still right for
  what was chosen, but glyph shapes will differ; report that as a recorded difference.
- **Low confidence means review, not trust.** Multi-line hints, rotated text, heavy
  antialiasing, and glyphs under ~8 px may not solve reliably; those items stay guarded
  by `fit_text` and must be checked by reading the source.
- **Measurement is not PowerPoint's own layout engine.** Sizes and origins are solved
  from real glyph metrics, and PowerPoint's line breaking and autofit can still differ
  slightly. That is why the gate exists: it verifies the render instead of trusting the
  model.
- **This is not a license to skip the source.** The gate detects drift, not meaning.

## The high-fidelity alternative that is deliberately not implemented

For raster input, the highest pixel fidelity comes from a **two-track** page: the source
raster as a locked background layer plus native text on top. It is not implemented here
because the vendored contract classifies a full-slide source raster with editable text
overlay as fake editability, and `validate_pptx.py` rejects that pattern. Adding it would
mean changing the upstream contract and its validator, not just adding a flag. If a user
only needs editable text and accepts a non-editable figure layer, say so explicitly and
keep the label honest rather than calling the result fully editable.
