from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scratch import scratch_dir  # noqa: E402


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
    def test_perceptual_gate_requires_five_distinct_unfooled_reviewers(self):
        module = load_module("perceptual_gate", SCRIPTS / "evaluate_perceptual_benchmark.py")
        verdicts = [
            {"reviewer_id": f"r{i}", "similarity_0_100": 96,
             "reliably_distinguishable": False, "original_guess": "uncertain"}
            for i in range(5)
        ]
        self.assertTrue(module.evaluate(verdicts)["passed"])
        verdicts[3]["similarity_0_100"] = 94
        self.assertFalse(module.evaluate(verdicts)["passed"])
        verdicts[3]["similarity_0_100"] = 96
        verdicts[2]["reliably_distinguishable"] = True
        self.assertFalse(module.evaluate(verdicts)["passed"])
        verdicts[4]["reviewer_id"] = "r0"
        with self.assertRaises(ValueError):
            module.evaluate(verdicts)

    def test_wps_native_manifest_rejects_uneditable_full_slide_picture(self):
        module = load_module("wps_native_builder", SCRIPTS / "wps_native_builder.py")
        with scratch_dir("native-manifest") as tmp:
            tmp = Path(tmp)
            (tmp / "full.png").write_bytes(b"image")
            manifest = {
                "figure_id": "test",
                "canvas": {"width": 100, "height": 100},
                "elements": [{"kind": "image", "file": "full.png", "x": 0, "y": 0, "w": 100, "h": 100}],
            }
            with self.assertRaises(ValueError):
                module.validate_manifest(manifest, tmp)
            manifest["elements"][0].update({"w": 30, "h": 30})
            inventory = module.validate_manifest(manifest, tmp)
            self.assertEqual(inventory["pictures"], 1)
            self.assertEqual(inventory["live_text"], 0)
            manifest["elements"].append({"kind": "text", "x": 10, "y": 10, "w": 20, "h": 10, "text": "Label"})
            inventory = module.validate_manifest(manifest, tmp)
            self.assertEqual(inventory["live_text"], 1)

    def test_wps_export_uses_positional_open_arguments_and_validates_result(self):
        module = load_module("wps_export", SCRIPTS / "wps_export.py")

        class Presentation:
            def __init__(self):
                self.Slides = type("Slides", (), {"Count": 1})()

        class Presentations:
            def __init__(self, result):
                self.result = result
                self.calls = []

            def Open(self, *args):
                self.calls.append(args)
                return self.result

        class App:
            def __init__(self, result):
                self.Presentations = Presentations(result)

        app = App(Presentation())
        result = module.open_presentation(app, Path("figure.pptx"), read_only=True)
        self.assertIsInstance(result, Presentation)
        self.assertEqual(app.Presentations.calls, [("figure.pptx", True, False, False)])

        with self.assertRaises(RuntimeError):
            module.open_presentation(App(object()), Path("bad.pptx"), read_only=False)

    def test_tex_classifier_distinguishes_self_contained_and_placeholder(self):
        module = load_module("tex_classifier", SCRIPTS / "classify_tex_source.py")
        deterministic = module.classify(r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}")
        self.assertEqual(deterministic["mode"], "deterministic-vector")
        placeholder = module.classify(r"\includegraphics{method.pdf}")
        self.assertEqual(placeholder["mode"], "external-image-placeholder")
        commented = module.classify("% \\begin{tikzpicture}\nprose only")
        self.assertEqual(commented["mode"], "semantic-description")
        dependent = module.classify(
            r"\begin{tikzpicture}\input{nodes.tex}\end{tikzpicture}"
        )
        self.assertEqual(dependent["mode"], "external-image-placeholder")

    def test_figure_extractor_isolates_tikz_from_unrelated_images(self):
        module = load_module("tex_extractor", SCRIPTS / "extract_tex_figure.py")
        paper = r"""
        \documentclass{article}
        \usepackage{tikz}
        \definecolor{accent}{RGB}{10,20,30}
        \begin{document}
        \includegraphics{unrelated.png}
        \begin{figure}\begin{tikzpicture}\draw[accent] (0,0)--(1,1);\end{tikzpicture}
        \label{fig:target}\end{figure}
        \end{document}
        """
        snippet, report = module.extract(paper, "fig:target", 1)
        self.assertIn("definecolor{accent}", snippet)
        self.assertNotIn("includegraphics", snippet)
        self.assertEqual(report["classification"]["mode"], "deterministic-vector")

    def test_figure_extractor_preserves_local_input_wrapper_and_used_style(self):
        module = load_module("tex_extractor_dependencies", SCRIPTS / "extract_tex_figure.py")
        with scratch_dir("tex-input") as tmp:
            tmp = Path(tmp)
            (tmp / "header.sty").write_text(
                r"\definecolor{used}{HTML}{4285F4}"
                "\n" + r"\definecolor{unused}{HTML}{FFFFFF}"
                "\n" + r"\renewcommand{\rmdefault}{ptm}"
                "\n" + r"\renewcommand{\footnotesize}{\@setfontsize\footnotesize\@ixpt\@xpt}"
                "\n" + r"\newcommand{\todo}[1]{first}"
                "\n" + r"\newcommand{\todo}[1]{second}",
                encoding="utf-8",
            )
            (tmp / "panel.tex").write_text(
                r"\tikzset{every picture/.style={line width=0.75pt}}"
                "\n" + r"\begin{tikzpicture}\draw[used](0,0)--(1,1);\end{tikzpicture}",
                encoding="utf-8",
            )
            source = tmp / "paper.tex"
            source.write_text(
                r"\documentclass{article}\usepackage{header}\begin{document}"
                r"\begin{figure}\resizebox{1.0\textwidth}{!}{\input{panel.tex}}"
                r"\caption{x}\label{fig:target}\end{figure}\end{document}",
                encoding="utf-8",
            )
            snippet, report = module.extract(source.read_text(encoding="utf-8"), "fig:target", 1, source=source)
            self.assertIn(r"\resizebox{1.0\textwidth}{!}", snippet)
            self.assertIn("line width=0.75pt", snippet)
            self.assertIn("definecolor{used}", snippet)
            self.assertNotIn("definecolor{unused}", snippet)
            self.assertNotIn("newcommand{\\todo}", snippet)
            self.assertIn(r"\renewcommand{\rmdefault}{ptm}", snippet)
            self.assertIn(r"\renewcommand{\footnotesize}", snippet)
            self.assertIn(r"\makeatletter", snippet)
            self.assertTrue(report["input_dependencies"][0]["sha256"])
            self.assertTrue(report["style_dependencies"][0]["sha256"])

    def test_editability_audit_rejects_large_picture_with_padding_shapes(self):
        module = load_module("editability_audit", SCRIPTS / "audit_pptx_editability.py")
        with scratch_dir("editability-audit") as tmp:
            pptx = Path(tmp) / "fake.pptx"
            presentation = """<p:presentation xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:sldSz cx=\"1000\" cy=\"1000\"/></p:presentation>"""
            slide = """<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><p:cSld><p:spTree>
            <p:pic><p:nvPicPr><p:cNvPr id=\"1\" name=\"large\"/></p:nvPicPr><p:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"690\" cy=\"1000\"/></a:xfrm></p:spPr></p:pic>
            <p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"small-label\"/></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"100\" y=\"100\"/><a:ext cx=\"10\" cy=\"10\"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:t>Visual
Encoder</a:t></a:r></a:p></p:txBody></p:sp>
            <p:sp><p:nvSpPr><p:cNvPr id=\"3\" name=\"hidden\" hidden=\"1\"/></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"1000\" cy=\"1000\"/></a:xfrm></p:spPr></p:sp>
            </p:spTree></p:cSld></p:sld>"""
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr("ppt/presentation.xml", presentation)
                archive.writestr("ppt/slides/slide1.xml", slide)
            report = module.audit(
                pptx, max_picture_fraction=0.70, max_total_picture_fraction=0.70,
                min_native_objects=1, min_native_text_runs=1,
                min_native_coverage=0.15, expected_text=["Visual Encoder"],
            )
            self.assertFalse(report["passed"])
            self.assertIn("cover too little", " ".join(report["problems"]))
            self.assertNotIn("missing expected native text", " ".join(report["problems"]))
            self.assertEqual(len(report["pptx_sha256"]), 64)

    def test_figure_extractor_ignores_commented_redefinitions_and_unrelated_inputs(self):
        module = load_module("tex_extractor_scope", SCRIPTS / "extract_tex_figure.py")
        with scratch_dir("tex-scope") as tmp:
            tmp = Path(tmp)
            (tmp / "appendix.tex").write_text(r"\includegraphics{missing.pdf}", encoding="utf-8")
            source = tmp / "paper.tex"
            source.write_text(
                r"% \newcommand{\mathbf}{\boldsymbol}" "\n"
                r"\DeclareMathOperator{\dt}{\,\mathrm{d}t}" "\n"
                r"\begin{document}\begin{figure}\begin{tikzpicture}"
                r"\node {$\dt$};\end{tikzpicture}\label{fig:target}\end{figure}"
                r"\input{appendix.tex}\end{document}",
                encoding="utf-8",
            )
            snippet, report = module.extract(
                source.read_text(encoding="utf-8"), "fig:target", 1, source=source
            )
            self.assertNotIn(r"\newcommand{\mathbf}", snippet)
            self.assertIn(r"\DeclareMathOperator{\dt}", snippet)
            self.assertEqual(report["input_dependencies"], [])

    def test_prompt_builder_preserves_topology_and_labels(self):
        module = load_module("prompt_builder", SCRIPTS / "build_imagegen_prompt.py")
        data = json.loads((ROOT / "examples" / "multimodal-method.json").read_text(encoding="utf-8"))
        prompt = module.build_prompt(data)
        self.assertIn("from=visual_encoder; to=cross_attention", prompt)
        self.assertIn('"Cross-Modal Attention"', prompt)
        self.assertIn("do not reverse or invent arrows", prompt)

    def test_init_run_creates_isolated_contract(self):
        with scratch_dir("init-run") as tmp:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "init_figure_run.py"), "--text", "A -> B", "--out-root", str(tmp), "--name", "demo"],
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
        with scratch_dir("final-validation") as tmp:
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
        with scratch_dir("short-label") as tmp:
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
        with scratch_dir("builtin-import") as tmp:
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
