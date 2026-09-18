#!/usr/bin/env python3
"""Validate scientific label coverage and dependency validation for a final PPTX."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


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
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    spec_path = Path(args.spec).expanduser().resolve()
    pptx_path = Path(args.pptx).expanduser().resolve()
    dependency_path = Path(args.editppt_validation).expanduser().resolve()
    quality_path = Path(args.quality_report).expanduser().resolve() if args.quality_report else None
    problems: list[str] = []
    if not spec_path.is_file():
        problems.append(f"missing figure spec: {spec_path}")
    if not pptx_path.is_file():
        problems.append(f"missing PPTX: {pptx_path}")
    if not dependency_path.is_file():
        problems.append(f"missing editppt validation: {dependency_path}")
    if quality_path and not quality_path.is_file():
        problems.append(f"missing quality audit: {quality_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.is_file() else {}
    dependency = json.loads(dependency_path.read_text(encoding="utf-8")) if dependency_path.is_file() else {}
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path and quality_path.is_file() else {}
    slide_count, visible_text = pptx_texts(pptx_path) if pptx_path.is_file() else (0, [])
    required = [normalize_text(str(value)) for value in spec.get("exact_text", []) if normalize_text(str(value))]
    missing_labels = [label for label in required if label not in visible_text]
    if dependency.get("passed") is not True:
        problems.append("editppt deck validation did not pass")
    if quality_path and quality.get("passed") is not True:
        problems.append("figure quality audit did not pass")
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
        "dependency_passed": dependency.get("passed") is True,
        "quality_passed": quality.get("passed") is True if quality_path else None,
        "slide_count": slide_count,
        "required_label_count": len(required),
        "visible_text_count": len(visible_text),
        "missing_labels": missing_labels,
        "problems": problems,
        "claim_boundary": "Checks package readability, one-slide output, dependency validation, and exact native-text coverage. Visual topology still requires rendered comparison against figure_spec.json.",
    }
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
