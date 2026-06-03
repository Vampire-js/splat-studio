"""Pydantic models — mirror of web/src/lib/types.ts.

Keep these two files in sync. In a future iteration we'd generate one from the
other (e.g. via an OpenAPI schema) — for v0 we maintain by hand.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

JobStatus = Literal["queued", "processing", "done", "failed"]


class Job(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    progress: float = 0.0  # 0..1
    image_count: int = 0
    splat_url: Optional[str] = None  # worker-relative URL when done
    error: Optional[str] = None


class CreateJobResponse(BaseModel):
    id: str
