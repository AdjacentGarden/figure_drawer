#!/usr/bin/env python3
"""Check the runtime required by research-figure-drawer.

The skill is self-contained: the editppt reconstruction runtime is vendored at
``<skill-root>/cli`` and pinned by ``cli/VENDOR.json``. This check reports whether the
bundled runtime is present and runnable, whether its Python dependencies are importable,
and whether every vendored file still matches its recorded hash.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_CLI = SKILL_ROOT / "cli"
VENDOR_MANIFEST = BUNDLED_CLI / "VENDOR.json"
LAUNCHER = SKILL_ROOT / "scripts" / "run_editppt.py"

# Runtime dependencies declared by the bundled cli/pyproject.toml.
PYTHON_DEPENDENCIES = {
    "PyMuPDF": "fitz",
    "Pillow": "PIL",
    "openai": "openai",
    "PyYAML": "yaml",
    "numpy": "numpy",
    "requests": "requests",
}

UPSTREAM_REPOSITORY = "https://github.com/ningzimu/image-to-editable-ppt-skill"


def sha256_lf(path: Path) -> str:
    """Hash UTF-8 content with normalised line endings, matching git storage."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_vendor_manifest() -> dict:
    """Verify every vendored file against the hashes recorded in cli/VENDOR.json."""
    if not VENDOR_MANIFEST.is_file():
        return {"ok": False, "checked": 0, "problems": [f"missing vendor manifest: {VENDOR_MANIFEST}"]}
    try:
        manifest = json.loads(VENDOR_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "checked": 0, "problems": [f"unreadable vendor manifest: {exc}"]}

    problems: list[str] = []
    files = manifest.get("files") or {}
    for relative, expected in sorted(files.items()):
        path = SKILL_ROOT / relative
        if not path.is_file():
            problems.append(f"missing vendored file: {relative}")
            continue
        actual = sha256_lf(path)
        if actual != expected:
            problems.append(f"vendored file changed since it was recorded: {relative}")
    if manifest.get("file_count") != len(files):
        problems.append("vendor manifest file_count does not match its file list")
    return {
        "ok": not problems,
        "checked": len(files),
        "upstream_repository": manifest.get("upstream_repository"),
        "upstream_commit": manifest.get("upstream_commit"),
        "license": manifest.get("license"),
        "problems": problems,
    }


def resolve_runtime(explicit: str | None) -> list[str] | None:
    """Prefer an explicit path, then editppt on PATH, then the bundled launcher."""
    if explicit:
        return [explicit]
    executable = shutil.which("editppt")
    if executable:
        return [executable]
    if LAUNCHER.is_file():
        return [sys.executable, str(LAUNCHER)]
    return None


def run_command(command: list[str], args: list[str], timeout: int = 60) -> dict:
    try:
        result = subprocess.run(
            [*command, *args],
            text=True,
            capture_output=True,
            timeout=timeout,
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
    parser.add_argument("--editppt", help="Explicit path to an editppt executable to prefer")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when required components are missing")
    args = parser.parse_args()

    bundled = {
        "ok": (BUNDLED_CLI / "pyproject.toml").is_file() and (BUNDLED_CLI / "editppt" / "cli.py").is_file(),
        "path": str(BUNDLED_CLI),
        "package": str(BUNDLED_CLI / "editppt"),
    }
    vendor = verify_vendor_manifest()

    command = resolve_runtime(args.editppt)
    if command is None:
        editppt = {"ok": False, "command": None, "reason": "no editppt executable and no bundled launcher"}
    else:
        mode = "path" if len(command) == 1 else "bundled-launcher"
        editppt = {
            "command": command,
            "mode": mode,
            "help": run_command(command, ["--help"]),
            "doctor": run_command(command, ["doctor", "--json"]),
        }
        editppt["ok"] = bool(editppt["help"].get("ok"))

    missing = sorted(name for name, module in PYTHON_DEPENDENCIES.items() if importlib.util.find_spec(module) is None)
    dependencies = {
        "ok": not missing,
        "missing": missing,
        "declared_by": "cli/pyproject.toml",
        "install_hint": "python3 -m pip install -e <skill-root>/cli",
    }

    report = {
        "skill_root": str(SKILL_ROOT),
        "bundled_runtime": bundled,
        "vendored_files": vendor,
        "editppt": editppt,
        "python_dependencies": dependencies,
        "reference_image_backend": {
            "default": "builtin image_gen.imagegen",
            "api_key_required": False,
            "runtime_note": "The agent must verify that the built-in image generation tool is callable in the current GPT/Codex client.",
            "optional_exact_model_fallback": {
                "model": "gpt-image-2",
                "selection_method": "editppt image generate --model gpt-image-2",
                "authentication_note": "Codex OAuth or an OpenAI-compatible API credential may be required only for this optional path.",
            },
        },
    }
    report["ok"] = bool(bundled["ok"] and editppt["ok"] and vendor["ok"] and dependencies["ok"])
    if not report["ok"]:
        report["install_hint"] = (
            "Install the bundled runtime with `python3 -m pip install -e <skill-root>/cli` (or run "
            "`python3 scripts/run_editppt.py <command>` without installing), then verify with "
            f"`editppt doctor`. Vendored files come from {UPSTREAM_REPOSITORY}. See references/installation.md."
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
