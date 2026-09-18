from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


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

    def test_final_validation_checks_native_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            spec = {"exact_text": ["Encoder", "Decoder"]}
            (tmp / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (tmp / "validation.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            slide = """<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Encoder</a:t></a:r></a:p><a:p><a:r><a:t>Decoder</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"""
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
            slide = """<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Visual Encoder</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"""
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


if __name__ == "__main__":
    unittest.main()
