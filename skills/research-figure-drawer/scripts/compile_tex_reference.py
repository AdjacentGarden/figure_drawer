#!/usr/bin/env python3
"""Compile deterministic TikZ/PGF TeX into a vector PDF and reference PNG.

Compilation uses Tectonic's untrusted mode.  Inputs that reference external images
or contain known file/system primitives are rejected; this command is for drawings
whose complete geometry is present in the TeX source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from classify_tex_source import classify


def standalone_document(text: str, column_width_pt: float | None = None) -> str:
    if re.search(r"\\documentclass(?:\s*\[[^]]*\])?\s*\{", text):
        return text
    marker = "% figure-drawer:body"
    preamble, body = (text.split(marker, 1) if marker in text else ("", text))
    libraries = "arrows.meta,positioning,calc,fit,backgrounds,shapes.geometric,matrix"
    return "\n".join(
        [
            r"\documentclass[tikz,border=2pt]{standalone}",
            r"\usepackage{amsmath,amssymb}",
            r"\usepackage{relsize}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{xcolor}",
            r"\usepackage{tikz}",
            rf"\usetikzlibrary{{{libraries}}}",
            r"\usepackage{pgfplots}",
            r"\pgfplotsset{compat=1.18}",
            preamble.strip(),
            rf"\setlength{{\columnwidth}}{{{column_width_pt}pt}}" if column_width_pt else "",
            r"\begin{document}",
            body.strip(),
            r"\end{document}",
            "",
        ]
    )


def run(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--column-width-pt", type=float,
        help="Bind \\columnwidth to the source venue's measured value instead of the standalone default.",
    )
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    classification = classify(text)
    if classification["mode"] != "deterministic-vector":
        raise SystemExit(
            "Refusing deterministic compilation: " + classification["reason"]
        )
    if classification["external_images"] or classification.get("external_dependencies"):
        raise SystemExit("Refusing compilation because the drawing still references external files.")

    tectonic = shutil.which("tectonic")
    renderer = shutil.which("pdftocairo") or shutil.which("pdftoppm")
    if not tectonic or not renderer:
        raise SystemExit("Required executables are missing: tectonic and pdftocairo/pdftoppm are required.")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="figure-tex-") as temporary:
        temp = Path(temporary)
        tex = temp / "figure.tex"
        tex.write_text(standalone_document(text, args.column_width_pt), encoding="utf-8")
        try:
            compiled = run(
                [tectonic, "--untrusted", "--keep-logs", "--outdir", str(temp), str(tex)],
                temp,
                args.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            details = "TeX compilation timed out. Partial output:\n" + str(exc.stdout or "") + "\n" + str(exc.stderr or "")
            (out_dir / "compile-error.log").write_text(details[-6000:], encoding="utf-8")
            raise SystemExit("TeX compilation timed out; see compile-error.log")
        if compiled.returncode != 0 or not (temp / "figure.pdf").is_file():
            log_tail = (compiled.stdout + "\n" + compiled.stderr)[-6000:]
            (out_dir / "compile-error.log").write_text(log_tail, encoding="utf-8")
            raise SystemExit("TeX compilation failed; see compile-error.log")
        pdf = out_dir / "reference.pdf"
        shutil.copy2(temp / "figure.pdf", pdf)

    png_prefix = out_dir / "reference"
    if Path(renderer).name == "pdftocairo":
        rendered = run([renderer, "-png", "-singlefile", "-r", str(args.dpi), str(pdf), str(png_prefix)], out_dir, args.timeout)
    else:
        rendered = run([renderer, "-png", "-singlefile", "-r", str(args.dpi), str(pdf), str(png_prefix)], out_dir, args.timeout)
    png = out_dir / "reference.png"
    if rendered.returncode != 0 or not png.is_file():
        raise SystemExit("PDF rasterization failed: " + (rendered.stderr or rendered.stdout)[-2000:])

    provenance = {
        "schema_version": 1,
        "backend": "deterministic-tex",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(source),
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "classification": classification,
        "compiler": "tectonic --untrusted",
        "renderer": Path(renderer).name,
        "dpi": args.dpi,
        "column_width_pt": args.column_width_pt,
        "artifacts": {"pdf": str(pdf), "png": str(png)},
    }
    record = out_dir / "reference-provenance.json"
    record.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
