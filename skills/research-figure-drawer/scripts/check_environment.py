#!/usr/bin/env python3
"""Check the runtime required by research-figure-drawer."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


DEPENDENCY_REPO = "https://github.com/ningzimu/image-to-editable-ppt-skill"


def dependency_candidates(explicit: str | None) -> list[Path]:
    values: list[Path] = []
    if explicit:
        values.append(Path(explicit).expanduser())
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    values.extend(
        [
            codex_home / "skills" / "image-to-editable-ppt",
            Path.home() / ".codex" / "skills" / "image-to-editable-ppt",
        ]
    )
    unique: list[Path] = []
    for value in values:
        resolved = value.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def run_doctor(executable: str) -> dict:
    try:
        result = subprocess.run(
            [executable, "doctor", "--json"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - platform-specific errors
        return {"ok": False, "error": str(exc)}
    payload: dict = {"ok": result.returncode == 0, "returncode": result.returncode}
    if result.stdout.strip():
        try:
            payload["details"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload["stdout"] = result.stdout[-2000:]
    if result.stderr.strip():
        payload["stderr"] = result.stderr[-2000:]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-skill", help="Explicit image-to-editable-ppt skill directory")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when required components are missing")
    args = parser.parse_args()

    candidates = dependency_candidates(args.dependency_skill)
    dependency = next((p for p in candidates if (p / "SKILL.md").is_file()), None)
    editppt = shutil.which("editppt")
    report = {
        "dependency_skill": {
            "ok": dependency is not None,
            "path": str(dependency) if dependency else None,
            "searched": [str(p) for p in candidates],
            "repository": DEPENDENCY_REPO,
        },
        "editppt": {
            "ok": editppt is not None,
            "path": editppt,
            "doctor": run_doctor(editppt) if editppt else None,
        },
        "exact_image_model": {
            "model": "gpt-image-2",
            "selection_method": "editppt image generate --model gpt-image-2",
            "authentication_note": "Codex OAuth or an OpenAI-compatible API credential is required at generation time.",
        },
    }
    report["ok"] = bool(dependency and editppt)
    if not report["ok"]:
        report["install_hint"] = (
            "Install both skills, install the dependency CLI, restart the client, then run editppt doctor. "
            "See references/installation.md."
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
