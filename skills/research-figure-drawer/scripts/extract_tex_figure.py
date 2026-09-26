#!/usr/bin/env python3
r"""Extract one TikZ/PGF figure from a larger paper without unrelated assets.

This is intentionally a lexical extractor, not a TeX executor.  It selects a
``figure``/``figure*`` by label (or index), resolves local TeX inputs, preserves
safe wrappers around every TikZ environment, copies drawing declarations, and
records a hash-bound extraction report.  The result must still pass
``classify_tex_source.py`` before it is compiled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from classify_tex_source import classify, visible_tex


FIGURE_RE = re.compile(r"\\begin\s*\{figure\*?\}.*?\\end\s*\{figure\*?\}", re.S)
LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
PACKAGE_RE = re.compile(r"\\usepackage(?:\[[^]]*\])?\s*\{([^}]+)\}")


def _balanced_group(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 0
    for position in range(start, len(text)):
        char = text[position]
        if char == opening and (position == 0 or text[position - 1] != "\\"):
            depth += 1
        elif char == closing and (position == 0 or text[position - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return position + 1
    return None


def balanced_command(text: str, start: int) -> str | None:
    """Return a command with optional ``[]`` and consecutive ``{}`` arguments."""
    command = re.match(r"\\[A-Za-z@]+\*?", text[start:])
    if not command:
        return None
    position = start + command.end()
    saw_argument = False
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text) or text[position] not in "[{":
            break
        opening = text[position]
        closing = "]" if opening == "[" else "}"
        end = _balanced_group(text, position, opening, closing)
        if end is None:
            return None
        saw_argument = True
        position = end
    return text[start:position].rstrip() if saw_argument else None


def drawing_declarations(text: str, *, preamble_only: bool = True) -> list[str]:
    # Strip comments before looking for declarations.  Commented-out macro
    # experiments are common in paper sources and must never become live code
    # in the extracted figure.
    clean = visible_tex(text)
    preamble = clean.split(r"\begin{document}", 1)[0] if preamble_only else clean
    declarations: list[str] = []
    starters = re.compile(
        r"\\(?:definecolor|colorlet|tikzset|pgfplotsset|usetikzlibrary|usepgfplotslibrary|"
        r"newcommand|renewcommand|providecommand|DeclareRobustCommand|DeclareMathOperator)\b"
    )
    def brace_depth(position: int) -> int:
        depth = 0
        for index, char in enumerate(preamble[:position]):
            if char == "{" and (index == 0 or preamble[index - 1] != "\\"):
                depth += 1
            elif char == "}" and (index == 0 or preamble[index - 1] != "\\"):
                depth = max(0, depth - 1)
        return depth

    for match in starters.finditer(preamble):
        if brace_depth(match.start()) != 0:
            continue
        command = balanced_command(preamble, match.start())
        if command and command not in declarations:
            declarations.append(command)
    # Simple \def forms are line-oriented in the paper sources used here.
    offset = 0
    for line in preamble.splitlines(keepends=True):
        if brace_depth(offset) == 0 and re.match(r"\s*\\def\\[A-Za-z@]+", line) and line.strip() not in declarations:
            declarations.append(line.strip())
        offset += len(line)
    return declarations


def _safe_local_path(base: Path, root: Path, raw: str, suffix: str) -> Path:
    candidate = (base / raw).with_suffix(suffix) if not Path(raw).suffix else base / raw
    candidate = candidate.resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"TeX dependency escapes source root: {raw}")
    return candidate


def inline_local_inputs(text: str, *, source: Path, root: Path, seen: set[Path] | None = None) -> tuple[str, list[str]]:
    seen = set() if seen is None else seen
    dependencies: list[str] = []

    def replace(match: re.Match[str]) -> str:
        path = _safe_local_path(source.parent, root, match.group(1), ".tex")
        if not path.exists() or path in seen:
            return match.group(0)
        seen.add(path)
        nested, nested_dependencies = inline_local_inputs(
            path.read_text(encoding="utf-8"), source=path, root=root, seen=seen
        )
        dependencies.append(str(path))
        dependencies.extend(nested_dependencies)
        return nested

    return INPUT_RE.sub(replace, text), dependencies


def local_style_declarations(text: str, *, source: Path, root: Path) -> tuple[list[str], list[str], list[str]]:
    declarations: list[str] = []
    dependencies: list[str] = []
    font_context: list[str] = []
    preamble = text.split(r"\begin{document}", 1)[0]
    for match in PACKAGE_RE.finditer(preamble):
        for package in (item.strip() for item in match.group(1).split(",")):
            try:
                path = _safe_local_path(source.parent, root, package, ".sty")
            except ValueError:
                continue
            if not path.exists():
                continue
            dependencies.append(str(path))
            style_text = path.read_text(encoding="utf-8")
            for declaration in drawing_declarations(style_text, preamble_only=False):
                if declaration not in declarations:
                    declarations.append(declaration)
                if declaration_key(declaration) in {
                    r"macro:\rmdefault", r"macro:\sfdefault", r"macro:\footnotesize"
                } and declaration not in font_context:
                    font_context.append(declaration)
    return declarations, dependencies, font_context


def declaration_key(declaration: str) -> str:
    macro = re.match(
        r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand|DeclareMathOperator\*?)"
        r"\s*\{?(\\[A-Za-z@]+)", declaration
    )
    if macro:
        return "macro:" + macro.group(1)
    colour = re.match(r"\\(?:definecolor|colorlet)\s*\{([^}]+)\}", declaration)
    if colour:
        return "colour:" + colour.group(1)
    tikz = re.match(r"\\tikzset\s*\{\s*([^=,}]+)", declaration)
    if tikz:
        return "tikz:" + tikz.group(1).strip()
    return declaration


def declaration_needed(declaration: str, visual_body: str) -> bool:
    key = declaration_key(declaration)
    if key.startswith("macro:"):
        # Built-in formatting/math commands already supplied by the standalone
        # wrapper must not be redeclared from venue style files.
        if key.removeprefix("macro:") in {
            r"\mathbf", r"\mathrm", r"\mathit", r"\footnotesize",
            r"\small", r"\scriptsize", r"\tiny", r"\normalsize",
        }:
            return False
        return key.removeprefix("macro:") in visual_body
    if key.startswith("colour:"):
        return bool(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(key.removeprefix('colour:'))}(?![A-Za-z0-9_-])", visual_body))
    if key.startswith("tikz:"):
        setting = key.removeprefix("tikz:")
        if setting.startswith("external/"):
            return False
        if setting.startswith("every picture"):
            return False
        if setting.startswith("every node"):
            return True
        style_name = setting.split("/.", 1)[0].strip()
        return bool(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(style_name)}(?![A-Za-z0-9_-])", visual_body))
    return declaration.lstrip().startswith((r"\pgfplotsset", r"\usetikzlibrary", r"\usepgfplotslibrary"))


def dependency_records(paths: list[str]) -> list[dict[str, str]]:
    records = []
    for raw in dict.fromkeys(paths):
        path = Path(raw)
        records.append({
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return records


def extract(text: str, label: str | None, index: int, *, source: Path | None = None) -> tuple[str, dict]:
    input_dependencies: list[str] = []
    style_dependencies: list[str] = []
    style_declarations: list[str] = []
    font_context: list[str] = []
    if source is not None:
        root = source.parent.resolve()
        style_declarations, style_dependencies, font_context = local_style_declarations(
            text, source=source, root=root
        )
    searchable = visible_tex(text)
    figures = list(FIGURE_RE.finditer(searchable))
    candidates: list[tuple[str | None, str, list[str]]] = []
    for match in figures:
        body = match.group(0)
        expanded_body = body
        candidate_dependencies: list[str] = []
        if source is not None and INPUT_RE.search(body):
            expanded_body, candidate_dependencies = inline_local_inputs(
                body, source=source, root=source.parent.resolve()
            )
        if r"\begin{tikzpicture}" in expanded_body:
            label_match = LABEL_RE.search(body)
            # Keep the complete visual body so resizebox, local tikzset, and
            # multiple subfigures remain faithful.  Captions and labels are not
            # part of the rendered figure canvas.
            visual_body = re.split(r"\\caption\s*\{", expanded_body, maxsplit=1)[0]
            visual_body = re.sub(r"^\\begin\s*\{figure\*?\}(?:\[[^]]*\])?", "", visual_body)
            visual_body = re.sub(r"\\(?:centering|vspace|vskip)\b(?:\s*\{[^}]*\}|\s*[-+]?\d+(?:\.\d+)?(?:pt|in|cm|mm|ex|em))?", "", visual_body)
            candidates.append((label_match.group(1) if label_match else None, visual_body.strip(), candidate_dependencies))
    if label:
        selected = next((item for item in candidates if item[0] == label), None)
        if selected is None:
            raise ValueError(f"No TikZ figure has label {label!r}")
    else:
        if index < 1 or index > len(candidates):
            raise ValueError(f"Figure index {index} is outside 1..{len(candidates)}")
        selected = candidates[index - 1]

    visual_body = selected[1]
    input_dependencies = selected[2]

    raw_declarations = [*drawing_declarations(text), *style_declarations]
    for declaration in drawing_declarations(visual_body, preamble_only=False):
        raw_declarations.append(declaration)
    # Keep only declarations referenced by the visual plus global TikZ/PGF
    # configuration.  When a style file contains conditional duplicate macro
    # definitions, the last relevant definition wins instead of emitting an
    # uncompilable sequence of \newcommand declarations.
    by_key: dict[str, str] = {}
    for declaration in raw_declarations:
        if declaration_needed(declaration, visual_body):
            by_key[declaration_key(declaration)] = declaration
    declarations = list(by_key.values())
    wrapped_font_context = []
    if font_context:
        wrapped_font_context = [
            "\\makeatletter\n" + "\n".join(font_context) + "\n\\makeatother"
        ]
    snippet = "\n\n".join([*wrapped_font_context, *declarations, "% figure-drawer:body", visual_body]) + "\n"
    report = {
        "schema_version": 1,
        "selected_label": selected[0],
        "selected_index": candidates.index(selected) + 1,
        "candidate_count": len(candidates),
        "preamble_declaration_count": len(declarations),
        "font_context": font_context,
        "input_dependencies": dependency_records(input_dependencies),
        "style_dependencies": dependency_records(style_dependencies),
        "classification": classify(snippet),
    }
    return snippet, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    choose = parser.add_mutually_exclusive_group()
    choose.add_argument("--label")
    choose.add_argument("--index", type=int, default=1)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    snippet, report = extract(text, args.label, args.index, source=source)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(snippet, encoding="utf-8")
    report.update(
        {
            "source": str(source),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "output": str(output),
            "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        }
    )
    report_path = Path(args.report).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["classification"]["deterministic_render_available"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
