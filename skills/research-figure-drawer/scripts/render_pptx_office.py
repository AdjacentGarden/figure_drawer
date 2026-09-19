#!/usr/bin/env python3
"""Render a PowerPoint slide through the installed desktop PowerPoint engine."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--slide", type=int, default=1)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()

    pptx_path = Path(args.pptx).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise SystemExit("pywin32 is required for Office-native rendering") from exc

    pythoncom.CoInitialize()
    app = None
    presentation = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        try:
            app.Visible = True
        except Exception:
            pass
        presentation = app.Presentations.Open(str(pptx_path), WithWindow=False)
        presentation.Slides(args.slide).Export(str(output_path), "PNG", args.width, args.height)
    finally:
        if presentation is not None:
            presentation.Close()
        if app is not None:
            app.Quit()
        pythoncom.CoUninitialize()
    if not output_path.is_file():
        raise SystemExit(f"PowerPoint did not create the requested render: {output_path}")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
