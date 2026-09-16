#!/usr/bin/env python3
"""Create an isolated research-figure-drawer run directory."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return value[:48] or "research-figure"


def skeleton(figure_id: str) -> dict:
    return {
        "schema_version": 1,
        "figure_id": figure_id,
        "figure_type": "architecture",
        "title": "",
        "venue_profile": "cvpr",
        "canvas": {
            "aspect_ratio": "16:9",
            "orientation": "landscape",
            "reading_direction": "left-to-right",
        },
        "scientific_message": "",
        "groups": [],
        "modules": [],
        "edges": [],
        "formulas": [],
        "exact_text": [],
        "style": {
            "tone": "clean publication-ready vector diagram",
            "palette": ["#4457A6", "#5CA8A8", "#E6B566", "#F5F6F8"],
            "background": "white",
            "line_style": "clean orthogonal connectors",
            "typography": "sans-serif, concise labels",
            "density": "moderate",
        },
        "forbidden": ["invented modules", "decorative arrows without semantics"],
        "assumptions": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--request-file", help="File containing TeX/TikZ or a research description")
    source.add_argument("--text", help="Inline research description")
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--name", default="research-figure")
    args = parser.parse_args()

    content = Path(args.request_file).read_text(encoding="utf-8") if args.request_file else args.text
    name = slugify(args.name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out_root).expanduser().resolve() / f"{stamp}-{name}"
    if run_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing run: {run_dir}")
    for relative in ("reference", "editable", "final"):
        (run_dir / relative).mkdir(parents=True, exist_ok=False)

    (run_dir / "request.md").write_text(content.rstrip() + "\n", encoding="utf-8")
    (run_dir / "figure_spec.json").write_text(
        json.dumps(skeleton(name), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    state = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "status": "initialized",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifacts": {
            "request": "request.md",
            "figure_spec": "figure_spec.json",
            "image_prompt": "imagegen-prompt.md",
            "reference": "reference/reference.png",
            "final_dir": "final",
        },
    }
    (run_dir / "figure_run.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
