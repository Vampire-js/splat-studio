"""FastAPI worker — accepts uploads, runs the (stubbed) pipeline, serves splats."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .jobs import JobStore
from .models import CreateJobResponse, Job
from .pipeline import run_pipeline
from .storage import LocalStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "./_storage")
# Resolve the sample path relative to the worker package by default so it works
# regardless of CWD (uvicorn --app-dir, systemd, docker, etc.).
_WORKER_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SAMPLE = _WORKER_ROOT / "samples" / "sample.splat"
SAMPLE_SPLAT_PATH = Path(os.environ.get("SAMPLE_SPLAT_PATH", str(_DEFAULT_SAMPLE))).resolve()
STUB_PROCESSING_SECONDS = float(os.environ.get("STUB_PROCESSING_SECONDS", "4"))

app = FastAPI(title="Gaussian Splats Worker", version="0.0.1")

# CORS: comma-separated origins via CORS_ORIGINS. "*" allows all (dev only).
# Production: set CORS_ORIGINS=https://your-frontend.vercel.app
_raw_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).strip()
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = LocalStorage(STORAGE_ROOT)
store = JobStore()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=CreateJobResponse)
async def create_job(
    background: BackgroundTasks,
    images: list[UploadFile] = File(...),
) -> CreateJobResponse:
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required.")

    job_id = uuid.uuid4().hex[:12]
    storage.job_dir(job_id)  # ensure exists

    saved = 0
    for f in images:
        # Light validation; deeper checks happen client-side pre-upload.
        if f.content_type and not f.content_type.startswith("image/"):
            continue
        data = await f.read()
        if not data:
            continue
        storage.save_upload(job_id, f.filename or f"img_{saved}.bin", data)
        saved += 1

    if saved == 0:
        raise HTTPException(status_code=400, detail="No valid images uploaded.")

    job = Job(
        id=job_id,
        status="queued",
        created_at=datetime.now(timezone.utc),
        image_count=saved,
    )
    store.put(job)

    background.add_task(
        run_pipeline,
        job_id,
        store=store,
        storage=storage,
        sample_splat_path=SAMPLE_SPLAT_PATH,
        stub_seconds=STUB_PROCESSING_SECONDS,
    )

    return CreateJobResponse(id=job_id)


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/jobs/{job_id}/splat")
def get_splat(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "done":
        raise HTTPException(status_code=409, detail=f"Job status is {job.status}.")
    path = storage.artifact_path(job_id, "scene.splat")
    if not path.exists():
        raise HTTPException(status_code=500, detail="Splat artifact missing on disk.")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename="scene.splat",
    )
