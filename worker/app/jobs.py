"""In-memory job registry.

v0 only — for production swap for Postgres/Redis. The interface (`get`, `put`,
`update`) is intentionally tiny so the swap is mechanical.
"""
from __future__ import annotations

import threading
from typing import Dict

from .models import Job


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def put(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            updated = job.model_copy(update=fields)
            self._jobs[job_id] = updated
            return updated
