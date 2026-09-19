#!/usr/bin/env python3
"""Insert editable Word OfficeMath equations into a PowerPoint deck as OLE objects."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path


PP_PASTE_OLE_OBJECT = 10
MSO_FALSE = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input PPTX path.")
    parser.add_argument("--output", required=True, help="Output PPTX path.")
    parser.add_argument("--spec", required=True, help="Native-equations JSON specification.")
    parser.add_argument("--slide", type=int, default=1, help="One-based slide index.")
    return parser.parse_args()


def source_box_to_points(box_px, spec):
    x, y, width, height = [float(value) for value in box_px]
    source_width = float(spec["source_width_px"])
    source_height = float(spec["source_height_px"])
    content = spec["content_box"]
    left = float(content["left"]) * 72.0 + x / source_width * float(content["width"]) * 72.0
    top = float(content["top"]) * 72.0 + y / source_height * float(content["height"]) * 72.0
    box_width = width / source_width * float(content["width"]) * 72.0
    box_height = height / source_height * float(content["height"]) * 72.0
    return left, top, box_width, box_height


def paste_equation(word, slide, equation, spec):
    left, top, width, height = source_box_to_points(equation["box_px"], spec)
    document = word.Documents.Add()
    try:
        # A tight page produces a tight embedded OLE canvas rather than a full-width Word line.
        # Word rejects very narrow pages, and a page narrower than the equation can
        # suppress the OLE clipboard flavor. Reserve enough width for the linear source.
        estimated_ink_width = len(equation["linear"]) * float(equation.get("font_size", 10.0)) * 0.48
        document.PageSetup.PageWidth = max(width + 3.75, estimated_ink_width + 8.0, 216.0)
        document.PageSetup.PageHeight = 144.0
        document.PageSetup.LeftMargin = 2.0
        document.PageSetup.RightMargin = 2.0
        document.PageSetup.TopMargin = 2.0
        document.PageSetup.BottomMargin = 2.0

        linear = equation["linear"]
        equation_range = document.Range(0, 0)
        equation_range.Text = linear
        # Re-acquire the populated range. A zero-length Range remains collapsed
        # after assigning Text in some Word COM versions and yields a placeholder.
        equation_range = document.Range(0, len(linear))
        document.Activate()
        math_range = word.Selection.OMaths.Add(equation_range)
        math = math_range.OMaths(1)
        math.BuildUp()
        math_range = math.Range
        if not str(math_range.Text).strip():
            raise RuntimeError(f"Word created an empty OfficeMath range for {equation['id']}")
        math_range.Font.Name = "Cambria Math"
        math_range.Font.Size = float(equation.get("font_size", 10.0))
        # Copy the containing Word document range, not only the equation range.
        # PowerPoint's OLE paste embeds the Word selection; equation-only copying
        # can leave its cached OLE preview at the empty-placeholder state.
        document.Content.Copy()
        time.sleep(0.15)

        before = slide.Shapes.Count
        pasted = slide.Shapes.PasteSpecial(DataType=PP_PASTE_OLE_OBJECT)
        for _ in range(20):
            if slide.Shapes.Count > before:
                break
            time.sleep(0.1)
        if slide.Shapes.Count <= before and pasted is not None:
            for candidate_index in (1, 0):
                try:
                    shape = pasted.Item(candidate_index)
                    break
                except Exception:
                    shape = None
            if shape is None:
                try:
                    _ = pasted.Name
                    shape = pasted
                except Exception:
                    shape = None
        elif slide.Shapes.Count > before:
            shape = slide.Shapes(before + 1)
        else:
            shape = None
        if shape is None:
            raise RuntimeError(f"PowerPoint did not create an OLE shape for {equation['id']}")
        shape.LockAspectRatio = -1
        shape.Width = width
        shape.Left = left
        shape.Top = top + max(0.0, (height - float(shape.Height)) / 2.0)
        shape.Name = f"Equation {equation['id']}"
        shape.AlternativeText = f"Editable OfficeMath equation: {equation['id']}"
        try:
            shape.Tags.Add("equation_id", equation["id"])
            shape.Tags.Add("equation_source", "Word OfficeMath")
        except Exception:
            pass
        return {
            "id": equation["id"],
            "name": shape.Name,
            "prog_id": shape.OLEFormat.ProgID,
            "left": float(shape.Left),
            "top": float(shape.Top),
            "width": float(shape.Width),
            "height": float(shape.Height),
        }
    finally:
        document.Close(False)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    spec_path = Path(args.spec).expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"input PPTX not found: {input_path}")
    if not spec_path.is_file():
        raise SystemExit(f"equation spec not found: {spec_path}")
    if input_path == output_path:
        raise SystemExit("--input and --output must be different paths")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    equations = list(spec.get("equations") or [])
    if not equations:
        raise SystemExit("equation spec contains no equations")

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise SystemExit("pywin32 is required; run this script with the Windows Python that provides win32com") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, output_path)
    pythoncom.CoInitialize()
    word = None
    powerpoint = None
    presentation = None
    inserted = []
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
        try:
            powerpoint.Visible = True
        except Exception:
            pass
        # Clipboard/OLE paste requires an active presentation window in desktop Office.
        presentation = powerpoint.Presentations.Open(str(output_path), WithWindow=True)
        slide = presentation.Slides(args.slide)

        expected_names = {f"Equation {item['id']}" for item in equations}
        for index in range(slide.Shapes.Count, 0, -1):
            if slide.Shapes(index).Name in expected_names:
                slide.Shapes(index).Delete()

        for equation in equations:
            inserted.append(paste_equation(word, slide, equation, spec))
        presentation.Save()
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        if powerpoint is not None:
            try:
                powerpoint.Quit()
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()

    report = {
        "passed": len(inserted) == len(equations),
        "input": str(input_path),
        "output": str(output_path),
        "inserted_count": len(inserted),
        "equations": inserted,
    }
    report_path = output_path.with_suffix(".native-equations.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
