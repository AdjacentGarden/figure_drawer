#!/usr/bin/env python3
"""Audit font, vector, and effective-raster quality in an editable figure manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


VECTOR_SUFFIXES = {".svg", ".emf", ".wmf"}


def resolved_policy(manifest: dict, args: argparse.Namespace) -> dict:
    policy = dict(manifest.get("quality_policy") or {})
    defaults = {
        "min_font_pt": 10.0,
        "min_micro_font_pt": 8.0,
        "max_micro_text_fraction": 0.25,
        "min_raster_dpi": 300.0,
        "prefer_vector_formulas": True,
    }
    for key, value in defaults.items():
        policy.setdefault(key, value)
    for key in ("min_font_pt", "min_micro_font_pt", "max_micro_text_fraction", "min_raster_dpi"):
        value = getattr(args, key, None)
        if value is not None:
            policy[key] = value
    return policy


def asset_path(page_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else page_dir / path


def audit(manifest_path: Path, args: argparse.Namespace) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    page_dir = manifest_path.parent
    policy = resolved_policy(manifest, args)
    violations: list[dict] = []
    warnings: list[dict] = []

    text_boxes = manifest.get("text_boxes", [])
    font_sizes = []
    body_font_sizes = []
    micro_font_sizes = []
    micro_count = 0
    for index, item in enumerate(text_boxes):
        size = float(item.get("font_size", 0) or 0)
        role = str(item.get("text_role", "body")).strip().lower()
        is_micro = role == "micro"
        micro_count += int(is_micro)
        (micro_font_sizes if is_micro else body_font_sizes).append(size)
        threshold = float(policy["min_micro_font_pt"] if is_micro else policy["min_font_pt"])
        font_sizes.append(size)
        if size < threshold:
            violations.append({
                "kind": "font-size",
                "index": index,
                "text": str(item.get("text", ""))[:120],
                "role": role,
                "font_size": size,
                "minimum": threshold,
            })
    micro_fraction = micro_count / len(text_boxes) if text_boxes else 0.0
    if micro_fraction > float(policy["max_micro_text_fraction"]):
        violations.append({
            "kind": "micro-text-fraction",
            "actual": round(micro_fraction, 4),
            "maximum": float(policy["max_micro_text_fraction"]),
        })

    source = manifest.get("source", {})
    slide = manifest.get("slide", {})
    source_width = float(source.get("width_px", 0) or 0)
    source_height = float(source.get("height_px", 0) or 0)
    slide_width = float(slide.get("width", 0) or 0)
    slide_height = float(slide.get("height", 0) or 0)
    raster_assets = []
    vector_assets = []
    images_by_id = {str(item.get("id", "")): item for item in manifest.get("images", [])}
    images_by_path = {str(item.get("path", "")): item for item in manifest.get("images", [])}

    for index, item in enumerate(manifest.get("images", [])):
        relative = str(item.get("path", ""))
        path = asset_path(page_dir, relative)
        if not path.is_file():
            violations.append({"kind": "missing-asset", "index": index, "path": relative})
            continue
        suffix = path.suffix.lower()
        if suffix in VECTOR_SUFFIXES:
            vector_assets.append(relative)
            continue
        box = item.get("box_px")
        if not box or len(box) != 4 or not source_width or not source_height or not slide_width or not slide_height:
            warnings.append({"kind": "dpi-unavailable", "index": index, "path": relative})
            continue
        with Image.open(path) as image:
            pixel_width, pixel_height = image.size
        placed_width_in = float(box[2]) / source_width * slide_width
        placed_height_in = float(box[3]) / source_height * slide_height
        dpi_x = pixel_width / placed_width_in if placed_width_in else 0.0
        dpi_y = pixel_height / placed_height_in if placed_height_in else 0.0
        effective_dpi = min(dpi_x, dpi_y)
        raster_assets.append({
            "path": relative,
            "pixel_size": [pixel_width, pixel_height],
            "effective_dpi": round(effective_dpi, 1),
        })
        if effective_dpi < float(policy["min_raster_dpi"]):
            violations.append({
                "kind": "raster-dpi",
                "index": index,
                "path": relative,
                "effective_dpi": round(effective_dpi, 1),
                "minimum": float(policy["min_raster_dpi"]),
            })

    formula_vectors = 0
    for index, item in enumerate(manifest.get("formula_inventory", [])):
        if not isinstance(item, dict):
            violations.append({"kind": "formula-inventory-not-object", "index": index, "value": str(item)[:120]})
            continue
        relative = str(item.get("image", item.get("path", "")))
        if Path(relative).suffix.lower() in VECTOR_SUFFIXES:
            formula_vectors += 1
        elif policy.get("prefer_vector_formulas", True):
            violations.append({"kind": "formula-not-vector", "index": index, "path": relative})

    for index, item in enumerate(manifest.get("visual_inventory", [])):
        if not isinstance(item, dict):
            # The schema allows plain strings in some inventories, so record the
            # deviation instead of failing with an AttributeError.
            violations.append({"kind": "visual-inventory-not-object", "index": index, "value": str(item)[:120]})
            continue
        if item.get("vector_required") is not True:
            continue
        relative = str(item.get("path", ""))
        image = images_by_path.get(relative) or images_by_id.get(str(item.get("id", ""))) or {}
        actual = relative or str(image.get("path", ""))
        if Path(actual).suffix.lower() not in VECTOR_SUFFIXES and item.get("role") != "structure":
            violations.append({
                "kind": "vector-required",
                "index": index,
                "id": item.get("id"),
                "path": actual,
            })

    report = {
        "schema_version": 1,
        "passed": not violations,
        "manifest": str(manifest_path.resolve()),
        "policy": policy,
        "summary": {
            "text_boxes": len(text_boxes),
            "minimum_font_pt": min(font_sizes) if font_sizes else None,
            "minimum_body_font_pt": min(body_font_sizes) if body_font_sizes else None,
            "minimum_micro_font_pt": min(micro_font_sizes) if micro_font_sizes else None,
            "micro_text_fraction": round(micro_fraction, 4),
            "raster_assets": len(raster_assets),
            "vector_assets": len(vector_assets),
            "formula_vectors": formula_vectors,
        },
        "raster_assets": raster_assets,
        "vector_assets": vector_assets,
        "violations": violations,
        "warnings": warnings,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--min-font-pt", type=float)
    parser.add_argument("--min-micro-font-pt", type=float)
    parser.add_argument("--max-micro-text-fraction", type=float)
    parser.add_argument("--min-raster-dpi", type=float)
    args = parser.parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    report = audit(manifest_path, args)
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
