#!/usr/bin/env python3
"""Generate a scientific reference image through editppt with an explicit model."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size", default="1536x864")
    parser.add_argument("--quality", default="high", choices=["low", "medium", "high", "xhigh", "max", "auto"])
    parser.add_argument("--editppt", default="editppt")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if "gpt-image-" not in args.model:
        raise SystemExit("--model must be a GPT Image model id")
    executable = shutil.which(args.editppt) if Path(args.editppt).name == args.editppt else args.editppt
    if not executable:
        raise SystemExit(
            "editppt was not found. Install the bundled runtime "
            "(`python3 -m pip install -e <skill-root>/cli`) or pass --editppt "
            "`python3 scripts/run_editppt.py`."
        )
    prompt = Path(args.prompt).expanduser().resolve()
    if not prompt.is_file():
        raise SystemExit(f"Prompt file not found: {prompt}")
    output = Path(args.out).expanduser().resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing output without --force: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        str(executable), "image", "generate",
        "--prompt-file", str(prompt),
        "--out", str(output),
        "--model", args.model,
        "--size", args.size,
        "--quality", args.quality,
    ]
    if args.force:
        command.append("--force")
    if args.dry_run:
        command.append("--dry-run")
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
