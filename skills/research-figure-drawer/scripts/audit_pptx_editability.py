#!/usr/bin/env python3
"""Audit a PPTX for object-level editability using its DrawingML geometry.

The audit deliberately treats SVG/EMF/WMF as picture objects: they may scale
cleanly, but their internal labels, connectors, and modules are not native PPT
objects.  This prevents a full-slide image (or a tiled set of images) from
passing as an editable reconstruction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def _in_bounds_rect(node: ET.Element, slide_cx: int, slide_cy: int) -> tuple[int, int, int, int] | None:
    xfrm = node.find(".//a:xfrm", NS)
    if xfrm is None or slide_cx <= 0 or slide_cy <= 0:
        return None
    offset = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if offset is None or ext is None:
        return None
    try:
        x0, y0 = int(offset.attrib["x"]), int(offset.attrib["y"])
        x1 = x0 + int(ext.attrib["cx"])
        y1 = y0 + int(ext.attrib["cy"])
        width = max(0, min(slide_cx, x1) - max(0, x0))
        height = max(0, min(slide_cy, y1) - max(0, y0))
        return (max(0, x0), max(0, y0), width, height) if width and height else None
    except (KeyError, ValueError):
        return None


def _in_bounds_area_fraction(node: ET.Element, slide_cx: int, slide_cy: int) -> float:
    rect = _in_bounds_rect(node, slide_cx, slide_cy)
    return (rect[2] * rect[3]) / (slide_cx * slide_cy) if rect else 0.0


def _union_fraction(rects: list[tuple[int, int, int, int]], slide_cx: int, slide_cy: int) -> float:
    if not rects or slide_cx <= 0 or slide_cy <= 0:
        return 0.0
    xs = sorted({x for left, _, width, _ in rects for x in (left, left + width)})
    area = 0
    for x0, x1 in zip(xs, xs[1:]):
        intervals = sorted(
            (top, top + height) for left, top, width, height in rects
            if left < x1 and left + width > x0
        )
        covered = 0
        if intervals:
            start, end = intervals[0]
            for next_start, next_end in intervals[1:]:
                if next_start > end:
                    covered += end - start
                    start, end = next_start, next_end
                else:
                    end = max(end, next_end)
            covered += end - start
        area += (x1 - x0) * covered
    return min(1.0, area / (slide_cx * slide_cy))


def _visible(node: ET.Element) -> bool:
    properties = node.find(".//p:cNvPr", NS)
    return properties is None or properties.attrib.get("hidden") not in {"1", "true"}


def _has_visible_native_content(node: ET.Element) -> bool:
    if any((item.text or "").strip() for item in node.findall(".//a:t", NS)):
        return True
    properties = node.find("p:spPr", NS)
    if properties is None:
        return True
    no_fill = properties.find("a:noFill", NS) is not None
    line = properties.find("a:ln", NS)
    no_line = line is not None and line.find("a:noFill", NS) is not None
    # An explicitly transparent, borderless geometry is audit padding, not
    # visible editable artwork.  Defaults remain conservative/visible.
    return not (no_fill and no_line)


def audit(path: Path, *, max_picture_fraction: float, max_total_picture_fraction: float,
          min_native_objects: int, min_native_text_runs: int,
          min_native_coverage: float, expected_text: list[str]) -> dict:
    with ZipFile(path) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        size = presentation.find("p:sldSz", NS)
        if size is None:
            raise ValueError("ppt/presentation.xml has no p:sldSz")
        slide_cx, slide_cy = int(size.attrib["cx"]), int(size.attrib["cy"])
        slides = sorted(
            name for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        per_slide = []
        problems: list[str] = []
        for name in slides:
            root = ET.fromstring(archive.read(name))
            pictures = [item for item in root.findall(".//p:pic", NS) if _visible(item)]
            native_shapes = [
                item for item in root.findall(".//p:sp", NS)
                if _visible(item) and _has_visible_native_content(item)
            ]
            native_connectors = [
                item for item in root.findall(".//p:cxnSp", NS)
                if _visible(item) and _has_visible_native_content(item)
            ]
            native_groups = [item for item in root.findall(".//p:grpSp", NS) if _visible(item)]
            graphics = [item for item in root.findall(".//p:graphicFrame", NS) if _visible(item)]
            native_tables = [
                item for item in graphics
                if any("/table" in data.attrib.get("uri", "") for data in item.findall(".//a:graphicData", NS))
            ]
            picture_fractions = [_in_bounds_area_fraction(pic, slide_cx, slide_cy) for pic in pictures]
            picture_rects = [rect for item in pictures if (rect := _in_bounds_rect(item, slide_cx, slide_cy))]
            picture_fraction_union = _union_fraction(picture_rects, slide_cx, slide_cy)
            native_object_count = (
                len(native_shapes) + len(native_connectors) +
                len(native_tables)
            )
            native_items = [*native_shapes, *native_connectors, *native_tables]
            native_rects = [rect for item in native_items if (rect := _in_bounds_rect(item, slide_cx, slide_cy))]
            native_coverage_union = _union_fraction(native_rects, slide_cx, slide_cy)
            native_text_runs = [
                node.text or "" for item in native_shapes
                if _in_bounds_rect(item, slide_cx, slide_cy)
                for node in item.findall(".//a:t", NS) if (node.text or "").strip()
            ]
            slide_problems = []
            if picture_fractions and max(picture_fractions) > max_picture_fraction:
                slide_problems.append("single picture exceeds allowed slide area")
            if picture_fraction_union > max_total_picture_fraction:
                slide_problems.append("pictures collectively cover too much slide area")
            if native_object_count < min_native_objects:
                slide_problems.append("too few native editable objects")
            if len(native_text_runs) < min_native_text_runs:
                slide_problems.append("too few native editable text runs")
            if native_coverage_union < min_native_coverage:
                slide_problems.append("native editable objects cover too little in-bounds slide area")
            # WPS preserves manual line breaks inside a live text box. Match
            # exact labels after whitespace normalization so ``Visual\nEncoder``
            # still satisfies an expected ``Visual Encoder`` label, while the
            # report keeps the original editable text runs.
            combined_text = " ".join(" ".join(value.split()) for value in native_text_runs)
            missing_expected_text = [
                value for value in expected_text
                if " ".join(value.split()) not in combined_text
            ]
            if missing_expected_text:
                slide_problems.append("missing expected native text: " + ", ".join(missing_expected_text))
            if slide_problems:
                problems.extend(f"{name}: {item}" for item in slide_problems)
            per_slide.append({
                "slide": name,
                "picture_count": len(pictures),
                "largest_picture_area_fraction": max(picture_fractions, default=0.0),
                "picture_area_fraction_union": picture_fraction_union,
                "native_shape_count": len(native_shapes),
                "native_connector_count": len(native_connectors),
                "native_group_count": len(native_groups),
                "graphic_frame_count": len(graphics),
                "native_table_count": len(native_tables),
                "native_object_count": native_object_count,
                "native_area_fraction_union": native_coverage_union,
                "native_text_run_count": len(native_text_runs),
                "native_text": native_text_runs,
                "problems": slide_problems,
            })
    return {
        "pptx": str(path.resolve()),
        "pptx_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "policy": {
            "max_picture_fraction": max_picture_fraction,
            "max_total_picture_fraction": max_total_picture_fraction,
            "min_native_objects": min_native_objects,
            "min_native_text_runs": min_native_text_runs,
            "min_native_coverage": min_native_coverage,
            "expected_text": expected_text,
            "vector_pictures_count_as_native": False,
        },
        "slides": per_slide,
        "problems": problems,
        "passed": not problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-picture-fraction", type=float, default=0.45)
    parser.add_argument("--max-total-picture-fraction", type=float, default=0.70)
    parser.add_argument("--min-native-objects", type=int, default=3)
    parser.add_argument("--min-native-text-runs", type=int, default=1)
    parser.add_argument("--min-native-coverage", type=float, default=0.15)
    parser.add_argument("--expected-text", action="append", default=[])
    args = parser.parse_args()
    report = audit(
        args.pptx,
        max_picture_fraction=args.max_picture_fraction,
        max_total_picture_fraction=args.max_total_picture_fraction,
        min_native_objects=args.min_native_objects,
        min_native_text_runs=args.min_native_text_runs,
        min_native_coverage=args.min_native_coverage,
        expected_text=args.expected_text,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
