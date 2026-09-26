#!/usr/bin/env python3
"""Render and round-trip a PPTX through Windows WPS Presentation.

Run this script on the target Windows host.  It uses ``KWPP.Application`` via
pywin32, exports every slide to PNG, saves a round-tripped PPTX, reopens that
file, exports it again, and writes provenance JSON.  A Pillow preview is not a
substitute for this output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_sha256(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Pillow is required on the WPS host: python -m pip install Pillow") from exc
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        payload = f"{rgba.width}x{rgba.height}:RGBA:".encode("ascii") + rgba.tobytes()
    return hashlib.sha256(payload).hexdigest()


def export_slides(presentation, directory: Path, width: int, height: int) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for index in range(1, presentation.Slides.Count + 1):
        target = directory / f"slide-{index:03d}.png"
        presentation.Slides(index).Export(str(target), "PNG", width, height)
        outputs.append({"path": str(target), "sha256": sha256(target), "pixel_sha256": pixel_sha256(target)})
    return outputs


def close_wps(app, presentation=None) -> None:
    if presentation is not None:
        try:
            presentation.Close()
        except Exception:
            pass
    if app is not None:
        try:
            app.Quit()
        except Exception:
            pass


def open_presentation(app, source: Path, *, read_only: bool):
    """Open a presentation using WPS-compatible positional COM arguments.

    Some WPS 12.0 type libraries accept PowerPoint's keyword argument names
    syntactically but return a dispatch proxy named ``Open`` instead of the
    Presentation object.  Positional arguments are reliable across the tested
    WPS builds.  Touching ``Slides.Count`` also turns a silent proxy mismatch
    into an immediate, actionable error.
    """
    presentation = app.Presentations.Open(
        str(source), bool(read_only), False, False
    )
    try:
        int(presentation.Slides.Count)
    except Exception as exc:
        raise RuntimeError(
            f"WPS did not return a Presentation object for {source}"
        ) from exc
    return presentation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=0, help="0 derives height from the WPS slide aspect ratio")
    args = parser.parse_args()

    try:
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise SystemExit("pywin32 is required on Windows: python -m pip install pywin32") from exc

    source = Path(args.input).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    roundtrip = out_dir / "roundtrip.pptx"
    # A WPS process that has just finished a separate automation job can leave
    # a short-lived COM registration proxy behind.  Retry the *initial* open as
    # well as the later round-trip open so build -> export works in one command.
    first_open_attempts = 0
    last_error = None
    for attempt in range(1, 4):
        first_open_attempts = attempt
        app = None
        first = None
        try:
            app = win32com.client.DispatchEx("KWPP.Application")
            # Current WPS builds may reject hidden automation with E_UNEXPECTED.
            # A visible window is more reliable and does not change exports.
            app.Visible = True
            version = str(getattr(app, "Version", "unknown"))
            first = open_presentation(app, source, read_only=False)
            slide_width = float(first.PageSetup.SlideWidth)
            slide_height = float(first.PageSetup.SlideHeight)
            export_height = args.height or max(1, round(args.width * slide_height / slide_width))
            first_exports = export_slides(first, out_dir / "first-open", args.width, export_height)
            first.SaveAs(str(roundtrip))
            first.Close()
            first = None
            close_wps(app)
            break
        except Exception as exc:
            last_error = exc
            close_wps(app, first)
            if attempt < 3:
                time.sleep(2)
    else:
        raise RuntimeError("WPS initial open/export failed after 3 attempts") from last_error

    # Use a fresh WPS process for the reopen check.  This is both a stronger
    # round-trip test and avoids stale RPC state in long-running WPS sessions.
    reopen_attempts = 0
    last_error = None
    for attempt in range(1, 4):
        reopen_attempts = attempt
        app = None
        second = None
        try:
            app = win32com.client.DispatchEx("KWPP.Application")
            app.Visible = True
            second = open_presentation(app, roundtrip, read_only=True)
            second_exports = export_slides(second, out_dir / "reopened", args.width, export_height)
            slide_count = int(second.Slides.Count)
            second.Close()
            second = None
            close_wps(app)
            break
        except Exception as exc:
            last_error = exc
            close_wps(app, second)
            if attempt < 3:
                time.sleep(2)
    else:
        raise RuntimeError("WPS reopen/export failed after 3 attempts") from last_error

    first_hashes = [item["pixel_sha256"] for item in first_exports]
    reopened_hashes = [item["pixel_sha256"] for item in second_exports]
    roundtrip_stable = first_hashes == reopened_hashes
    report = {
        "schema_version": 1,
        "renderer": "WPS Presentation COM",
        "prog_id": "KWPP.Application",
        "wps_version": version,
        "host": platform.node(),
        "platform": platform.platform(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(source),
        "source_sha256": sha256(source),
        "roundtrip": str(roundtrip),
        "roundtrip_sha256": sha256(roundtrip),
        "slide_count": slide_count,
        "slide_size_points": [slide_width, slide_height],
        "export_size": [args.width, export_height],
        "first_open_exports": first_exports,
        "reopened_exports": second_exports,
        "roundtrip_visual_stable": roundtrip_stable,
        "first_open_attempts": first_open_attempts,
        "reopen_attempts": reopen_attempts,
        "passed": (
            slide_count > 0
            and all(Path(item["path"]).is_file() for item in first_exports + second_exports)
            and roundtrip_stable
        ),
    }
    report_path = out_dir / "wps-render-provenance.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
