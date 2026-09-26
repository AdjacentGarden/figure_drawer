#!/usr/bin/env python3
"""Append measured, live text from a born-digital paper PDF to a WPS manifest.

The figure's shapes still have to be reconstructed as native objects. This
script imports only PDF text spans; it never embeds a rendered figure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def import_spans(manifest: dict, pdf: Path, page_number: int, crop: tuple[float, ...],
                 scale: float, origin: tuple[float, float], font_scale: float,
                 replace_text: bool) -> dict:
    try:
        import fitz
    except ImportError as exc:
        raise SystemExit("PyMuPDF is required: pip install pymupdf") from exc
    document = fitz.open(pdf)
    page = document[page_number - 1]
    region = fitz.Rect(crop)
    output = dict(manifest)
    output["elements"] = [dict(e) for e in manifest["elements"]
                          if not replace_text or e["kind"] != "text"]
    count = 0
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            rotation = 90 if abs(line["dir"][1]) > 0.5 else 0
            for span in line["spans"]:
                if not span["text"].strip() or not fitz.Rect(span["bbox"]).intersects(region):
                    continue
                x0, y0, x1, y1 = span["bbox"]
                x, y = x0 * scale - origin[0], y0 * scale - origin[1]
                w, h = (x1 - x0) * scale, (y1 - y0) * scale
                # Extra width/height prevents PowerPoint/WPS wrap without
                # changing the measured origin or the editable glyphs.
                pad = max(2.0, float(span["size"]) * scale * 0.32)
                x, y, w, h = x - 1, y - 2, w + pad, h + 4
                font = span["font"]
                count += 1
                output["elements"].append({
                    "kind": "text", "id": f"pdf_text_{count:03d}",
                    "x": round(x, 2), "y": round(y, 2),
                    "w": round(w, 2), "h": round(h, 2),
                    "text": span["text"],
                    "font": "Times New Roman" if "Times" in font else "Calibri",
                    "size": round(float(span["size"]) * font_scale, 2),
                    "bold": "Bold" in font, "italic": "Italic" in font,
                    "color": f"#{int(span['color']):06X}",
                    "align": "left", "valign": "middle", "rotation": rotation,
                    "pdf_span_bbox": [round(v, 3) for v in span["bbox"]],
                })
    output["pdf_text_import"] = {
        "source_pdf": pdf.name, "page": page_number, "crop_pdf_points": list(crop),
        "render_scale": scale, "render_origin": list(origin),
        "font_scale": font_scale, "native_text_spans": count,
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--page", type=int, required=True, help="1-based PDF page number")
    parser.add_argument("--crop", type=float, nargs=4, required=True,
                        metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--scale", type=float, required=True,
                        help="PDF-point to WPS-slide-coordinate scale")
    parser.add_argument("--origin", type=float, nargs=2, required=True,
                        metavar=("X", "Y"), help="Crop origin after scaling")
    parser.add_argument("--font-scale", type=float, required=True,
                        help="PDF font-size to WPS font-size calibration")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace-text", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = import_spans(manifest, args.pdf, args.page, tuple(args.crop),
                          args.scale, tuple(args.origin), args.font_scale,
                          args.replace_text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["pdf_text_import"], indent=2))


if __name__ == "__main__":
    main()
