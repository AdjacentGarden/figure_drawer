#!/usr/bin/env python3
"""Audit semantic figure layout for collisions, connector crossings, and canonical geometry."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def rect(item):
    box = item.get("box_px")
    if not box or len(box) != 4:
        return None
    x, y, width, height = [float(value) for value in box]
    return x, y, x + width, y + height


def overlap_area(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def inset(box, amount):
    return box[0] + amount, box[1] + amount, box[2] - amount, box[3] - amount


def point_in_rect(point, box):
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def segment_intersects_rect(start, end, box):
    if box[0] >= box[2] or box[1] >= box[3]:
        return False
    if point_in_rect(start, box) or point_in_rect(end, box):
        return True
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    p = (-dx, dx, -dy, dy)
    q = (x1 - box[0], box[2] - x1, y1 - box[1], box[3] - y1)
    low, high = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-9:
            if qi < 0:
                return False
            continue
        ratio = qi / pi
        if pi < 0:
            low = max(low, ratio)
        else:
            high = min(high, ratio)
        if low > high:
            return False
    return True


def bezier_point(points, t):
    working = [tuple(point) for point in points]
    while len(working) > 1:
        working = [
            ((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1])
            for a, b in zip(working, working[1:])
        ]
    return working[0]


def path_segments(shape):
    if shape.get("type") == "line" and len(shape.get("points_px") or []) == 4:
        x1, y1, x2, y2 = [float(value) for value in shape["points_px"]]
        return [((x1, y1), (x2, y2))]
    commands = shape.get("path_px") or []
    current = None
    start = None
    segments = []
    for command in commands:
        op = command.get("op")
        points = [tuple(map(float, point)) for point in command.get("points") or []]
        if op == "moveTo" and points:
            current = start = points[0]
        elif op == "lnTo" and current is not None and points:
            segments.append((current, points[0]))
            current = points[0]
        elif op in {"quadBezTo", "cubicBezTo"} and current is not None and points:
            control = [current, *points]
            sampled = [bezier_point(control, step / 12.0) for step in range(13)]
            segments.extend(zip(sampled, sampled[1:]))
            current = points[-1]
        elif op == "close" and current is not None and start is not None:
            segments.append((current, start))
            current = start
    return list(segments)


def is_parallel(a, b, tolerance=1e-6):
    return abs(a[0] * b[1] - a[1] * b[0]) <= tolerance * max(1.0, math.hypot(*a) * math.hypot(*b))


def valid_parallelogram(points):
    if len(points) != 4:
        return False
    vectors = [
        (points[(index + 1) % 4][0] - points[index][0], points[(index + 1) % 4][1] - points[index][1])
        for index in range(4)
    ]
    return is_parallel(vectors[0], vectors[2]) and is_parallel(vectors[1], vectors[3])


def audit(manifest):
    violations = []
    warnings = []
    width = float(manifest.get("source", {}).get("width_px", 0) or 0)
    height = float(manifest.get("source", {}).get("height_px", 0) or 0)
    text_items = []
    for index, item in enumerate(manifest.get("text_boxes", [])):
        box = rect(item)
        if box:
            text_items.append((f"text:{item.get('id') or index}", item, box))
    for index, item in enumerate(manifest.get("formula_inventory", [])):
        box = rect(item)
        if box:
            text_items.append((f"formula:{item.get('id') or index}", item, box))

    for name, item, box in text_items:
        if width and height and (box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height):
            violations.append({"kind": "out-of-bounds", "object": name, "box_px": list(item["box_px"])})

    for index, (name_a, item_a, box_a) in enumerate(text_items):
        if item_a.get("allow_overlap") is True:
            continue
        for name_b, item_b, box_b in text_items[index + 1 :]:
            if item_b.get("allow_overlap") is True:
                continue
            area = overlap_area(box_a, box_b)
            if area > 1.0:
                violations.append({
                    "kind": "content-overlap",
                    "objects": [name_a, name_b],
                    "overlap_area_px2": round(area, 2),
                })

    inset_px = float((manifest.get("quality_policy") or {}).get("connector_text_inset_px", 2.0))
    for shape_index, shape in enumerate(manifest.get("shapes", [])):
        if shape.get("allow_text_crossing") is True:
            continue
        segments = path_segments(shape)
        if not segments:
            continue
        connector = shape.get("semantic_line_id") or f"shape:{shape_index}"
        for name, item, box in text_items:
            if item.get("allow_line_crossing") is True:
                continue
            inner = inset(box, inset_px)
            if any(segment_intersects_rect(start, end, inner) for start, end in segments):
                violations.append({"kind": "connector-crosses-content", "connector": connector, "object": name})

    cube_faces = defaultdict(dict)
    for index, shape in enumerate(manifest.get("shapes", [])):
        if shape.get("geometry_role") != "isometric-cube-face":
            continue
        cube_faces[str(shape.get("cube_id") or "cube")][str(shape.get("face") or index)] = shape
    for cube_id, faces in cube_faces.items():
        if set(faces) != {"top", "left", "right"}:
            violations.append({"kind": "cube-face-set", "cube_id": cube_id, "faces": sorted(faces)})
            continue
        point_sets = []
        for face_name, shape in faces.items():
            points = [tuple(map(float, point)) for point in shape.get("polygon_px") or []]
            point_sets.append(set(points))
            if not valid_parallelogram(points):
                violations.append({"kind": "cube-face-not-parallelogram", "cube_id": cube_id, "face": face_name})
        for first, second, label in ((0, 1, "top-left"), (0, 2, "top-right"), (1, 2, "left-right")):
            if len(point_sets[first] & point_sets[second]) != 2:
                violations.append({"kind": "cube-seam-mismatch", "cube_id": cube_id, "seam": label})
        if len(set.intersection(*point_sets)) != 1:
            violations.append({"kind": "cube-center-mismatch", "cube_id": cube_id})

    return {
        "schema_version": 1,
        "passed": not violations,
        "summary": {
            "content_boxes": len(text_items),
            "connectors": sum(bool(path_segments(shape)) for shape in manifest.get("shapes", [])),
            "canonical_cubes": len(cube_faces),
        },
        "violations": violations,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    report = audit(json.loads(manifest_path.read_text(encoding="utf-8")))
    report["manifest"] = str(manifest_path)
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
