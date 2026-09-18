#!/usr/bin/env python3
"""Compare an accepted GPT reference with a rendered editable-slide preview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


def normalized(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def edge_mask(image: Image.Image, threshold: int = 32) -> Image.Image:
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return edges.point(lambda value: 255 if value >= threshold else 0, mode="1")


def flat_pixels(image: Image.Image) -> list[int]:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())  # pragma: no cover - Pillow before 12


def compare(reference: Path, rendered: Path, size: tuple[int, int]) -> dict:
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
        "schema_version": 1,
        "reference": str(reference.resolve()),
        "rendered": str(rendered.resolve()),
        "normalized_size": list(size),
        "metrics": {
            "luminance_mae": round(luma_mae, 4),
            "edge_precision": round(precision, 4),
            "edge_recall": round(recall, 4),
            "edge_f1": round(edge_f1, 4),
            "mean_color_distance": round(mean_color_distance, 4),
        },
        "claim_boundary": "Diagnostic pixel metrics only. Scientific correctness and acceptable vector simplification require spec-aware visual review.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--rendered", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=288)
    args = parser.parse_args()
    report = compare(
        Path(args.reference).expanduser().resolve(),
        Path(args.rendered).expanduser().resolve(),
        (args.width, args.height),
    )
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
