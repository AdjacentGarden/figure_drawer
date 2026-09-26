#!/usr/bin/env python3
"""Build a paper mechanism diagram from native WPS Presentation objects.

This runs on Windows with pywin32 and WPS Presentation installed.  A manifest
is deliberately simple so figure-specific geometry can be revised without
modifying COM code.  Raster assets are permitted only as isolated photograph
or icon objects; the information structure stays native/editable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time


def validate_manifest(manifest: dict, assets_dir: Path) -> dict:
    canvas = manifest["canvas"]
    width, height = float(canvas["width"]), float(canvas["height"])
    if width <= 0 or height <= 0:
        raise ValueError("Canvas width and height must be positive")
    if not manifest.get("figure_id") or not isinstance(manifest.get("elements"), list):
        raise ValueError("Manifest needs figure_id and elements")
    picture_count = 0
    text_count = 0
    for index, spec in enumerate(manifest["elements"], 1):
        kind = spec.get("kind")
        if kind not in {"shape", "path", "text", "image"}:
            raise ValueError(f"Element {index}: unsupported kind {kind!r}")
        if kind == "image":
            picture_count += 1
            if not (assets_dir / spec["file"]).is_file():
                raise FileNotFoundError(assets_dir / spec["file"])
            if float(spec["w"]) * float(spec["h"]) >= 0.70 * width * height:
                raise ValueError(f"Element {index}: page-sized picture is not an editable reconstruction")
        if kind == "text":
            text_count += 1
            if not spec.get("text"):
                raise ValueError(f"Element {index}: empty live text")
        if kind in {"shape", "text", "image"}:
            if float(spec["w"]) <= 0 or float(spec["h"]) <= 0:
                raise ValueError(f"Element {index}: non-positive object size")
            if float(spec["x"]) < -1 or float(spec["y"]) < -1:
                raise ValueError(f"Element {index}: object outside canvas")
            if float(spec["x"]) + float(spec["w"]) > width + 1 or float(spec["y"]) + float(spec["h"]) > height + 1:
                raise ValueError(f"Element {index}: object outside canvas")
        if kind == "path":
            if "bezier" in spec:
                if len(spec["bezier"]) != 4:
                    raise ValueError(f"Element {index}: cubic bezier needs four points")
            elif len(spec.get("points", [])) < 2:
                raise ValueError(f"Element {index}: path needs at least two points")
    return {"elements": len(manifest["elements"]), "pictures": picture_count, "live_text": text_count}


def rgb(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16) + (int(h[2:4], 16) << 8) + (int(h[4:6], 16) << 16)


def apply_line(item, spec: dict) -> None:
    line = item.Line
    if not spec.get("stroke"):
        line.Visible = 0
        return
    line.Visible = -1
    line.ForeColor.RGB = rgb(spec["stroke"])
    line.Weight = float(spec.get("stroke_width", 1.0))
    if spec.get("dash") == "dash":
        line.DashStyle = 4
    elif spec.get("dash") == "dot":
        line.DashStyle = 2
    if spec.get("arrow"):
        line.EndArrowheadStyle = 3
        line.EndArrowheadLength = 1
        line.EndArrowheadWidth = 1


def add_text(shapes, spec: dict):
    if spec.get("rotation"):
        # Manifest coordinates are the desired *visible* rotated bbox.  WPS
        # wraps against the unrotated textbox width, so swap width/height and
        # preserve its centre before applying Shape.Rotation.
        cx = float(spec["x"]) + float(spec["w"]) / 2
        cy = float(spec["y"]) + float(spec["h"]) / 2
        tw, th = float(spec["h"]), float(spec["w"])
        left, top = cx - tw / 2, cy - th / 2
    else:
        left, top, tw, th = spec["x"], spec["y"], spec["w"], spec["h"]
    item = shapes.AddTextbox(1, left, top, tw, th)
    item.Line.Visible = 0
    item.Fill.Visible = 0
    frame = item.TextFrame
    frame.MarginLeft = frame.MarginRight = frame.MarginTop = frame.MarginBottom = 0
    frame.VerticalAnchor = {"top": 1, "middle": 3, "bottom": 4}.get(spec.get("valign", "middle"), 3)
    rng = frame.TextRange
    rng.Text = spec["text"]
    rng.Font.Name = spec.get("font", "Arial")
    rng.Font.Size = float(spec.get("size", 12))
    rng.Font.Bold = -1 if spec.get("bold") else 0
    rng.Font.Italic = -1 if spec.get("italic") else 0
    rng.Font.Color.RGB = rgb(spec.get("color", "#111111"))
    rng.ParagraphFormat.Alignment = {"left": 1, "center": 2, "right": 3}.get(spec.get("align", "center"), 2)
    if spec.get("rotation"):
        item.Rotation = float(spec["rotation"])
    return item


def add_shape(shapes, spec: dict):
    kinds = {"rect": 1, "roundrect": 5, "ellipse": 9, "triangle": 7}
    item = shapes.AddShape(kinds[spec.get("shape", "rect")], spec["x"], spec["y"], spec["w"], spec["h"])
    if spec.get("fill"):
        item.Fill.Visible = -1
        item.Fill.Solid()
        item.Fill.ForeColor.RGB = rgb(spec["fill"])
        item.Fill.Transparency = float(spec.get("transparency", 0))
    else:
        item.Fill.Visible = 0
    apply_line(item, spec)
    return item


def add_path(shapes, spec: dict):
    if "bezier" in spec:
        # WPS serializes Freeform cubic geometry but its own PNG exporter omits
        # the stroke for some curves. Approximate as short native line segments
        # so the PPTX and the WPS reopen render are both reliably visible.
        p0, p1, p2, p3 = spec["bezier"]
        def point(t):
            u = 1 - t
            return tuple(u**3 * p0[k] + 3*u*u*t * p1[k] +
                         3*u*t*t * p2[k] + t**3 * p3[k] for k in (0, 1))
        points = [point(i / 12) for i in range(13)]
    else:
        points = spec["points"]
    last = None
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        last = shapes.AddLine(x1, y1, x2, y2)
        segment = dict(spec)
        segment["arrow"] = bool(spec.get("arrow") and i == len(points) - 2)
        apply_line(last, segment)
    return last


def add_photo(shapes, spec: dict, assets_dir: Path):
    source = (assets_dir / spec["file"]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    return shapes.AddPicture(str(source), False, True, spec["x"], spec["y"], spec["w"], spec["h"])


def build(manifest_path: Path, output: Path, assets_dir: Path) -> None:
    import pythoncom
    import win32com.client

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory = validate_manifest(manifest, assets_dir)
    pythoncom.CoInitialize()
    app = None
    pres = None
    try:
        app = win32com.client.DispatchEx("KWPP.Application")
        app.Visible = True
        pres = app.Presentations.Add()
        pres.PageSetup.SlideWidth = float(manifest["canvas"]["width"])
        pres.PageSetup.SlideHeight = float(manifest["canvas"]["height"])
        slide = pres.Slides.Add(1, 12)
        shapes = slide.Shapes
        counts = {"shape": 0, "path": 0, "text": 0, "image": 0}
        for index, spec in enumerate(manifest["elements"], 1):
            kind = spec["kind"]
            if kind == "shape":
                item = add_shape(shapes, spec)
            elif kind == "path":
                item = add_path(shapes, spec)
            elif kind == "text":
                item = add_text(shapes, spec)
            elif kind == "image":
                item = add_photo(shapes, spec, assets_dir)
            else:
                raise ValueError(f"Unsupported object type: {kind}")
            counts[kind] += 1
            if item is not None:
                item.Name = str(spec.get("id") or f"{manifest['figure_id']}_{index:03d}")[:60]
        output.parent.mkdir(parents=True, exist_ok=True)
        pres.SaveAs(str(output), 24)
        report = {
            "figure_id": manifest["figure_id"],
            "wps_version": str(app.Version),
            "slide_size_points": [float(pres.PageSetup.SlideWidth), float(pres.PageSetup.SlideHeight)],
            "shape_count": int(shapes.Count),
            "semantic_object_counts": counts,
            "validated_manifest_inventory": inventory,
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "pptx_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        }
        output.with_suffix(".builder.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        if pres is not None:
            try:
                pres.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--assets-dir", type=Path, default=Path("assets"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        print(json.dumps(validate_manifest(manifest, args.assets_dir.resolve()), indent=2))
    else:
        if args.output.exists():
            raise SystemExit(f"Refusing to overwrite existing PPTX: {args.output}")
        for attempt in range(1, 4):
            try:
                build(args.manifest.resolve(), args.output.resolve(), args.assets_dir.resolve())
                break
            except Exception:
                if attempt == 3 or args.output.exists():
                    raise
                time.sleep(2)
