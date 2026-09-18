#!/usr/bin/env python3
"""Fidelity gate: compare a source raster with the reconstructed render.

This started as a diagnostic that always exited 0. For raster input that is the
weakest link in the loop, because nothing ever forces a bad region to be redone.
It now reports three things the page owner can act on:

1. structural similarity overall and per tile, so drift is localised;
2. content-extent alignment, which catches canvas/padding/scale errors;
3. per-text-box ink checks, which separate "missing", "misaligned" and
   "wrong size" instead of lumping them into one average score.

`repair_targets` lists the worst regions in source-pixel coordinates, which is
the input the next reconstruction pass needs. The command exits non-zero when
the gate fails; pass --advisory to keep the old always-zero behaviour.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat  # noqa: E402

from image_metrics import (  # noqa: E402 - sibling module, path set above
    align_ink_iou,
    boxes_from_bad_grid,
    boxes_from_tiles,
    content_alignment,
    dilate,
    ink_bbox,
    ink_mask,
    normalized_pair,
    overlap_ratio,
    ssim,
    tile_grid,
    tile_sums,
    to_gray,
)

DEFAULT_MIN_SSIM = 0.90
DEFAULT_BAD_TILE_SSIM = 0.60
DEFAULT_MAX_BAD_TILE_FRACTION = 0.05
DEFAULT_MIN_TEXT_INK_IOU = 0.55
DEFAULT_MAX_TEXT_OFFSET_PX = 3.0


# --------------------------------------------------------------------------- #
# legacy diagnostic metrics (kept for report compatibility)
# --------------------------------------------------------------------------- #


def normalized(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def edge_mask(image: Image.Image, threshold: int = 32) -> Image.Image:
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return edges.point(lambda value: 255 if value >= threshold else 0, mode="1")


def flat_pixels(image: Image.Image) -> list[int]:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())  # pragma: no cover - Pillow before 12


def legacy_metrics(reference: Path, rendered: Path, size: tuple[int, int]) -> dict:
    with Image.open(reference) as source_image, Image.open(rendered) as rendered_image:
        source = normalized(source_image, size)
        target = normalized(rendered_image, size)
    difference = ImageChops.difference(source, target)
    luma_mae = sum(ImageStat.Stat(difference.convert("L")).mean) / 255.0
    source_edge = edge_mask(source)
    target_edge = edge_mask(target)
    source_pixels = flat_pixels(source_edge)
    target_pixels = flat_pixels(target_edge)
    intersection = sum(1 for left, right in zip(source_pixels, target_pixels) if left and right)
    source_count = sum(1 for value in source_pixels if value)
    target_count = sum(1 for value in target_pixels if value)
    precision = intersection / target_count if target_count else 0.0
    recall = intersection / source_count if source_count else 0.0
    edge_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    source_mean = ImageStat.Stat(source).mean
    target_mean = ImageStat.Stat(target).mean
    mean_color_distance = sum(abs(left - right) for left, right in zip(source_mean, target_mean)) / (3 * 255)
    return {
        "luminance_mae": round(luma_mae, 4),
        "edge_precision": round(precision, 4),
        "edge_recall": round(recall, 4),
        "edge_f1": round(edge_f1, 4),
        "mean_color_distance": round(mean_color_distance, 4),
    }


# --------------------------------------------------------------------------- #
# text checks
# --------------------------------------------------------------------------- #


def load_text_boxes(layout: str | Path | None, manifest: str | Path | None) -> tuple[list[dict], str | None]:
    if layout:
        layout_path = Path(layout).expanduser().resolve()
        payload = json.loads(layout_path.read_text(encoding="utf-8"))
        return list(payload.get("text_boxes") or []), str(layout_path)
    if manifest:
        manifest_path = Path(manifest).expanduser().resolve()
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return list(payload.get("text_boxes") or []), str(manifest_path)
    return [], None


def check_text_boxes(
    reference_mask: np.ndarray,
    rendered_mask: np.ndarray,
    text_boxes: list[dict],
    args: argparse.Namespace,
) -> dict:
    height, width = reference_mask.shape
    margin = args.text_margin_px
    items: list[dict] = []
    for index, box in enumerate(text_boxes):
        solve = box.get("_solve") or {}
        # Prefer the ink box the solver measured: the padded box_px can overlap a
        # neighbouring line, and comparing that overlap would report a placement
        # error that does not exist.
        raw = solve.get("ink_box_px") or box.get("box_px")
        if not raw or len(raw) != 4:
            continue
        left = max(0, int(round(float(raw[0]))) - margin)
        top = max(0, int(round(float(raw[1]))) - margin)
        right = min(width, int(round(float(raw[0]) + float(raw[2]))) + margin)
        bottom = min(height, int(round(float(raw[1]) + float(raw[3]))) + margin)
        if right <= left or bottom <= top:
            continue
        reference_crop = reference_mask[top:bottom, left:right]
        rendered_crop = rendered_mask[top:bottom, left:right]
        reference_ink = ink_bbox(reference_crop)
        rendered_ink = ink_bbox(rendered_crop)
        confidence = str((box.get("_solve") or {}).get("confidence", "unknown"))
        record = {
            "index": index,
            "text": str(box.get("text", ""))[:80],
            "box_px": [left, top, right - left, bottom - top],
            "confidence": confidence,
        }
        if reference_ink is None:
            record["status"] = "no_source_ink"
            items.append(record)
            continue
        if rendered_ink is None:
            record["status"] = "missing_text"
            items.append(record)
            continue
        iou, shift = align_ink_iou(reference_crop, rendered_crop, max_shift=args.align_shift)
        # Placement is judged by the ink anchors (left/top of the box), not by the
        # centroid: the centroid moves when a substituted font changes line width,
        # while the left-aligned anchor does not.
        left_delta = rendered_ink[0] - reference_ink[0]
        top_delta = rendered_ink[1] - reference_ink[1]
        reference_centre = (reference_ink[0] + reference_ink[2] / 2, reference_ink[1] + reference_ink[3] / 2)
        rendered_centre = (rendered_ink[0] + rendered_ink[2] / 2, rendered_ink[1] + rendered_ink[3] / 2)
        centroid_offset = (rendered_centre[0] - reference_centre[0], rendered_centre[1] - reference_centre[1])
        width_ratio = rendered_ink[2] / reference_ink[2] if reference_ink[2] else 1.0
        height_ratio = rendered_ink[3] / reference_ink[3] if reference_ink[3] else 1.0
        record.update(
            {
                "ink_iou": round(iou, 4),
                "anchor_offset_px": [round(left_delta, 2), round(top_delta, 2)],
                "centroid_offset_px": [round(centroid_offset[0], 2), round(centroid_offset[1], 2)],
                "size_ratio": [round(width_ratio, 3), round(height_ratio, 3)],
            }
        )
        problems: list[str] = []
        if iou < args.min_text_ink_iou:
            problems.append("low_ink_similarity")
        if max(abs(left_delta), abs(top_delta)) > args.max_text_offset_px:
            problems.append("misaligned")
        if abs(width_ratio - 1.0) > args.max_text_size_ratio_delta or abs(height_ratio - 1.0) > args.max_text_size_ratio_delta:
            problems.append("size_mismatch")

        solve_margin = solve.get("size_margin")
        offset_ok = "misaligned" not in problems
        if (
            bool(solve.get("font_substitution"))
            and offset_ok
            and solve_margin is not None
            and float(solve_margin) >= args.substitution_margin
        ):
            # Placement is verified independently of the font, and the +/-10% solve
            # margin pins the size down. Ink shape and ink width then differ because
            # the source font is not installed, which is a recorded difference the
            # user must decide on rather than a silent pass or a silent failure.
            record["problems"] = ["font_substitution"]
            record["status"] = "font_substitution"
            record["recorded_difference"] = (
                "size verified by the solve margin and placement verified; glyph shape and ink width differ "
                "because the source font is not installed"
            )
        else:
            record["problems"] = problems
            record["status"] = "ok" if not problems else problems[0]
        items.append(record)

    recorded = [item for item in items if item.get("status") == "font_substitution"]
    failing = [
        item
        for item in items
        if item.get("problems") and item.get("status") != "font_substitution" and item.get("confidence") != "low"
    ]
    skipped = [
        item
        for item in items
        if item.get("problems") and item.get("confidence") == "low" and item.get("status") != "font_substitution"
    ]
    return {
        "checked": len(items),
        "failing": len(failing),
        "recorded_differences": len(recorded),
        "skipped_low_confidence": len(skipped),
        "items": items,
    }


def collect_repair_targets(
    tiles: np.ndarray,
    reference_mask: np.ndarray,
    rendered_mask: np.ndarray,
    text_report: dict,
    args: argparse.Namespace,
) -> tuple[list[dict], np.ndarray, int]:
    """Rank the regions worth rebuilding.

    Tile SSIM alone misses sparse ink defects: erasing a thin text line from a
    mostly-white 64 px tile barely moves SSIM. So a second channel looks for
    source ink that is absent in the render, and failing text boxes are added
    directly because they are the most precise signal available.
    """
    structure_boxes = boxes_from_tiles(tiles, args.tile, args.bad_tile_ssim)
    for box in structure_boxes:
        box["source"] = "tile_ssim"
        box["min_ssim"] = box["min_severity"]
        box["mean_ssim"] = box["mean_severity"]

    missing_ink = np.logical_and(reference_mask, ~dilate(rendered_mask, args.ink_tolerance_px))
    reference_ink_counts = tile_sums(reference_mask, args.tile)
    missing_counts = tile_sums(missing_ink, args.tile)
    ink_bad = (
        (reference_ink_counts >= args.min_reference_ink_px)
        & (missing_counts >= args.min_missing_ink_px)
        & (missing_counts >= args.missing_ink_ratio * np.maximum(1, reference_ink_counts))
    )
    ink_severity = np.where(reference_ink_counts > 0, missing_counts / np.maximum(1, reference_ink_counts), 0.0)
    ink_boxes = boxes_from_bad_grid(ink_bad, args.tile, 1.0 - ink_severity)
    for box in ink_boxes:
        box["source"] = "missing_ink"
        box["min_ssim"] = None
        box["mean_ssim"] = None

    text_targets = [
        {
            "box_px": item["box_px"],
            "source": "text_check",
            "status": item["status"],
            "text": item["text"],
            "tiles": None,
            "min_severity": 0.0,
            "min_ssim": None,
        }
        for item in text_report.get("items", [])
        if item.get("problems") and item.get("confidence") != "low"
    ]

    priority = {"text_check": 0, "missing_ink": 1, "tile_ssim": 2}
    merged: list[dict] = []
    for candidate in sorted(structure_boxes + ink_boxes + text_targets, key=lambda item: priority[item["source"]]):
        if any(overlap_ratio(candidate["box_px"], kept["box_px"]) >= 0.6 for kept in merged):
            continue
        merged.append(candidate)
    merged.sort(key=lambda item: (priority[item["source"]], item.get("min_severity") or 0.0))
    return merged[: args.max_repair_targets], ink_bad


# --------------------------------------------------------------------------- #
# main comparison
# --------------------------------------------------------------------------- #


def compare(reference: Path, rendered: Path, args: argparse.Namespace) -> dict:
    text_boxes, text_source = load_text_boxes(args.layout, args.manifest)
    size = (args.width, args.height) if args.width and args.height else None
    reference_rgb, rendered_rgb, normalized_size = normalized_pair(reference, rendered, size)

    with Image.open(reference) as reference_image, Image.open(rendered) as rendered_image:
        reference_size = reference_image.size
        rendered_size = rendered_image.size

    reference_gray = to_gray(reference_rgb)
    rendered_gray = to_gray(rendered_rgb)
    overall_ssim, score_map = ssim(reference_gray, rendered_gray)
    tiles = tile_grid(score_map, args.tile)

    reference_mask, _, _ = ink_mask(reference_gray)
    rendered_mask, _, _ = ink_mask(rendered_gray)
    alignment = content_alignment(reference_mask, rendered_mask)

    text_report = (
        check_text_boxes(reference_mask, rendered_mask, text_boxes, args)
        if text_boxes
        else {"checked": 0, "failing": 0, "recorded_differences": 0, "skipped_low_confidence": 0, "items": []}
    )

    repair_targets, ink_bad = collect_repair_targets(tiles, reference_mask, rendered_mask, text_report, args)
    structure_bad = tiles < args.bad_tile_ssim
    combined_bad = np.logical_or(structure_bad, ink_bad)
    tile_count = int(tiles.size)
    bad_tile_count = int(combined_bad.sum())
    missing_ink_count = int(ink_bad.sum())
    bad_fraction = bad_tile_count / tile_count if tile_count else 0.0
    missing_ink_fraction = missing_ink_count / tile_count if tile_count else 0.0

    problems: list[str] = []
    if overall_ssim < args.min_ssim:
        problems.append(f"global SSIM {overall_ssim:.4f} is below the {args.min_ssim:.4f} threshold")
    if bad_fraction > args.max_bad_tile_fraction:
        problems.append(
            f"{bad_tile_count}/{tile_count} tiles ({bad_fraction:.1%}) are below SSIM {args.bad_tile_ssim:.2f} "
            f"or lost source ink, above the allowed {args.max_bad_tile_fraction:.1%}"
        )
    if missing_ink_fraction > args.max_missing_ink_fraction:
        problems.append(
            f"{missing_ink_count}/{tile_count} tiles ({missing_ink_fraction:.1%}) lost source ink, "
            f"above the allowed {args.max_missing_ink_fraction:.1%}"
        )
    if abs(reference_size[0] / reference_size[1] - rendered_size[0] / rendered_size[1]) > 0.01:
        problems.append(f"aspect ratio differs: source {reference_size} vs rendered {rendered_size}")
    reference_has_ink = bool(reference_mask.any())
    rendered_has_ink = bool(rendered_mask.any())
    if reference_has_ink and not rendered_has_ink:
        # A blank render still scores well on SSIM for a mostly-white page, so
        # "no ink at all" has to be an explicit failure rather than a metric dip.
        problems.append("rendered image contains no detectable ink: the render is blank or unreadable")
    elif alignment.get("comparable"):
        offset = alignment["offset_px"]
        if max(abs(offset[0]), abs(offset[1])) > args.max_content_offset_px:
            problems.append(f"content extent is offset by {offset} px, above the {args.max_content_offset_px} px tolerance")
        scale = alignment["scale_ratio"]
        if abs(scale[0] - 1.0) > args.max_content_scale_delta or abs(scale[1] - 1.0) > args.max_content_scale_delta:
            problems.append(f"content extent is scaled by {scale} instead of ~1.0")
    if text_report.get("failing"):
        problems.append(f"{text_report['failing']} text boxes failed fidelity checks")
    if args.fail_on_recorded_differences and text_report.get("recorded_differences"):
        problems.append(
            f"{text_report['recorded_differences']} text boxes are recorded font-substitution differences "
            "(strict mode treats them as failures)"
        )

    report = {
        "schema_version": 2,
        "reference": str(reference),
        "rendered": str(rendered),
        "normalized_size": list(normalized_size),
        "source_size": list(reference_size),
        "rendered_size": list(rendered_size),
        "metrics": {
            **legacy_metrics(reference, rendered, normalized_size),
            "ssim": round(overall_ssim, 4),
            "tile_ssim_min": round(float(tiles.min()), 4),
            "tile_ssim_mean": round(float(tiles.mean()), 4),
            "tile_size_px": args.tile,
            "tile_count": tile_count,
            "bad_tile_count": bad_tile_count,
            "bad_tile_fraction": round(bad_fraction, 4),
            "lost_ink_tile_count": missing_ink_count,
            "lost_ink_tile_fraction": round(missing_ink_fraction, 4),
        },
        "content_alignment": alignment,
        "text_checks": text_report,
        "repair_targets": repair_targets,
        "thresholds": {
            "min_ssim": args.min_ssim,
            "bad_tile_ssim": args.bad_tile_ssim,
            "max_bad_tile_fraction": args.max_bad_tile_fraction,
            "max_missing_ink_fraction": args.max_missing_ink_fraction,
            "min_text_ink_iou": args.min_text_ink_iou,
            "max_text_offset_px": args.max_text_offset_px,
        },
        "text_source": text_source,
        "problems": problems,
        "passed": not problems,
        "next_actions": [
            "Rebuild only the objects intersecting each repair_targets box, then re-run this gate.",
            "Fix canvas/scale first: while content extent is offset or scaled, every other metric is unreliable.",
            "Treat text_checks with status missing_text or misaligned as hard failures; keep low-confidence solves for manual review.",
        ],
        "claim_boundary": (
            "Pixel and ink metrics compare the render with the source raster. They detect drift, not meaning: "
            "scientific correctness still needs spec-aware human review, and this gate never overrides the spec."
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", required=True, help="source raster (page source.png)")
    parser.add_argument("--rendered", required=True, help="rendered reconstruction (preview or exported PNG)")
    parser.add_argument("--report", required=True)
    parser.add_argument("--layout", default=None, help="solve_text_metrics.py output, for text-level checks")
    parser.add_argument("--manifest", default=None, help="page manifest.json, for text-level checks")
    parser.add_argument("--width", type=int, default=None, help="normalised comparison width (default: reference width)")
    parser.add_argument("--height", type=int, default=None, help="normalised comparison height (default: reference height)")
    parser.add_argument("--tile", type=int, default=64)
    parser.add_argument("--min-ssim", type=float, default=DEFAULT_MIN_SSIM)
    parser.add_argument("--bad-tile-ssim", type=float, default=DEFAULT_BAD_TILE_SSIM)
    parser.add_argument("--max-bad-tile-fraction", type=float, default=DEFAULT_MAX_BAD_TILE_FRACTION)
    parser.add_argument("--max-missing-ink-fraction", type=float, default=0.01, help="tiles allowed to lose source ink")
    parser.add_argument("--min-missing-ink-px", type=int, default=16, help="per-tile missing-ink pixel floor")
    parser.add_argument("--missing-ink-ratio", type=float, default=0.30, help="share of a tile's source ink that must vanish")
    parser.add_argument("--min-reference-ink-px", type=int, default=24, help="ignore tiles with less source ink than this")
    parser.add_argument("--substitution-margin", type=float, default=0.08,
                        help="solve margin at or above which a shape-only text difference is recorded as font substitution")
    parser.add_argument("--fail-on-recorded-differences", action="store_true",
                        help="treat recorded font-substitution differences as gate failures")
    parser.add_argument("--ink-tolerance-px", type=int, default=1, help="registration tolerance for the ink-loss channel")
    parser.add_argument("--min-text-ink-iou", type=float, default=DEFAULT_MIN_TEXT_INK_IOU)
    parser.add_argument("--max-text-offset-px", type=float, default=DEFAULT_MAX_TEXT_OFFSET_PX)
    parser.add_argument("--max-text-size-ratio-delta", type=float, default=0.15)
    parser.add_argument("--max-content-offset-px", type=float, default=4.0)
    parser.add_argument("--max-content-scale-delta", type=float, default=0.02)
    parser.add_argument("--text-margin-px", type=int, default=2)
    parser.add_argument("--align-shift", type=int, default=3)
    parser.add_argument("--max-repair-targets", type=int, default=20)
    parser.add_argument("--advisory", action="store_true", help="always exit 0 (diagnostic use only)")
    args = parser.parse_args()

    report = compare(
        Path(args.reference).expanduser().resolve(),
        Path(args.rendered).expanduser().resolve(),
        args,
    )
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.advisory:
        return 0
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
