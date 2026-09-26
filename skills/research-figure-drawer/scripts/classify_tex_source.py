#!/usr/bin/env python3
r"""Classify whether TeX contains enough visual geometry for deterministic rendering.

The classifier deliberately distinguishes authored drawing code from prose and from
``\includegraphics`` placeholders.  It never executes the input.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DRAWING_MARKERS = {
    "tikzpicture": re.compile(r"\\begin\s*\{tikzpicture\}"),
    "pgfpicture": re.compile(r"\\begin\s*\{pgfpicture\}"),
    "pspicture": re.compile(r"\\begin\s*\{pspicture\}"),
}
PLOT_MARKER = re.compile(r"\\begin\s*\{axis\}")
EXTERNAL_IMAGE = re.compile(r"\\includegraphics(?:\s*\[[^]]*\])?\s*\{([^}]+)\}")
EXTERNAL_DEPENDENCIES = {
    "input": re.compile(r"\\(?:input|include)\s*\{([^}]+)\}"),
    "includesvg": re.compile(r"\\includesvg(?:\s*\[[^]]*\])?\s*\{([^}]+)\}"),
    "includepdf": re.compile(r"\\includepdf(?:\s*\[[^]]*\])?\s*\{([^}]+)\}"),
    "pgfplot-table": re.compile(r"\\(?:addplot\s+table|pgfplotstableread)\b"),
}
UNSAFE = {
    "shell_escape": re.compile(r"\\(?:write18|immediate\s*\\write18)\b", re.I),
    "pipe_input": re.compile(r"\\(?:input|include)\s*\{?\s*\|", re.I),
    "openout": re.compile(r"\\openout\b", re.I),
    "read": re.compile(r"\\read\b", re.I),
}


def visible_tex(text: str) -> str:
    """Remove comments and literal environments before evidence detection."""
    for environment in ("verbatim", "Verbatim", "lstlisting", "minted", "comment"):
        text = re.sub(
            rf"\\begin\s*\{{{environment}\}}.*?\\end\s*\{{{environment}\}}",
            "",
            text,
            flags=re.S,
        )
    lines = []
    for line in text.splitlines():
        lines.append(re.split(r"(?<!\\)%", line, maxsplit=1)[0])
    return "\n".join(lines)


def classify(text: str) -> dict:
    text = visible_tex(text)
    drawing = [name for name, pattern in DRAWING_MARKERS.items() if pattern.search(text)]
    if PLOT_MARKER.search(text):
        drawing.append("pgfplots-axis")
    images = [match.group(1).strip() for match in EXTERNAL_IMAGE.finditer(text)]
    dependencies: list[dict] = []
    for kind, pattern in EXTERNAL_DEPENDENCIES.items():
        for match in pattern.finditer(text):
            dependencies.append({"kind": kind, "target": match.group(1).strip() if match.groups() else None})
    unsafe = [name for name, pattern in UNSAFE.items() if pattern.search(text)]

    if unsafe:
        mode = "unsafe-tex"
        deterministic = False
        reason = "TeX contains commands that must not be executed."
    elif drawing and not images and not dependencies:
        mode = "deterministic-vector"
        deterministic = True
        reason = "TeX contains explicit vector drawing geometry."
    elif images or dependencies:
        mode = "external-image-placeholder"
        deterministic = False
        reason = "The visual program depends on external files or tables and is not self-contained."
    else:
        mode = "semantic-description"
        deterministic = False
        reason = "The input contains scientific text but no explicit visual geometry."

    return {
        "schema_version": 1,
        "mode": mode,
        "deterministic_render_available": deterministic,
        "drawing_markers": drawing,
        "external_images": images,
        "external_dependencies": dependencies,
        "unsafe_markers": unsafe,
        "reason": reason,
        "claim_boundary": (
            "Only deterministic-vector input can reproduce an unseen published figure from TeX alone. "
            "An external-image placeholder or prose description is insufficient to infer unique layout, "
            "colour, typography, or icon pixels."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    source = Path(args.input).expanduser().resolve()
    report = classify(source.read_text(encoding="utf-8"))
    report["input"] = str(source)
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["mode"] == "unsafe-tex" else 0


if __name__ == "__main__":
    raise SystemExit(main())
