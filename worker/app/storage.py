"""Storage abstraction.

v0: local filesystem. The `Storage` Protocol is the seam we'll swap for an
S3-backed implementation later without touching call sites.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, Protocol


class Storage(Protocol):
    def job_dir(self, job_id: str) -> Path: ...
    def save_upload(self, job_id: str, filename: str, data: bytes) -> Path: ...
    def write_artifact(self, job_id: str, name: str, src_path: Path) -> Path: ...
    def artifact_path(self, job_id: str, name: str) -> Path: ...
    def list_uploads(self, job_id: str) -> Iterable[Path]: ...


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        p = self.root / job_id
        (p / "uploads").mkdir(parents=True, exist_ok=True)
        (p / "artifacts").mkdir(parents=True, exist_ok=True)
        return p

    def save_upload(self, job_id: str, filename: str, data: bytes) -> Path:
        # Defense in depth: strip path components from incoming filename.
        safe = os.path.basename(filename) or "upload.bin"
        dest = self.job_dir(job_id) / "uploads" / safe
        dest.write_bytes(data)
        return dest

    def write_artifact(self, job_id: str, name: str, src_path: Path) -> Path:
        safe = os.path.basename(name)
        dest = self.job_dir(job_id) / "artifacts" / safe
        shutil.copyfile(src_path, dest)
        return dest

    def artifact_path(self, job_id: str, name: str) -> Path:
        return self.job_dir(job_id) / "artifacts" / os.path.basename(name)

    def list_uploads(self, job_id: str) -> Iterable[Path]:
        return sorted((self.job_dir(job_id) / "uploads").iterdir())
