from __future__ import annotations

import subprocess
from pathlib import Path

from .config import QPDF_BIN


class CleanError(Exception):
    pass


def clean_pdf(src: Path, dest: Path, password: str = "") -> None:
    cmd = [QPDF_BIN, "--decrypt", "--remove-restrictions", str(src), str(dest)]
    if password:
        cmd[1:1] = [f"--password={password}"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CleanError(
            f"qpdf not found ({QPDF_BIN}). Install qpdf >= 11 or set QPDF_BIN."
        ) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "qpdf failed").strip()
        raise CleanError(err)
