"""Verification for the raster-precision toolchain.

These tests build synthetic pages with known ground truth (font, pixel size, ink
position), then check that the solver recovers those numbers and that the gate
localises injected defects. The last test runs the whole chain through the
vendored builder's own preview renderer, which is the integration that matters.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scratch import scratch_dir  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-figure-drawer"
SCRIPTS = SKILL / "scripts"
SOLVER = SCRIPTS / "solve_text_metrics.py"
GATE = SCRIPTS / "compare_renders.py"

WINDOWS_FONTS = Path(r"C:\Windows\Fonts")
ARIAL = WINDOWS_FONTS / "arial.ttf"
SOURCE_SIZE = (1280, 720)
SLIDE = (13.3333, 7.5)
# 1280 px across 13.3333 in = 96 px per inch, so the builder's preview at
# preview_scale=96 reproduces the source at exactly 1:1.
PREVIEW_SCALE = 96


def load_module(name: str, path: Path):
    # The bundled runtime imports its sibling modules by bare name.
    directory = str(path.parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def require_font() -> Path:
    if not ARIAL.is_file():
        raise unittest.SkipTest("Arial is required for the raster-precision tests")
    return ARIAL


def paste_text(
    base: Image.Image,
    text: str,
    font_path: Path,
    size_px: int,
    target: tuple[int, int],
    color: tuple[int, int, int] = (17, 17, 17),
) -> list[int]:
    """Draw `text` so its tight ink lands with top-left exactly at `target`.

    Returns the ground-truth ink box `[left, top, width, height]`.
    """
    font = ImageFont.truetype(str(font_path), size_px)
    bbox = font.getbbox(text)
    pad = 6
    tile_size = (max(1, bbox[2] - bbox[0]) + 2 * pad, max(1, bbox[3] - bbox[1]) + 2 * pad)
    mask = Image.new("L", tile_size, 0)
    ImageDraw.Draw(mask).text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=255)
    ink = np.asarray(mask) > 127
    rows = np.flatnonzero(ink.any(axis=1))
    cols = np.flatnonzero(ink.any(axis=0))
    tight = (int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))
    ink_layer = Image.new("RGB", tile_size, color)
    base.paste(ink_layer, (target[0] - tight[0], target[1] - tight[1]), mask)
    return [target[0], target[1], tight[2], tight[3]]


def build_page(directory: Path, items: list[tuple[str, int, tuple[int, int]]], name: str = "source.png") -> tuple[Path, list[list[int]]]:
    """Render a synthetic page; returns (path, ground-truth ink boxes)."""
    font_path = require_font()
    canvas = Image.new("RGB", SOURCE_SIZE, (255, 255, 255))
    boxes = [paste_text(canvas, text, font_path, size_px, target) for text, size_px, target in items]
    path = directory / name
    canvas.save(path)
    return path, boxes


def hints_for(items: list[tuple[str, int, tuple[int, int]]], boxes: list[list[int]], path: Path) -> Path:
    """Build hints in the shape `editppt page hints` emits (padded ink boxes)."""
    lines = []
    for (text, _size, _target), box in zip(items, boxes):
        pad_x = max(2, int(round(box[3] * 0.35)))
        pad_y = max(1, int(round(box[3] * 0.30)))
        lines.append(
            {
                "box_px": [box[0] - pad_x, box[1] - pad_y, box[2] + 2 * pad_x, box[3] + 2 * pad_y],
                "text": text,
                "glyph_height_px": box[3],
                "line_count": 1,
                "size_group": "g1",
            }
        )
    payload = {"backend": "test-fixture", "source": {"width_px": SOURCE_SIZE[0], "height_px": SOURCE_SIZE[1]}, "lines": lines}
    out = path.with_name("text_hints.json")
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def run_solver(directory: Path, image: Path, hints: Path, out_name: str = "solved.json") -> dict:
    report = directory / out_name
    result = subprocess.run(
        [
            sys.executable,
            str(SOLVER),
            "--image",
            str(image),
            "--hints",
            str(hints),
            "--out",
            str(report),
            "--font-dir",
            str(WINDOWS_FONTS),
            "--families",
            "arial",
            "--slide",
            f"{SLIDE[0]}x{SLIDE[1]}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"solver failed: {result.stdout}\n{result.stderr}")
    return json.loads(report.read_text(encoding="utf-8"))


def run_gate(reference: Path, rendered: Path, report: Path, layout: Path | None = None, extra: list[str] | None = None) -> tuple[int, dict]:
    command = [
        sys.executable,
        str(GATE),
        "--reference",
        str(reference),
        "--rendered",
        str(rendered),
        "--report",
        str(report),
    ]
    if layout:
        command += ["--layout", str(layout)]
    command += extra or []
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if not report.is_file():
        raise AssertionError(f"gate produced no report (exit {result.returncode}):\n{result.stdout}\n{result.stderr}")
    return result.returncode, json.loads(report.read_text(encoding="utf-8"))


class SolverTests(unittest.TestCase):
    def test_recovers_font_size_and_style_from_raster(self):
        items = [
            ("Architecture Overview", 30, (80, 60)),
            ("Feature Extraction", 20, (80, 160)),
            ("Cross-Modal Attention", 14, (80, 240)),
        ]
        with scratch_dir("solver") as directory:
            image, boxes = build_page(directory, items)
            hints = hints_for(items, boxes, image)
            solved = run_solver(directory, image, hints)

            self.assertEqual(solved["summary"]["solved"], 3)
            self.assertGreaterEqual(solved["summary"]["high"], 2)
            self.assertEqual(len(solved["text_boxes"]), 3)
            for (text, size_px, _target), record, manifest_box in zip(items, solved["items"], solved["text_boxes"]):
                self.assertEqual(record["text"], text)
                self.assertIn("Arial", record["font"])
                self.assertLessEqual(
                    abs(record["font_size_px"] - size_px),
                    1.0,
                    f"{text!r}: solved {record['font_size_px']} px, drew {size_px} px",
                )
                self.assertGreaterEqual(record["ink_iou"], 0.70, f"{text!r}: ink IoU {record['ink_iou']}")
                self.assertEqual(manifest_box["font_size_source"], "measured")
                self.assertTrue(Path(manifest_box["preview_font"]).is_file())

    def test_high_confidence_solve_disables_the_width_table_clamp(self):
        items = [("Raster Input", 26, (100, 100))]
        with scratch_dir("clamp") as directory:
            image, boxes = build_page(directory, items)
            solved = run_solver(directory, image, hints_for(items, boxes, image))
            box = solved["text_boxes"][0]
            self.assertGreaterEqual(box["_solve"]["ink_iou"], 0.70)
            self.assertIs(box["fit_text"], False, "a verified measurement must not be clamped by the estimate")
            # The measured size must survive the builder's own normalisation.
            builder = load_module("builder", SKILL / "cli" / "editppt" / "runtime" / "build_pptx_from_manifest.py")
            manifest = {
                "slide": {"width": SLIDE[0], "height": SLIDE[1]},
                "source": {"width_px": SOURCE_SIZE[0], "height_px": SOURCE_SIZE[1]},
                "text_boxes": [box],
            }
            normalized = builder.normalize_manifest(manifest)
            self.assertAlmostEqual(normalized["text_boxes"][0]["font_size"], box["font_size"], places=3)

    def test_box_geometry_lands_source_ink_on_the_box_top_left(self):
        items = [("Publication Ready", 24, (200, 180))]
        with scratch_dir("geometry") as directory:
            image, boxes = build_page(directory, items)
            solved = run_solver(directory, image, hints_for(items, boxes, image))
            record = solved["items"][0]
            manifest_box = solved["text_boxes"][0]
            # Reconstruct where the renderer will put the ink: box origin plus the
            # font's ink offset at the solved size (zero insets, top anchor).
            font = ImageFont.truetype(record["font_file"], int(round(record["font_size_px"])))
            offset_x, offset_y, _x1, _y1 = font.getbbox(record["text"])
            scale = record["font_size_px"] / int(round(record["font_size_px"]))
            predicted_x = manifest_box["box_px"][0] + offset_x * scale
            predicted_y = manifest_box["box_px"][1] + offset_y * scale
            self.assertLessEqual(abs(predicted_x - boxes[0][0]), 1.5)
            self.assertLessEqual(abs(predicted_y - boxes[0][1]), 1.5)

    def test_hints_without_text_are_reported_not_guessed(self):
        with scratch_dir("notext") as directory:
            image, boxes = build_page(directory, [("Silent", 20, (60, 60))])
            hints = hints_for([("Silent", 20, (60, 60))], boxes, image)
            payload = json.loads(hints.read_text(encoding="utf-8"))
            payload["lines"][0]["text"] = ""
            hints.write_text(json.dumps(payload), encoding="utf-8")
            solved = run_solver(directory, image, hints)
            self.assertEqual(solved["items"][0]["mode"], "hint-only")
            self.assertIn("no_text_in_hints", solved["items"][0]["warnings"])
            self.assertEqual(solved["text_boxes"], [])


class BandRegressionTests(unittest.TestCase):
    """Guards the fixes that the real-page test exposed."""

    def test_dominant_band_ignores_a_neighbouring_band(self):
        metrics = load_module("image_metrics_band", SCRIPTS / "image_metrics.py")
        mask = np.zeros((40, 10), dtype=bool)
        mask[4:7, :] = True      # descenders of the line above
        mask[20:26, :] = True    # the line under measurement
        band = metrics.dominant_band(mask, center_row=22)
        self.assertEqual(band, (20, 25))
        # without a centre the heaviest band still wins
        self.assertEqual(metrics.dominant_band(mask), (20, 25))

    def test_previous_line_descender_does_not_shift_the_solved_box(self):
        """A padded hint box that overlaps the line above must not move the solve."""
        font_path = require_font()
        with scratch_dir("descender") as directory:
            canvas = Image.new("RGB", SOURCE_SIZE, (255, 255, 255))
            # line above, with descenders that reach well below its baseline
            paste_text(canvas, "gapy jumping", font_path, 20, (80, 100))
            # the measured line sits close below it
            target = (80, 130)
            box = paste_text(canvas, "Measured Line", font_path, 20, target)
            image = directory / "source.png"
            canvas.save(image)

            # a padded hint box, as the detectors emit, reaches up into the line above
            pad_y = 8
            hint = {
                "backend": "fixture",
                "lines": [
                    {
                        "box_px": [box[0] - 3, box[1] - pad_y, box[2] + 6, box[3] + 2 * pad_y],
                        "text": "Measured Line",
                        "glyph_height_px": box[3],
                        "line_count": 1,
                    }
                ],
            }
            hints = directory / "text_hints.json"
            hints.write_text(json.dumps(hint), encoding="utf-8")
            solved = run_solver(directory, image, hints)

            record = solved["items"][0]
            self.assertEqual(record["mode"], "solved")
            # the band restriction keeps only the measured line, so the ink box is its own
            self.assertLessEqual(
                abs(record["ink_box_px"][1] - box[1]),
                2,
                f"ink top {record['ink_box_px'][1]} drifted from the true {box[1]}",
            )


class GateTests(unittest.TestCase):
    def test_identical_render_passes_the_gate(self):
        items = [("Exact Match", 22, (120, 90))]
        with scratch_dir("identical") as directory:
            image, boxes = build_page(directory, items)
            solved = run_solver(directory, image, hints_for(items, boxes, image))
            code, report = run_gate(image, image, directory / "report.json", layout=directory / "solved.json")
            self.assertEqual(code, 0, report["problems"])
            self.assertTrue(report["passed"])
            self.assertGreaterEqual(report["metrics"]["ssim"], 0.999)

    def test_missing_text_is_a_failure_with_a_localised_repair_target(self):
        items = [("Keep This Line", 22, (120, 90)), ("Erase This Line", 22, (120, 200))]
        with scratch_dir("missing") as directory:
            image, boxes = build_page(directory, items)
            solved = run_solver(directory, image, hints_for(items, boxes, image))
            damaged = Image.open(image).convert("RGB")
            left, top, width, height = boxes[1]
            ImageDraw.Draw(damaged).rectangle([left - 4, top - 4, left + width + 4, top + height + 4], fill=(255, 255, 255))
            rendered = directory / "rendered.png"
            damaged.save(rendered)

            code, report = run_gate(image, rendered, directory / "report.json", layout=directory / "solved.json")
            self.assertEqual(code, 1)
            self.assertFalse(report["passed"])
            statuses = {item["text"]: item["status"] for item in report["text_checks"]["items"]}
            self.assertEqual(statuses.get("Erase This Line"), "missing_text")
            self.assertEqual(statuses.get("Keep This Line"), "ok")
            self.assertGreater(report["metrics"]["lost_ink_tile_count"], 0, "the ink-loss channel missed a deleted text line")
            target = boxes[1]
            self.assertTrue(
                any(
                    candidate["box_px"][0] <= target[0] + target[2] and candidate["box_px"][0] + candidate["box_px"][2] >= target[0]
                    and candidate["box_px"][1] <= target[1] + target[3] and candidate["box_px"][1] + candidate["box_px"][3] >= target[1]
                    for candidate in report["repair_targets"]
                ),
                f"repair targets did not cover the erased text at {target}: {report['repair_targets']}",
            )

    def test_global_scale_drift_is_reported_as_alignment(self):
        items = [("Anchored Block", 24, (160, 120))]
        with scratch_dir("scale") as directory:
            image, boxes = build_page(directory, items)
            original = Image.open(image).convert("RGB")
            # Shrink the content slightly and recentre it: a canvas/scale error.
            shrunk = original.resize((int(SOURCE_SIZE[0] * 0.94), int(SOURCE_SIZE[1] * 0.94)), Image.Resampling.LANCZOS)
            rendered_image = Image.new("RGB", SOURCE_SIZE, (255, 255, 255))
            rendered_image.paste(shrunk, ((SOURCE_SIZE[0] - shrunk.width) // 2, (SOURCE_SIZE[1] - shrunk.height) // 2))
            rendered = directory / "rendered.png"
            rendered_image.save(rendered)

            code, report = run_gate(image, rendered, directory / "report.json")
            self.assertEqual(code, 1)
            self.assertTrue(report["content_alignment"]["comparable"])
            scale = report["content_alignment"]["scale_ratio"]
            self.assertLess(scale[0], 0.99)
            self.assertTrue(any("scaled" in problem or "offset" in problem for problem in report["problems"]), report["problems"])

    def test_advisory_mode_keeps_the_old_always_zero_behaviour(self):
        items = [("Present", 22, (100, 100))]
        with scratch_dir("advisory") as directory:
            image, boxes = build_page(directory, items)
            blank = Image.new("RGB", SOURCE_SIZE, (255, 255, 255))
            rendered = directory / "blank.png"
            blank.save(rendered)
            code, report = run_gate(image, rendered, directory / "report.json", extra=["--advisory"])
            self.assertEqual(code, 0)
            self.assertFalse(report["passed"])
            self.assertTrue(report["problems"])


class ClosedLoopTests(unittest.TestCase):
    def test_solver_to_manifest_to_builder_preview_passes_the_gate(self):
        items = [
            ("System Overview", 30, (90, 70)),
            ("Encoder Stack", 20, (90, 170)),
            ("Fusion and Calibration", 16, (90, 250)),
        ]
        with scratch_dir("loop") as directory:
            image, boxes = build_page(directory, items)
            solved = run_solver(directory, image, hints_for(items, boxes, image))

            manifest = {
                "slide": {"width": SLIDE[0], "height": SLIDE[1], "background": "#ffffff"},
                "source": {"width_px": SOURCE_SIZE[0], "height_px": SOURCE_SIZE[1]},
                "content_box": {"left": 0.0, "top": 0.0, "width": SLIDE[0], "height": SLIDE[1]},
                "preview_scale": PREVIEW_SCALE,
                "text_boxes": solved["text_boxes"],
                "shapes": [],
                "images": [],
                "tables": [],
                "text_inventory": [box["text"] for box in solved["text_boxes"]],
                "visual_inventory": [],
                "background_strategy": "solid background colour, no source raster layer",
                "quality_checks": {
                    "font_size_calibrated": True,
                    "visual_inventory_matched": True,
                    "background_strategy_checked": True,
                },
                "asset_provenance": [],
            }
            manifest_path = directory / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            builder = load_module("builder_loop", SKILL / "cli" / "editppt" / "runtime" / "build_pptx_from_manifest.py")
            preview = directory / "preview.png"
            builder.render_preview(manifest, str(manifest_path), str(preview))
            self.assertTrue(preview.is_file(), "the bundled preview renderer produced no image")

            with Image.open(preview) as preview_image:
                # The preview size is int(inches * preview_scale), so a one-pixel
                # rounding difference from the source is expected.
                self.assertLessEqual(abs(preview_image.size[0] - SOURCE_SIZE[0]), 2, f"preview size {preview_image.size}")
                self.assertLessEqual(abs(preview_image.size[1] - SOURCE_SIZE[1]), 2, f"preview size {preview_image.size}")

            code, report = run_gate(image, preview, directory / "report.json", layout=directory / "solved.json")
            self.assertEqual(code, 0, f"closed loop failed: {report['problems']}")
            self.assertTrue(report["passed"])
            self.assertEqual(report["text_checks"]["failing"], 0)
            self.assertGreaterEqual(report["metrics"]["ssim"], 0.95)


if __name__ == "__main__":
    unittest.main()
