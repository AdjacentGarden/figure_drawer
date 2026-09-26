#!/usr/bin/env python3
"""Validate scientific label coverage and dependency validation for a final PPTX."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def pptx_texts(path: Path) -> tuple[int, list[str]]:
    texts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        slides = sorted(
            name for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )
        for slide in slides:
            root = ET.fromstring(archive.read(slide))
            for text_body in root.findall(".//p:txBody", NS):
                paragraphs: list[str] = []
                for paragraph in text_body.findall("./a:p", NS):
                    value = "".join(node.text or "" for node in paragraph.findall(".//a:t", NS))
                    normalized = normalize_text(value)
                    if normalized:
                        paragraphs.append(normalized)
                        texts.append(normalized)
                combined = normalize_text(" ".join(paragraphs))
                if combined and combined not in texts:
                    texts.append(combined)
    return len(slides), texts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--editppt-validation", required=True)
    parser.add_argument("--quality-report")
    parser.add_argument("--render-comparison")
    parser.add_argument("--render-provenance")
    parser.add_argument("--editability-report")
    parser.add_argument("--strict-wps", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    spec_path = Path(args.spec).expanduser().resolve()
    pptx_path = Path(args.pptx).expanduser().resolve()
    dependency_path = Path(args.editppt_validation).expanduser().resolve()
    quality_path = Path(args.quality_report).expanduser().resolve() if args.quality_report else None
    comparison_path = Path(args.render_comparison).expanduser().resolve() if args.render_comparison else None
    provenance_path = Path(args.render_provenance).expanduser().resolve() if args.render_provenance else None
    editability_path = Path(args.editability_report).expanduser().resolve() if args.editability_report else None
    problems: list[str] = []
    if not spec_path.is_file():
        problems.append(f"missing figure spec: {spec_path}")
    if not pptx_path.is_file():
        problems.append(f"missing PPTX: {pptx_path}")
    if not dependency_path.is_file():
        problems.append(f"missing editppt validation: {dependency_path}")
    if quality_path and not quality_path.is_file():
        problems.append(f"missing quality audit: {quality_path}")
    if args.strict_wps and not comparison_path:
        problems.append("strict WPS validation requires --render-comparison")
    if args.strict_wps and not provenance_path:
        problems.append("strict WPS validation requires --render-provenance")
    if args.strict_wps and not editability_path:
        problems.append("strict WPS validation requires --editability-report")
    if comparison_path and not comparison_path.is_file():
        problems.append(f"missing render comparison: {comparison_path}")
    if provenance_path and not provenance_path.is_file():
        problems.append(f"missing render provenance: {provenance_path}")
    if editability_path and not editability_path.is_file():
        problems.append(f"missing editability report: {editability_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.is_file() else {}
    dependency = json.loads(dependency_path.read_text(encoding="utf-8")) if dependency_path.is_file() else {}
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path and quality_path.is_file() else {}
    comparison = json.loads(comparison_path.read_text(encoding="utf-8")) if comparison_path and comparison_path.is_file() else {}
    provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path and provenance_path.is_file() else {}
    editability = json.loads(editability_path.read_text(encoding="utf-8")) if editability_path and editability_path.is_file() else {}
    slide_count, visible_text = pptx_texts(pptx_path) if pptx_path.is_file() else (0, [])
    required = [normalize_text(str(value)) for value in spec.get("exact_text", []) if normalize_text(str(value))]
    missing_labels = [label for label in required if label not in visible_text]
    if dependency.get("passed") is not True:
        problems.append("editppt deck validation did not pass")
    if quality_path and quality.get("passed") is not True:
        problems.append("figure quality audit did not pass")
    if comparison_path and comparison.get("passed") is not True:
        problems.append("render comparison did not pass")
    if provenance_path and (
        provenance.get("passed") is not True or "WPS" not in str(provenance.get("renderer", ""))
    ):
        problems.append("render provenance does not certify a successful WPS Presentation export")
    if args.strict_wps and provenance.get("roundtrip_visual_stable") is not True:
        problems.append("WPS first-open and reopened exports are not pixel-identical")
    if editability_path and editability.get("passed") is not True:
        problems.append("object-level editability audit did not pass")
    if args.strict_wps and pptx_path.is_file() and provenance:
        source_hash = provenance.get("source_sha256")
        if source_hash != file_sha256(pptx_path):
            problems.append("WPS provenance source hash does not match the validated PPTX")
    if args.strict_wps and pptx_path.is_file() and editability:
        if editability.get("pptx_sha256") != file_sha256(pptx_path):
            problems.append("editability report hash does not match the validated PPTX")
    if args.strict_wps and comparison and provenance:
        if comparison.get("gate_mode") != "strict-identical":
            problems.append("render comparison was not run in strict-identical mode")
        rendered_hash = comparison.get("rendered_sha256")
        reopened_hashes = {
            str(item.get("sha256"))
            for item in (provenance.get("reopened_exports") or [])
            if isinstance(item, dict) and item.get("sha256")
        }
        if not rendered_hash or rendered_hash not in reopened_hashes:
            problems.append("render comparison image is not hash-bound to a WPS reopened export")
    if slide_count != 1:
        problems.append(f"expected one slide, found {slide_count}")
    if missing_labels:
        problems.append("missing required native text labels: " + ", ".join(missing_labels))

    report = {
        "schema_version": 1,
        "passed": not problems,
        "figure_spec": str(spec_path),
        "pptx": str(pptx_path),
        "editppt_validation": str(dependency_path),
        "quality_report": str(quality_path) if quality_path else None,
        "render_comparison": str(comparison_path) if comparison_path else None,
        "render_provenance": str(provenance_path) if provenance_path else None,
        "editability_report": str(editability_path) if editability_path else None,
        "dependency_passed": dependency.get("passed") is True,
        "quality_passed": quality.get("passed") is True if quality_path else None,
        "render_comparison_passed": comparison.get("passed") is True if comparison_path else None,
        "wps_render_passed": provenance.get("passed") is True if provenance_path else None,
        "editability_passed": editability.get("passed") is True if editability_path else None,
        "slide_count": slide_count,
        "required_label_count": len(required),
        "visible_text_count": len(visible_text),
        "missing_labels": missing_labels,
        "problems": problems,
        "claim_boundary": "Checks package readability, one-slide output, dependency validation, exact native-text coverage, WPS render provenance, and object-level editability. Visual topology still requires rendered comparison against figure_spec.json.",
    }
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
