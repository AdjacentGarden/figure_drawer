#!/usr/bin/env python3
"""Inline SVG <use> references so PowerPoint can render path-based formula SVGs."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from xml.etree import ElementTree as ET


SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def join_transform(existing: str, x: str, y: str) -> str:
    translate = f"translate({x} {y})"
    return f"{translate} {existing}".strip() if existing else translate


def flatten(source: Path, output: Path) -> int:
    tree = ET.parse(source)
    root = tree.getroot()
    targets = {
        element.get("id"): element
        for element in root.iter()
        if element.get("id")
    }
    replacements = 0

    def visit(parent: ET.Element) -> None:
        nonlocal replacements
        for index, child in list(enumerate(list(parent))):
            if local_name(child.tag) != "use":
                visit(child)
                continue
            href = child.get(f"{{{XLINK}}}href") or child.get("href") or ""
            target = targets.get(href.lstrip("#"))
            if target is None:
                continue
            group = ET.Element(f"{{{SVG}}}g")
            group.set("transform", join_transform(child.get("transform", ""), child.get("x", "0"), child.get("y", "0")))
            if child.get("style"):
                group.set("style", child.get("style", ""))
            for target_child in list(target):
                group.append(copy.deepcopy(target_child))
            parent.remove(child)
            parent.insert(index, group)
            replacements += 1

    visit(root)
    for parent in root.iter():
        for child in list(parent):
            if local_name(child.tag) == "defs":
                parent.remove(child)
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return replacements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    count = flatten(source, output)
    if count == 0:
        raise SystemExit("No SVG <use> references were found; refusing to claim a flattened output.")
    print(f"{output}\tuses_inlined={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
