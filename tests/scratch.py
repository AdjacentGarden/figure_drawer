"""Scratch directories for tests.

`tempfile.mkdtemp()` is unusable in some locked-down sandboxes (the created
directory cannot be written to). Set `FIGURE_DRAWER_TEST_SCRATCH` to a writable
directory to redirect test scratch space there; otherwise the usual temporary
directory is used.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def scratch_root() -> Path:
    override = os.environ.get("FIGURE_DRAWER_TEST_SCRATCH")
    if override:
        root = Path(override).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(tempfile.mkdtemp(prefix="figure-drawer-tests-"))


@contextmanager
def scratch_dir(name: str = "case") -> Iterator[Path]:
    """Yield a fresh writable directory; removal failures are ignored."""
    directory = scratch_root() / f"{name}-{uuid.uuid4().hex[:8]}"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)
