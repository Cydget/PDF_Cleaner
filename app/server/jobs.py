from __future__ import annotations

import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import config


@dataclass
class Job:
    id: str
    created: float
    dir: Path
    original: Path
    cleaned: Optional[Path] = None
    prepared: Optional[Path] = None
    signed: Optional[Path] = None
    status: str = "uploaded"
    error: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def create(self, filename: str, data: bytes) -> Job:
        self.purge_expired()
        job_id = uuid.uuid4().hex
        job_dir = config.DATA_DIR / job_id
        job_dir.mkdir(parents=True)
        dest = job_dir / "original.pdf"
        dest.write_bytes(data)
        job = Job(id=job_id, created=time.time(), dir=job_dir, original=dest)
        job.extra["filename"] = filename
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def purge_expired(self) -> None:
        now = time.time()
        dead: list[str] = []
        with self._lock:
            for jid, job in self._jobs.items():
                if now - job.created > config.JOB_TTL_SECONDS:
                    dead.append(jid)
            for jid in dead:
                job = self._jobs.pop(jid)
                shutil.rmtree(job.dir, ignore_errors=True)


store = JobStore()
