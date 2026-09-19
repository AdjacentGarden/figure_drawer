#!/usr/bin/env python3
"""Verify that required editable equation OLE objects exist in a PPTX package."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pptx_path = Path(args.pptx).expanduser().resolve()
    spec_path = Path(args.spec).expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    required = {f"Equation {item['id']}" for item in spec.get("equations", [])}
    found = {}
    embedding_files = []
    with zipfile.ZipFile(pptx_path) as archive:
        embedding_files = [name for name in archive.namelist() if name.startswith("ppt/embeddings/")]
        for name in archive.namelist():
            if not re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                continue
            root = ET.fromstring(archive.read(name))
            for frame in root.iter():
                if frame.tag.rsplit("}", 1)[-1] != "graphicFrame":
                    continue
                non_visual = next(
                    (node for node in frame.iter() if node.tag.rsplit("}", 1)[-1] == "cNvPr"), None
                )
                ole_object = next(
                    (node for node in frame.iter() if node.tag.rsplit("}", 1)[-1] == "oleObj"), None
                )
                if non_visual is None or ole_object is None:
                    continue
                shape_name = non_visual.get("name", "")
                if shape_name in required:
                    found[shape_name] = {"slide_xml": name, "prog_id": ole_object.get("progId", "")}

    missing = sorted(required - set(found))
    wrong_prog_id = sorted(name for name, item in found.items() if not item["prog_id"].startswith("Word.Document"))
    report = {
        "passed": not missing and not wrong_prog_id and len(embedding_files) >= len(required),
        "pptx": str(pptx_path),
        "required_count": len(required),
        "found_count": len(found),
        "embedding_count": len(embedding_files),
        "missing": missing,
        "wrong_prog_id": wrong_prog_id,
        "objects": found,
    }
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
