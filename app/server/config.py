from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("PDFCLEANER_DATA", ROOT / "data"))
QPDF_BIN = os.environ.get("QPDF_BIN", "qpdf")
MAX_UPLOAD_BYTES = int(os.environ.get("PDFCLEANER_MAX_UPLOAD", str(50 * 1024 * 1024)))
JOB_TTL_SECONDS = int(os.environ.get("PDFCLEANER_JOB_TTL", "3600"))
HOST = os.environ.get("PDFCLEANER_HOST", "127.0.0.1")
PORT = int(os.environ.get("PDFCLEANER_PORT", "8080"))
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("PDFCLEANER_CORS", "http://127.0.0.1:8080,http://localhost:8080").split(",")
    if o.strip()
]
