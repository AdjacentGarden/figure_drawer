from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-figure-drawer"
SCRIPTS = SKILL / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class SkillScriptTests(unittest.TestCase):
    def test_prompt_builder_preserves_topology_and_labels(self):
        module = load_module("prompt_builder", SCRIPTS / "build_imagegen_prompt.py")
        data = json.loads((ROOT / "examples" / "multimodal-method.json").read_text(encoding="utf-8"))
        prompt = module.build_prompt(data)
        self.assertIn("from=visual_encoder; to=cross_attention", prompt)
        self.assertIn('"Cross-Modal Attention"', prompt)
        self.assertIn("do not reverse or invent arrows", prompt)

    def test_init_run_creates_isolated_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "init_figure_run.py"), "--text", "A -> B", "--out-root", tmp, "--name", "demo"],
                text=True,
                capture_output=True,
                check=True,
            )
            run_dir = Path(result.stdout.strip())
            self.assertTrue((run_dir / "request.md").is_file())
            self.assertTrue((run_dir / "figure_spec.json").is_file())
            self.assertTrue((run_dir / "reference").is_dir())
            self.assertTrue((run_dir / "final").is_dir())
            figure_spec = json.loads((run_dir / "figure_spec.json").read_text(encoding="utf-8"))
            self.assertEqual(figure_spec["reconstruction"]["mode"], "reference-guided-hybrid")

    def test_final_validation_checks_native_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            spec = {"exact_text": ["Encoder", "Decoder"]}
            (tmp / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (tmp / "validation.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            slide = """<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><p:cSld><p:spTree><p:sp><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Encoder</a:t></a:r></a:p><a:p><a:r><a:t>Decoder</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"""
            with zipfile.ZipFile(tmp / "result.pptx", "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", slide)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "validate_figure_run.py"),
                    "--spec", str(tmp / "spec.json"),
                    "--pptx", str(tmp / "result.pptx"),
                    "--editppt-validation", str(tmp / "validation.json"),
                    "--report", str(tmp / "report.json"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads((tmp / "report.json").read_text(encoding="utf-8"))["passed"])

    def test_short_label_requires_its_own_native_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "spec.json").write_text(json.dumps({"exact_text": ["V"]}), encoding="utf-8")
            (tmp / "validation.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            slide = """<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><p:cSld><p:spTree><p:sp><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Visual Encoder</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"""
            with zipfile.ZipFile(tmp / "result.pptx", "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", slide)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "validate_figure_run.py"),
                    "--spec", str(tmp / "spec.json"),
                    "--pptx", str(tmp / "result.pptx"),
                    "--editppt-validation", str(tmp / "validation.json"),
                    "--report", str(tmp / "report.json"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads((tmp / "report.json").read_text(encoding="utf-8"))["missing_labels"], ["V"])

    def test_builtin_reference_import_records_no_unverified_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "tool-output.png"
            source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "import_builtin_reference.py"),
                    "--source", str(source),
                    "--out", str(tmp / "run" / "reference.png"),
                    "--record", str(tmp / "run" / "provenance.json"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            provenance = json.loads((tmp / "run" / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["backend"], "builtin-imagegen")
            self.assertIsNone(provenance["model_id"])

    def test_quality_audit_passes_vector_and_readable_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            assets = tmp / "assets"
            assets.mkdir()
            (assets / "icon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'/>", encoding="utf-8")
            manifest = {
                "slide": {"width": 10, "height": 5.625},
                "source": {"width_px": 1000, "height_px": 563},
                "quality_policy": {"min_font_pt": 10, "min_raster_dpi": 300},
                "text_boxes": [{"text": "Encoder", "font_size": 11, "box_px": [20, 20, 100, 30]}],
                "images": [{"id": "icon", "path": "assets/icon.svg", "box_px": [20, 60, 40, 40]}],
                "visual_inventory": [{"id": "icon", "role": "foreground", "path": "assets/icon.svg", "vector_required": True}],
                "formula_inventory": [{"id": "eq", "image": "assets/icon.svg"}],
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "audit_figure_quality.py"), "--manifest", str(tmp / "manifest.json"), "--report", str(tmp / "report.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads((tmp / "report.json").read_text(encoding="utf-8"))["passed"])

    def test_quality_audit_rejects_small_text_low_dpi_and_raster_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            assets = tmp / "assets"
            assets.mkdir()
            Image.new("RGBA", (20, 20), "white").save(assets / "icon.png")
            manifest = {
                "slide": {"width": 10, "height": 5.625},
                "source": {"width_px": 1000, "height_px": 563},
                "quality_policy": {"min_font_pt": 10, "min_raster_dpi": 300, "prefer_vector_formulas": True},
                "text_boxes": [{"text": "Tiny", "font_size": 8, "box_px": [20, 20, 100, 30]}],
                "images": [{"id": "icon", "path": "assets/icon.png", "box_px": [20, 60, 100, 100]}],
                "visual_inventory": [{"id": "icon", "role": "foreground", "path": "assets/icon.png", "vector_required": True}],
                "formula_inventory": [{"id": "eq", "image": "assets/icon.png"}],
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "audit_figure_quality.py"), "--manifest", str(tmp / "manifest.json"), "--report", str(tmp / "report.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            kinds = {item["kind"] for item in json.loads((tmp / "report.json").read_text(encoding="utf-8"))["violations"]}
            self.assertTrue({"font-size", "raster-dpi", "formula-not-vector", "vector-required"}.issubset(kinds))

    def test_quality_audit_accepts_declared_native_editable_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest = {
                "slide": {"width": 10, "height": 5.625},
                "source": {"width_px": 1000, "height_px": 563},
                "quality_policy": {"prefer_editable_formulas": True},
                "text_boxes": [{"text": "Encoder", "font_size": 11, "box_px": [20, 20, 100, 30]}],
                "images": [],
                "visual_inventory": [],
                "formula_inventory": [
                    {
                        "id": "eq",
                        "decision": "native-office-math-ole",
                        "editable": True,
                        "box_px": [200, 100, 240, 40],
                    }
                ],
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "audit_figure_quality.py"), "--manifest", str(tmp / "manifest.json"), "--report", str(tmp / "report.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((tmp / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["formula_editable"], 1)

    def test_layout_audit_rejects_overlap_line_crossing_and_bad_cube(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest = {
                "source": {"width_px": 1000, "height_px": 600},
                "quality_policy": {"connector_text_inset_px": 2},
                "text_boxes": [
                    {"id": "a", "text": "A", "box_px": [100, 100, 100, 40]},
                    {"id": "b", "text": "B", "box_px": [150, 110, 100, 40]},
                ],
                "formula_inventory": [],
                "shapes": [
                    {"type": "line", "points_px": [0, 120, 300, 120], "semantic_line_id": "flow"},
                    {"type": "polygon", "box_px": [400, 100, 40, 20], "polygon_px": [[420, 100], [440, 110], [420, 120], [400, 109]], "geometry_role": "isometric-cube-face", "cube_id": "cube", "face": "top"},
                    {"type": "polygon", "box_px": [400, 110, 20, 30], "polygon_px": [[400, 110], [420, 120], [420, 140], [400, 130]], "geometry_role": "isometric-cube-face", "cube_id": "cube", "face": "left"},
                    {"type": "polygon", "box_px": [420, 110, 20, 30], "polygon_px": [[420, 120], [440, 110], [440, 130], [420, 140]], "geometry_role": "isometric-cube-face", "cube_id": "cube", "face": "right"},
                ],
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "audit_layout_geometry.py"), "--manifest", str(tmp / "manifest.json"), "--report", str(tmp / "layout.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            kinds = {item["kind"] for item in json.loads((tmp / "layout.json").read_text(encoding="utf-8"))["violations"]}
            self.assertTrue({"content-overlap", "connector-crosses-content", "cube-face-not-parallelogram"}.issubset(kinds))

    def test_layout_audit_accepts_separated_content_and_exact_cube(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest = {
                "source": {"width_px": 1000, "height_px": 600},
                "text_boxes": [
                    {"id": "a", "text": "A", "box_px": [100, 100, 80, 30]},
                    {"id": "b", "text": "B", "box_px": [260, 100, 80, 30]},
                ],
                "formula_inventory": [],
                "shapes": [
                    {"type": "line", "points_px": [180, 150, 260, 150], "semantic_line_id": "flow"},
                    {"type": "polygon", "box_px": [400, 100, 40, 20], "polygon_px": [[420, 100], [440, 110], [420, 120], [400, 110]], "geometry_role": "isometric-cube-face", "cube_id": "cube", "face": "top"},
                    {"type": "polygon", "box_px": [400, 110, 20, 30], "polygon_px": [[400, 110], [420, 120], [420, 140], [400, 130]], "geometry_role": "isometric-cube-face", "cube_id": "cube", "face": "left"},
                    {"type": "polygon", "box_px": [420, 110, 20, 30], "polygon_px": [[420, 120], [440, 110], [440, 130], [420, 140]], "geometry_role": "isometric-cube-face", "cube_id": "cube", "face": "right"},
                ],
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "audit_layout_geometry.py"), "--manifest", str(tmp / "manifest.json"), "--report", str(tmp / "layout.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_equation_audit_verifies_embedded_word_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            spec = {"equations": [{"id": "loss"}]}
            (tmp / "native-equations.json").write_text(json.dumps(spec), encoding="utf-8")
            slide = """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="Equation loss"/></p:nvGraphicFramePr><p:graphic><p:graphicData><p:oleObj progId="Word.Document.8"/></p:graphicData></p:graphic></p:graphicFrame></p:spTree></p:cSld></p:sld>"""
            with zipfile.ZipFile(tmp / "equation.pptx", "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", slide)
                archive.writestr("ppt/embeddings/oleObject1.bin", b"fixture")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "audit_native_equations.py"), "--pptx", str(tmp / "equation.pptx"), "--spec", str(tmp / "native-equations.json"), "--report", str(tmp / "audit.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_render_comparison_reports_identical_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            image = Image.new("RGB", (160, 90), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 20, 140, 70), outline="navy", width=4)
            image.save(tmp / "reference.png")
            image.save(tmp / "rendered.png")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "compare_renders.py"), "--reference", str(tmp / "reference.png"), "--rendered", str(tmp / "rendered.png"), "--report", str(tmp / "report.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            metrics = json.loads((tmp / "report.json").read_text(encoding="utf-8"))["metrics"]
            self.assertEqual(metrics["luminance_mae"], 0.0)
            self.assertEqual(metrics["edge_f1"], 1.0)

    def test_svg_use_flattener_inlines_referenced_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "input.svg"
            source.write_text(
                """<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' viewBox='0 0 20 20'><defs><symbol id='g'><path d='M0 0L2 0L2 2Z'/></symbol></defs><g fill='black'><use xlink:href='#g' x='5' y='7'/></g></svg>""",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "flatten_svg_uses.py"), "--input", str(source), "--output", str(tmp / "output.svg")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            root = ET.parse(tmp / "output.svg").getroot()
            tags = [node.tag.rsplit("}", 1)[-1] for node in root.iter()]
            self.assertNotIn("use", tags)
            self.assertNotIn("defs", tags)
            self.assertIn("path", tags)


if __name__ == "__main__":
    unittest.main()
