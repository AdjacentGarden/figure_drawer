#!/usr/bin/env python3
"""Build a topology-aware GPT Image prompt from figure_spec.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_KEYS = {
    "schema_version",
    "figure_id",
    "figure_type",
    "canvas",
    "scientific_message",
    "groups",
    "modules",
    "edges",
    "formulas",
    "exact_text",
    "style",
    "forbidden",
    "assumptions",
}


def validate(spec: dict) -> None:
    missing = sorted(REQUIRED_KEYS - set(spec))
    if missing:
        raise ValueError(f"Missing required figure spec keys: {', '.join(missing)}")
    if spec.get("schema_version") != 1:
        raise ValueError("Only figure spec schema_version 1 is supported")
    modules = spec.get("modules") or []
    groups = spec.get("groups") or []
    ids = [str(item.get("id", "")) for item in [*groups, *modules]]
    if any(not item for item in ids):
        raise ValueError("Every module and group requires a non-empty id")
    if len(ids) != len(set(ids)):
        raise ValueError("Module and group ids must be unique")
    endpoints = set(ids)
    edge_ids: set[str] = set()
    for edge in spec.get("edges") or []:
        edge_id = str(edge.get("id", ""))
        if not edge_id or edge_id in edge_ids:
            raise ValueError("Every edge requires a unique non-empty id")
        edge_ids.add(edge_id)
        for key in ("from", "to"):
            if edge.get(key) not in endpoints:
                raise ValueError(f"Edge {edge_id} has unknown {key} endpoint: {edge.get(key)}")
    if not str(spec.get("scientific_message", "")).strip():
        raise ValueError("scientific_message must be completed before image generation")


def lines_for_items(items: list[dict], fields: tuple[str, ...]) -> list[str]:
    result = []
    for item in items:
        parts = [f"{field}={item.get(field, '')}" for field in fields if item.get(field, "") != ""]
        result.append("- " + "; ".join(parts))
    return result or ["- none"]


def build_prompt(spec: dict) -> str:
    validate(spec)
    canvas = spec["canvas"]
    style = spec["style"]
    exact = [str(value) for value in spec.get("exact_text", [])]
    palette = ", ".join(style.get("palette", [])) or "restrained academic palette"
    forbidden = [str(value) for value in spec.get("forbidden", [])]

    sections = [
        "Create one publication-ready scientific figure, not a presentation slide mockup.",
        "",
        "SCIENTIFIC PURPOSE",
        str(spec["scientific_message"]),
        "",
        "CANVAS AND READING ORDER",
        f"- aspect ratio: {canvas.get('aspect_ratio', '16:9')}",
        f"- orientation: {canvas.get('orientation', 'landscape')}",
        f"- reading direction: {canvas.get('reading_direction', 'left-to-right')}",
        f"- figure type: {spec.get('figure_type')}",
        "",
        "GROUPS",
        *lines_for_items(spec.get("groups", []), ("id", "label", "description")),
        "",
        "MODULES — preserve every module exactly once unless the description explicitly says repeated",
        *lines_for_items(spec.get("modules", []), ("id", "label", "kind", "group", "description", "visual_hint")),
        "",
        "EDGES — preserve endpoint, direction, branch structure, label, and semantic style",
        *lines_for_items(spec.get("edges", []), ("id", "from", "to", "direction", "style", "label", "meaning")),
        "",
        "FORMULAS",
        *lines_for_items(spec.get("formulas", []), ("id", "latex", "placement")),
        "",
        "EXACT VISIBLE LABELS",
        *(f'- "{value}"' for value in exact),
        "Do not paraphrase, translate, duplicate, or invent visible labels. Keep labels short, horizontal, and readable.",
        "",
        "VISUAL SYSTEM",
        f"- tone: {style.get('tone', 'clean publication-ready vector diagram')}",
        f"- palette: {palette}",
        f"- background: {style.get('background', 'white')}",
        f"- connectors: {style.get('line_style', 'clean orthogonal connectors')}",
        f"- typography: {style.get('typography', 'sans-serif, concise labels')}",
        f"- density: {style.get('density', 'moderate')}",
        "- use meaningful visual grammar: tensor stacks, sequences, grids, operator nodes, modality icons, or stage containers only where scientifically appropriate",
        "- create clear hierarchy, consistent alignment, generous padding, and compact whitespace",
        "- attach arrows precisely to object boundaries; avoid crossings, loose line fragments, unexplained arrowheads, and lines through text",
        "- use low-saturation fills, dark readable strokes, minimal shadow, and grayscale-safe distinctions",
        "- no UI chrome, browser frame, slide title bar, watermark, pseudo-code, decorative statistics, or poster styling",
        "",
        "HARD CONSTRAINTS",
        "- do not add, remove, merge, split, or rename scientific modules",
        "- do not reverse or invent arrows",
        "- do not invent equations, datasets, metrics, results, legends, or claims",
        "- prioritize correct topology and reconstruction-friendly separation over ornamental detail",
        *(f"- forbidden: {value}" for value in forbidden),
    ]
    title = str(spec.get("title", "")).strip()
    if title:
        sections.extend(["", f'OPTIONAL FIGURE HEADING: "{title}"'])
    return "\n".join(sections).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_prompt(spec), encoding="utf-8")
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
