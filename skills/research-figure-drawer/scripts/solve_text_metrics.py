#!/usr/bin/env python3
"""Solve exact text metrics for raster input and emit manifest-ready text boxes.

Why this exists: the deterministic builder derives a text box's font size from a
per-character width table (0.55 em for ASCII, a 0.9 safety factor, a 1.22 line
height). That is an estimate, and it is also why the hint detector has to inflate
its ink boxes by 0.35/0.30 glyphs to compensate. For screenshot input this tool
replaces the estimate with measurement:

1. binarise the source crop around each detected line into an ink mask,
2. for every candidate font, solve the size from real advance widths, then
   rasterise the string and score it against the source ink by mask IoU,
3. convert the winning ink box into the line box the builder anchors at
   (ink top -> ascender top), which removes the systematic vertical offset,
4. sample the text colour from the darkest ink cluster instead of an average,
5. emit `text_boxes` entries with `font_size_source: "measured"`.

It also emits `preview_font` (an absolute font path). The bundled preview
renderer resolves fonts from a macOS-only list, so on Windows/Linux its text
falls back to a bitmap default unless the manifest supplies a real path.

Dependencies: numpy + Pillow only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from image_metrics import (  # noqa: E402  - sibling module, path set above
    align_ink_iou,
    crop_mask,
    ink_bbox,
    ink_color_hex,
    ink_mask,
    load_rgb,
    to_gray,
)

REFERENCE_SIZE = 100.0  # px size used to measure advance widths at 1:1 scale
DEFAULT_FAMILIES = [
    "arial",
    "calibri",
    "segoeui",
    "tahoma",
    "verdana",
    "georgia",
    "times",
    "cour",
    "consola",
    "msyh",
    "simhei",
    "simsun",
    "deng",
    "dejavu",
    "liberation",
    "noto",
]
CJK_RANGES = ((0x3000, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF))


# --------------------------------------------------------------------------- #
# fonts
# --------------------------------------------------------------------------- #


class FontCandidate:
    __slots__ = ("family", "style", "path", "bold", "italic")

    def __init__(self, family: str, style: str, path: str) -> None:
        self.family = family
        self.style = style
        self.path = path
        lowered = style.lower()
        self.bold = "bold" in lowered
        self.italic = "italic" in lowered or "oblique" in lowered

    def as_dict(self) -> dict:
        return {"family": self.family, "style": self.style, "path": self.path}


def discover_fonts(font_dirs: list[Path], families: list[str] | None, include_all: bool) -> list[FontCandidate]:
    wanted = None if include_all else [name.lower() for name in (families or DEFAULT_FAMILIES)]
    candidates: list[FontCandidate] = []
    seen: set[str] = set()
    for directory in font_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc"} or path.name.lower() in seen:
                continue
            stem = path.stem.lower()
            if wanted is not None and not any(name in stem for name in wanted):
                continue
            seen.add(path.name.lower())
            try:
                family, style = ImageFont.truetype(str(path), 20).getname()
            except Exception:
                continue
            candidates.append(FontCandidate(family or path.stem, style or "Regular", str(path)))
    return candidates


def contains_cjk(text: str) -> bool:
    return any(any(low <= ord(char) <= high for low, high in CJK_RANGES) for char in text)


# --------------------------------------------------------------------------- #
# rasterising candidates
# --------------------------------------------------------------------------- #


def rasterise_tight(text: str, font: ImageFont.FreeTypeFont, pad: int = 2) -> np.ndarray:
    """Tight boolean ink mask of `text` drawn with `font`."""
    from PIL import Image, ImageDraw

    bbox = font.getbbox(text)
    width = max(1, bbox[2] - bbox[0]) + 2 * pad
    height = max(1, bbox[3] - bbox[1]) + 2 * pad
    canvas = Image.new("L", (width, height), 0)
    ImageDraw.Draw(canvas).text((pad - bbox[0], pad - bbox[1]), text, fill=255, font=font)
    mask = np.asarray(canvas) > 127
    tight = ink_bbox(mask)
    return mask if tight is None else crop_mask(mask, tight)


def size_candidates(estimate: float, extra: list[float], minimum: float, maximum: float) -> list[int]:
    values = {int(round(max(minimum, min(maximum, estimate * factor)))) for factor in np.linspace(0.88, 1.14, 14)}
    for value in extra:
        if value:
            values.add(int(round(max(minimum, min(maximum, value)))))
    return sorted(value for value in values if value >= 1)


# --------------------------------------------------------------------------- #
# solving
# --------------------------------------------------------------------------- #


def solve_item(rgb: np.ndarray, gray: np.ndarray, item: dict, fonts: list[FontCandidate], args: argparse.Namespace) -> dict:
    text = str(item.get("text") or "").strip()
    hint_box = [int(round(float(value))) for value in item.get("box_px", [0, 0, 0, 0])]
    height, width = gray.shape
    margin = int(args.margin_px)
    left = max(0, hint_box[0] - margin)
    top = max(0, hint_box[1] - margin)
    right = min(width, hint_box[0] + hint_box[2] + margin)
    bottom = min(height, hint_box[1] + hint_box[3] + margin)
    record: dict = {
        "index": item.get("index"),
        "text": text,
        "hint_box_px": hint_box,
        "glyph_height_px": item.get("glyph_height_px"),
        "size_group": item.get("size_group"),
        "line_count": item.get("line_count"),
        "warnings": [],
    }
    if not text:
        record.update({"mode": "hint-only", "reason": "no recognised text in hints; box and size were not solvable"})
        record["warnings"].append("no_text_in_hints")
        return record
    if right <= left or bottom <= top:
        record.update({"mode": "failed", "reason": "hint box does not overlap the image"})
        record["warnings"].append("box_outside_image")
        return record

    region_gray = gray[top:bottom, left:right]
    region_rgb = rgb[top:bottom, left:right]
    region_mask, threshold, inverted = ink_mask(region_gray)
    box = ink_bbox(region_mask)
    if box is None:
        record.update({"mode": "failed", "reason": "no ink detected inside the hint box"})
        record["warnings"].append("no_ink_in_box")
        return record

    ink_left = left + box[0]
    ink_top = top + box[1]
    ink_width = box[2]
    ink_height = box[3]
    target = crop_mask(region_mask, box)
    record["ink_box_px"] = [ink_left, ink_top, ink_width, ink_height]
    record["threshold"] = round(threshold, 1)
    record["inverted"] = inverted

    if (item.get("line_count") or 1) > 1:
        record["warnings"].append("hint_reports_multiple_lines")

    hint_pt = item.get("font_pt_if_cjk") if contains_cjk(text) else item.get("font_pt_if_latin")
    hint_pt = hint_pt or item.get("font_pt") or item.get("font_size_pt")
    hint_sizes = [float(hint_pt) / args.pt_per_px] if hint_pt and args.pt_per_px else []
    record["font_pt_hint"] = float(hint_pt) if hint_pt else None
    best: dict | None = None
    for candidate in fonts:
        try:
            reference_font = ImageFont.truetype(candidate.path, int(REFERENCE_SIZE))
        except Exception:
            continue
        try:
            advance = float(reference_font.getlength(text))
        except Exception:
            continue
        if advance <= 0:
            continue
        estimate = ink_width / advance * REFERENCE_SIZE
        for size_px in size_candidates(estimate, hint_sizes, args.min_px, args.max_px):
            try:
                font = ImageFont.truetype(candidate.path, size_px)
            except Exception:
                continue
            try:
                candidate_mask = rasterise_tight(text, font)
            except Exception:
                continue
            candidate_box = ink_bbox(candidate_mask)
            if candidate_box is None:
                continue
            iou, _shift = align_ink_iou(target, candidate_mask, max_shift=args.align_shift)
            height_ratio = candidate_box[3] / ink_height if ink_height else 1.0
            # IoU decides; the height ratio only breaks near-ties.
            score = iou - abs(height_ratio - 1.0) * 0.02
            if best is None or score > best["score"]:
                best = {
                    "score": score,
                    "iou": iou,
                    "candidate": candidate,
                    "size_px": float(size_px),
                    "candidate_width": candidate_box[2],
                    "candidate_height": candidate_box[3],
                }
    if best is None:
        record.update({"mode": "failed", "reason": "no candidate font produced a comparable raster"})
        record["warnings"].append("no_font_candidate")
        return record

    # Sub-pixel refinement: scalable outlines make ink width proportional to size.
    ratio = ink_width / best["candidate_width"] if best["candidate_width"] else 1.0
    size_px = max(float(args.min_px), min(float(args.max_px), best["size_px"] * ratio))
    font = ImageFont.truetype(best["candidate"].path, int(round(best["size_px"])))
    offset_x, offset_y, extent_x, _extent_y = font.getbbox(text)
    ascent, descent = font.getmetrics()
    scale = size_px / best["size_px"] if best["size_px"] else 1.0
    offset_x *= scale
    offset_y *= scale
    ascent *= scale
    descent *= scale

    pad = float(args.box_pad_px)
    # The builder anchors the first line's ascender at the box top with zero
    # insets, so shifting by the ink offset lands the glyphs on the source ink.
    box_left = ink_left - offset_x - pad
    box_top = ink_top - offset_y - pad
    box_width = max(1.0, (ink_width if ink_width > extent_x * scale else extent_x * scale) + 2 * pad)
    box_height = max(1.0, ascent + descent + 2 * pad)

    iou = best["iou"]
    confidence = "high" if iou >= args.high_iou else ("medium" if iou >= args.medium_iou else "low")
    if confidence == "low":
        record["warnings"].append("low_ink_similarity")
    if contains_cjk(text) and not any(ord(char) > 0x2E80 for char in best["candidate"].family):
        record["warnings"].append("cjk_text_with_latin_font")

    scale_inches_per_px = args.pt_per_px / 72.0
    font_size_pt = size_px * args.pt_per_px
    record.update(
        {
            "mode": "solved",
            "font": best["candidate"].family,
            "font_style": best["candidate"].style,
            "font_file": best["candidate"].path,
            "bold": best["candidate"].bold,
            "italic": best["candidate"].italic,
            "font_size_px": round(size_px, 2),
            "font_size_pt": round(font_size_pt, 2),
            # `box` is region-local, so the colour must be sampled from the same
            # crop; sampling the full image here yields background colour.
            "color": ink_color_hex(region_rgb, region_mask, box),
            "confidence": confidence,
            "ink_iou": round(iou, 4),
            "box_px": [round(box_left, 2), round(box_top, 2), round(box_width, 2), round(box_height, 2)],
            "line_box_px": {"ascent": round(ascent, 2), "descent": round(descent, 2)},
            "px_per_inch": round(1.0 / scale_inches_per_px, 4) if scale_inches_per_px else None,
        }
    )
    return record


def manifest_text_box(record: dict, args: argparse.Namespace) -> dict | None:
    """Convert a solved record into a manifest `text_boxes` entry."""
    if record.get("mode") != "solved":
        return None
    trusted = record["confidence"] in {"high", "medium"} and record["ink_iou"] >= args.trust_iou
    item = {
        "text": record["text"],
        "box_px": record["box_px"],
        "font": record["font"],
        "font_size": record["font_size_pt"],
        "font_size_source": "measured",
        "color": record["color"],
        "align": "left",
        "valign": "top",
        "wrap": "none",
        # The box and the size were solved from real glyph metrics and verified
        # by ink IoU, so the builder's width-table clamp can only degrade them.
        # Below the trust threshold the guard stays on.
        "fit_text": not trusted,
        "preview_font": record["font_file"] if args.emit_preview_font else None,
        "_solve": {
            "ink_iou": record["ink_iou"],
            "confidence": record["confidence"],
            "font_style": record["font_style"],
            "ink_box_px": record["ink_box_px"],
        },
    }
    if record.get("bold"):
        item["bold"] = True
    if record.get("italic"):
        item["italic"] = True
    return {key: value for key, value in item.items() if value is not None}


# --------------------------------------------------------------------------- #
# input handling
# --------------------------------------------------------------------------- #


def load_items(path: Path) -> list[dict]:
    """Accept editppt `text_hints.json`, a list, or {"lines"|"items": [...]}."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("lines") or payload.get("items") or payload.get("text_lines") or []
    else:
        raw = []
    items: list[dict] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        box = entry.get("box_px") or entry.get("box") or entry.get("bbox")
        if not box or len(box) != 4:
            continue
        text = entry.get("text") or entry.get("ocr_text") or entry.get("content") or ""
        record = dict(entry)
        record["box_px"] = [float(value) for value in box]
        record["text"] = str(text)
        record["index"] = entry.get("index", index)
        items.append(record)
    return items


def content_box_for(source_width: float, source_height: float, slide_width: float, slide_height: float) -> dict:
    """Mirror of the builder's aspect-fit content box."""
    source_aspect = source_width / source_height
    slide_aspect = slide_width / slide_height
    if source_aspect >= slide_aspect:
        width = slide_width
        height = width / source_aspect
        left = 0.0
        top = (slide_height - height) / 2
    else:
        height = slide_height
        width = height * source_aspect
        left = (slide_width - width) / 2
        top = 0.0
    return {"left": left, "top": top, "width": width, "height": height}


def parse_size(value: str) -> tuple[float, float]:
    left, _, right = value.lower().partition("x")
    return float(left), float(right)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", required=True, help="source.png (page-normalised raster)")
    parser.add_argument("--hints", required=True, help="editppt text_hints.json, or a list of {text, box_px}")
    parser.add_argument("--out", required=True)
    parser.add_argument("--font-dir", action="append", default=[], help="repeatable; defaults to the OS font directory")
    parser.add_argument("--families", default=None, help="comma-separated family substrings to consider")
    parser.add_argument("--all-fonts", action="store_true", help="consider every font file found")
    parser.add_argument("--slide", default="13.333x7.5", help="slide size in inches (WxH)")
    parser.add_argument("--content-box", default=None, help="explicit left,top,width,height in inches")
    parser.add_argument("--min-px", type=float, default=6.0)
    parser.add_argument("--max-px", type=float, default=200.0)
    parser.add_argument("--margin-px", type=int, default=4, help="search margin around each hint box")
    parser.add_argument("--box-pad-px", type=float, default=1.0, help="padding added to the solved box")
    parser.add_argument("--align-shift", type=int, default=2, help="pixels of shift tolerance in the ink comparison")
    parser.add_argument("--high-iou", type=float, default=0.75)
    parser.add_argument("--medium-iou", type=float, default=0.55)
    parser.add_argument("--trust-iou", type=float, default=0.70, help="IoU at or above which fit_text is disabled")
    parser.add_argument("--emit-preview-font", action="store_true", default=True)
    parser.add_argument("--no-preview-font", dest="emit_preview_font", action="store_false")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    hints_path = Path(args.hints).expanduser().resolve()
    rgb = load_rgb(image_path)
    gray = to_gray(rgb)
    source_height, source_width = gray.shape

    slide_width, slide_height = parse_size(args.slide)
    if args.content_box:
        parts = [float(value) for value in args.content_box.split(",")]
        if len(parts) != 4:
            raise SystemExit("--content-box needs left,top,width,height")
        content_box = {"left": parts[0], "top": parts[1], "width": parts[2], "height": parts[3]}
    else:
        content_box = content_box_for(source_width, source_height, slide_width, slide_height)
    inches_per_px = content_box["width"] / float(source_width)
    pt_per_px = inches_per_px * 72.0
    args.pt_per_px = pt_per_px

    if args.font_dir:
        font_dirs = [Path(value).expanduser() for value in args.font_dir]
    else:
        candidates: list[Path] = []
        if sys.platform.startswith("win"):
            candidates.append(Path(r"C:\Windows\Fonts"))
        candidates.extend([Path("/usr/share/fonts"), Path("/Library/Fonts"), Path("/System/Library/Fonts")])
        font_dirs = candidates
    families = [value.strip() for value in args.families.split(",")] if args.families else None
    fonts = discover_fonts(font_dirs, families, args.all_fonts)
    if not fonts:
        raise SystemExit(f"no candidate fonts found in: {', '.join(str(path) for path in font_dirs)}")

    items = load_items(hints_path)
    solved = [solve_item(rgb, gray, item, fonts, args) for item in items]
    text_boxes = [box for box in (manifest_text_box(record, args) for record in solved) if box]

    confidences = [record.get("confidence") for record in solved if record.get("mode") == "solved"]
    ious = [record["ink_iou"] for record in solved if record.get("mode") == "solved"]
    report = {
        "schema_version": 1,
        "source": {"path": str(image_path), "width_px": source_width, "height_px": source_height},
        "slide": {"width": slide_width, "height": slide_height},
        "content_box": {key: round(value, 5) for key, value in content_box.items()},
        "pt_per_px": round(pt_per_px, 5),
        "font_search": {
            "directories": [str(path) for path in font_dirs],
            "candidates": len(fonts),
            "families": sorted({font.family for font in fonts}),
        },
        "summary": {
            "items": len(items),
            "solved": len(confidences),
            "text_boxes": len(text_boxes),
            "high": confidences.count("high"),
            "medium": confidences.count("medium"),
            "low": confidences.count("low"),
            "mean_ink_iou": round(float(np.mean(ious)), 4) if ious else None,
        },
        "items": solved,
        "text_boxes": text_boxes,
        "claim_boundary": (
            "Metrics are solved against the raster with real font metrics and verified by ink IoU. "
            "A low-confidence item means the raster could not be matched reliably: review it by hand "
            "and leave fit_text enabled rather than trusting the solved size."
        ),
    }
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(output), **report["summary"], "pt_per_px": report["pt_per_px"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
