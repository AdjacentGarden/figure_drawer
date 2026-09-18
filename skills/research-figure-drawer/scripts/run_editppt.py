#!/usr/bin/env python3
"""Run the bundled editppt runtime without installing it.

Usage: python3 scripts/run_editppt.py <editppt arguments...>

This adds ``<skill-root>/cli`` to sys.path and forwards to the bundled package entry
point, so the skill works straight from a checkout. Installing the bundled package
(``python3 -m pip install -e <skill-root>/cli``) gives you the same runtime as an
``editppt`` command instead.
"""

from __future__ import annotations

import sys
from pathlib import Path


CLI_ROOT = Path(__file__).resolve().parent.parent / "cli"


def main() -> int:
    if not (CLI_ROOT / "editppt" / "cli.py").is_file():
        print(f"Bundled editppt runtime not found at {CLI_ROOT}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(CLI_ROOT))
    sys.argv[0] = "editppt"  # programme name shown in the forwarded CLI's help/errors
    from editppt.cli import main as editppt_main  # noqa: PLC0415 - path must be set first

    return editppt_main()


if __name__ == "__main__":
    raise SystemExit(main())
