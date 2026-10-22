"""File IO with fixed encoding and newlines, so output is byte-identical on every OS."""

import os
import tempfile
from pathlib import Path


def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text(path: Path, text: str) -> None:
    """Write utf-8 with LF newlines via a temp file and rename, so a crash never leaves a half file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def append_line(path: Path, line: str) -> None:
    """Append one line to a text file (read, add, atomic rewrite), keeping utf-8 and LF."""
    path = Path(path)
    existing = read_text(path) if path.exists() else ""
    write_text(path, existing + line + "\n")
