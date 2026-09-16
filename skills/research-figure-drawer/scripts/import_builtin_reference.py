#!/usr/bin/env python3
"""Import a local image returned by the client image tool and record provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Explicit local path returned by image_gen.imagegen")
    parser.add_argument("--out", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    output = Path(args.out).expanduser().resolve()
    record = Path(args.record).expanduser().resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise SystemExit(f"Built-in image output is missing or empty: {source}")
    if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise SystemExit(f"Unsupported built-in image output type: {source.suffix}")
    if (output.exists() or record.exists()) and not args.force:
        raise SystemExit("Refusing to overwrite the imported reference or provenance record without --force")
    output.parent.mkdir(parents=True, exist_ok=True)
    record.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    payload = {
        "schema_version": 1,
        "backend": "builtin-imagegen",
        "tool_name": "image_gen.imagegen",
        "model_id": None,
        "model_selection_note": "The client tool does not expose a model selector; no exact model ID is claimed.",
        "source_path": str(source),
        "imported_path": str(output),
        "sha256": sha256_file(output),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
