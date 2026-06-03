"""Real 3D Gaussian Splat reconstruction pipeline.

Stages
------
0. **Downscale** uploaded images to a max long edge (~1280 px) with Pillow —
   reduces COLMAP matching time and keeps brush within 6 GB VRAM.
1. **Structure from Motion** via `pycolmap` (bundled COLMAP, CPU-only OK for
   <80 object images, no system install required).
2. **3DGS training** via the prebuilt `brush` binary (Rust + wgpu, runs on
   Vulkan, no CUDA toolkit needed). Output: a `scene.ply` of trained Gaussians.
3. **Convert** `scene.ply` -> `scene.splat` for the web viewer.
4. **Cleanup** uploads/ and work/ so only the ~50-200 MB artifact remains.

Fallback
--------
If `pycolmap` is not importable OR the `brush` binary isn't found, we fall back
to the v0 stub (publish the bundled sample) so the demo keeps working on
machines without the trainer installed. The job's `error` field surfaces the
exact reason.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from pathlib import Path

from .jobs import JobStore
from .ply_to_splat import ply_to_splat
from .storage import Storage

log = logging.getLogger("pipeline")

# Tunables — kept conservative to fit on a 6 GB laptop GPU. Override via env.
MAX_IMAGE_LONG_EDGE = int(os.environ.get("PIPELINE_MAX_IMAGE_EDGE", "1280"))
TRAIN_TOTAL_STEPS = int(os.environ.get("PIPELINE_TRAIN_STEPS", "7000"))
TRAIN_MAX_SPLATS = int(os.environ.get("PIPELINE_MAX_SPLATS", "300000"))
TRAIN_SH_DEGREE = int(os.environ.get("PIPELINE_SH_DEGREE", "2"))
TRAIN_MAX_RESOLUTION = int(os.environ.get("PIPELINE_TRAIN_MAX_RES", "1280"))
CLEANUP_INTERMEDIATES = os.environ.get("PIPELINE_CLEANUP", "1") != "0"

# --- SfM matcher selection ----------------------------------------------------
# auto       -> sequential if PIPELINE_SEQUENTIAL=1, else vocab_tree if N>auto_threshold
#               and a vocab tree file is available, else exhaustive.
# exhaustive -> O(N^2), gold standard, slowest. Safe default for small unordered sets.
# sequential -> O(N), only correct for ordered captures (video frames, dense orbits).
# vocab_tree -> O(N*k), retrieval-pruned; needs PIPELINE_VOCAB_TREE_PATH to point
#               at a pretrained vocab tree (see scripts/install-vocab-tree.sh).
PIPELINE_MATCHER = os.environ.get("PIPELINE_MATCHER", "auto").lower()
PIPELINE_AUTO_VOCAB_THRESHOLD = int(os.environ.get("PIPELINE_AUTO_VOCAB_THRESHOLD", "80"))
PIPELINE_VOCAB_TREE_PATH = os.environ.get("PIPELINE_VOCAB_TREE_PATH", "")
# Whether `auto` may pick sequential. Off by default — only enable for ordered input.
PIPELINE_SEQUENTIAL_HINT = os.environ.get("PIPELINE_SEQUENTIAL", "0") != "0"
# Cap features per image. Lower = faster matching (quadratic in feature count per pair).
PIPELINE_SIFT_MAX_FEATURES = int(os.environ.get("PIPELINE_SIFT_MAX_FEATURES", "4096"))
# Threads for matching. -1 = use all cores.
PIPELINE_MATCH_THREADS = int(os.environ.get("PIPELINE_MATCH_THREADS", "-1"))


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------
def _find_brush() -> Path | None:
    """Locate the brush binary: $BRUSH_BIN, then worker/bin/brush, then $PATH."""
    env_bin = os.environ.get("BRUSH_BIN")
    if env_bin and Path(env_bin).is_file():
        return Path(env_bin)
    bundled = Path(__file__).resolve().parent.parent / "bin" / "brush"
    if bundled.is_file():
        return bundled
    found = shutil.which("brush") or shutil.which("brush_app")
    return Path(found) if found else None


def _have_pycolmap() -> bool:
    try:
        import pycolmap  # noqa: F401
        return True
    except Exception:
        return False


def pipeline_available() -> tuple[bool, str]:
    """Return (ok, reason). Reason is empty when ok=True."""
    if not _have_pycolmap():
        return False, "pycolmap not installed (pip install pycolmap)"
    if _find_brush() is None:
        return False, "brush binary not found (run worker/scripts/install-brush.sh)"
    return True, ""


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------
def _downscale_images(src_dir: Path, dst_dir: Path, max_edge: int) -> int:
    from PIL import Image, ImageOps

    dst_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(src_dir.iterdir()):
        if not p.is_file():
            continue
        try:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im)
                im = im.convert("RGB")
                w, h = im.size
                long_edge = max(w, h)
                if long_edge > max_edge:
                    scale = max_edge / long_edge
                    im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
                # JPEG keeps COLMAP matching fast and brush memory low.
                out = dst_dir / (p.stem + ".jpg")
                im.save(out, "JPEG", quality=92)
                n += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("skip non-image %s: %s", p.name, exc)
    return n


def _resolve_vocab_tree() -> Path | None:
    """Locate a usable vocab tree file, or None if unavailable."""
    if PIPELINE_VOCAB_TREE_PATH:
        p = Path(PIPELINE_VOCAB_TREE_PATH)
        if p.is_file():
            return p
        log.warning("PIPELINE_VOCAB_TREE_PATH set but file missing: %s", p)
    bundled = Path(__file__).resolve().parent.parent / "models" / "vocab_tree_flickr100K_words32K.bin"
    return bundled if bundled.is_file() else None


def _choose_matcher(n_images: int) -> str:
    """Pick a matcher mode given user config + image count."""
    mode = PIPELINE_MATCHER
    if mode != "auto":
        return mode
    if PIPELINE_SEQUENTIAL_HINT:
        return "sequential"
    if n_images > PIPELINE_AUTO_VOCAB_THRESHOLD and _resolve_vocab_tree() is not None:
        return "vocab_tree"
    return "exhaustive"


def _run_matching(db_path: Path, n_images: int) -> str:
    """Dispatch to the configured matcher. Returns the mode actually used."""
    import pycolmap

    mode = _choose_matcher(n_images)
    sift = pycolmap.SiftMatchingOptions(num_threads=PIPELINE_MATCH_THREADS)
    log.info("matching: mode=%s n_images=%d threads=%d", mode, n_images, PIPELINE_MATCH_THREADS)

    if mode == "exhaustive":
        pycolmap.match_exhaustive(str(db_path), sift_options=sift)
    elif mode == "sequential":
        opts = pycolmap.SequentialMatchingOptions(overlap=10, quadratic_overlap=True)
        pycolmap.match_sequential(str(db_path), sift_options=sift, matching_options=opts)
    elif mode == "vocab_tree":
        vt = _resolve_vocab_tree()
        if vt is None:
            log.warning("vocab_tree requested but no tree file found; falling back to exhaustive")
            pycolmap.match_exhaustive(str(db_path), sift_options=sift)
            return "exhaustive (fallback)"
        opts = pycolmap.VocabTreeMatchingOptions(
            vocab_tree_path=str(vt),
            num_images=min(100, max(20, n_images // 2)),
            num_threads=PIPELINE_MATCH_THREADS,
        )
        pycolmap.match_vocabtree(str(db_path), sift_options=sift, matching_options=opts)
    else:
        raise ValueError(
            f"PIPELINE_MATCHER={mode!r} invalid (use auto|exhaustive|sequential|vocab_tree)"
        )
    return mode


def _run_sfm(image_dir: Path, work_dir: Path) -> Path:
    """Run COLMAP SfM. Returns the path of the produced sparse model directory."""
    import pycolmap

    db_path = work_dir / "database.db"
    sparse_root = work_dir / "sparse"
    sparse_root.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    n_images = sum(1 for p in image_dir.iterdir() if p.is_file())

    # Single-camera + SIMPLE_RADIAL is the right call for orbit captures of one
    # object taken with the same phone — fewer free parameters, more stable
    # poses on small image sets.
    sift_extract = pycolmap.SiftExtractionOptions(
        num_threads=PIPELINE_MATCH_THREADS,
        max_num_features=PIPELINE_SIFT_MAX_FEATURES,
    )
    pycolmap.extract_features(
        database_path=str(db_path),
        image_path=str(image_dir),
        camera_mode=pycolmap.CameraMode.SINGLE,
        camera_model="SIMPLE_RADIAL",
        sift_options=sift_extract,
    )
    _run_matching(db_path, n_images)
    maps = pycolmap.incremental_mapping(
        database_path=str(db_path),
        image_path=str(image_dir),
        output_path=str(sparse_root),
    )
    if not maps:
        raise RuntimeError("COLMAP failed to reconstruct any cameras from the input images.")

    # brush expects sparse/0/{cameras,images,points3D}.bin. pycolmap writes
    # sparse/0/, sparse/1/ etc. — pick the largest model.
    candidates = sorted(
        [p for p in sparse_root.iterdir() if p.is_dir()],
        key=lambda p: len(list(p.glob("*"))),
        reverse=True,
    )
    best = candidates[0]
    if best.name != "0":
        target = sparse_root / "0"
        if target.exists():
            shutil.rmtree(target)
        best.rename(target)
    return sparse_root / "0"


_STEP_RE = re.compile(r"\b(?:step|iter|iteration)[\s:=]*?(\d+)\b", re.IGNORECASE)


async def _run_brush(
    brush_bin: Path,
    dataset_dir: Path,
    artifact_dir: Path,
    *,
    total_steps: int,
    on_progress,
) -> Path:
    """Train with brush. Returns the path to the exported PLY."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(brush_bin),
        str(dataset_dir),
        "--total-steps", str(total_steps),
        "--max-splats", str(TRAIN_MAX_SPLATS),
        "--sh-degree", str(TRAIN_SH_DEGREE),
        "--max-resolution", str(TRAIN_MAX_RESOLUTION),
        "--export-path", str(artifact_dir),
        "--export-name", "scene.ply",
        "--export-every", str(total_steps),
    ]
    log.info("brush: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "WGPU_BACKEND": os.environ.get("WGPU_BACKEND", "VULKAN")},
    )

    assert proc.stdout is not None
    start = time.monotonic()
    last_update = start
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip()
        if line:
            log.info("brush| %s", line)
        # Try to parse a step number; otherwise interpolate by elapsed time.
        m = _STEP_RE.search(line)
        now = time.monotonic()
        if m:
            step = min(int(m.group(1)), total_steps)
            frac = step / total_steps
            on_progress(0.40 + 0.50 * frac)  # train phase = 0.40 .. 0.90
            last_update = now
        elif now - last_update > 5:
            # Heuristic: assume training takes ~10 min; never decrease.
            elapsed_frac = min(0.95, (now - start) / 600.0)
            on_progress(0.40 + 0.50 * elapsed_frac)
            last_update = now

    rc = await proc.wait()
    if rc != 0:
        raise RuntimeError(f"brush exited with code {rc}")

    out = artifact_dir / "scene.ply"
    if not out.exists():
        plys = sorted(artifact_dir.glob("*.ply"))
        if not plys:
            raise RuntimeError("brush finished but no PLY was exported.")
        out = plys[-1]
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
async def run_pipeline(
    job_id: str,
    *,
    store: JobStore,
    storage: Storage,
    sample_splat_path: Path,
    stub_seconds: float,
) -> None:
    """Run the real pipeline. Fall back to the sample on capability failure."""
    try:
        store.update(job_id, status="processing", progress=0.02)

        ok, reason = pipeline_available()
        if not ok:
            log.warning("job=%s real pipeline unavailable (%s); using stub.", job_id, reason)
            await _run_stub(job_id, store=store, storage=storage,
                            sample_splat_path=sample_splat_path,
                            stub_seconds=stub_seconds,
                            note=f"stub: {reason}")
            return

        await _run_real(job_id, store=store, storage=storage)

    except Exception as exc:  # noqa: BLE001
        log.exception("job=%s failed", job_id)
        store.update(job_id, status="failed", error=str(exc))


async def _run_real(job_id: str, *, store: JobStore, storage: Storage) -> None:
    job_dir = storage.job_dir(job_id)
    uploads_dir = job_dir / "uploads"
    artifact_dir = job_dir / "artifacts"
    work_dir = job_dir / "work"
    images_dir = work_dir / "images"
    work_dir.mkdir(parents=True, exist_ok=True)

    # --- 0. downscale -------------------------------------------------------
    n = _downscale_images(uploads_dir, images_dir, MAX_IMAGE_LONG_EDGE)
    if n < 8:
        raise RuntimeError(
            f"Only {n} usable images after preprocessing — need at least ~20 for "
            "a reasonable splat. Try a denser orbit around the object."
        )
    store.update(job_id, progress=0.10)
    log.info("job=%s downscaled %d images", job_id, n)

    # --- 1. SfM (COLMAP) ----------------------------------------------------
    sparse_dir = await asyncio.to_thread(_run_sfm, images_dir, work_dir)
    store.update(job_id, progress=0.40)
    log.info("job=%s SfM done -> %s", job_id, sparse_dir)

    # --- 2. train (brush) ---------------------------------------------------
    brush_bin = _find_brush()
    assert brush_bin is not None  # checked in pipeline_available
    ply_path = await _run_brush(
        brush_bin,
        dataset_dir=work_dir,  # brush reads <root>/images + <root>/sparse/0/
        artifact_dir=artifact_dir,
        total_steps=TRAIN_TOTAL_STEPS,
        on_progress=lambda p: store.update(job_id, progress=min(0.95, p)),
    )
    store.update(job_id, progress=0.92)
    log.info("job=%s training done -> %s", job_id, ply_path)

    # --- 3. convert to .splat ----------------------------------------------
    splat_path = artifact_dir / "scene.splat"
    n_splats = await asyncio.to_thread(ply_to_splat, ply_path, splat_path)
    log.info("job=%s converted %d splats -> %s (%d bytes)",
             job_id, n_splats, splat_path, splat_path.stat().st_size)

    # --- 4. cleanup ---------------------------------------------------------
    if CLEANUP_INTERMEDIATES:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
            shutil.rmtree(uploads_dir, ignore_errors=True)
            if ply_path.exists() and ply_path != splat_path:
                ply_path.unlink()
        except Exception:  # noqa: BLE001
            log.warning("job=%s cleanup partial failure", job_id, exc_info=True)

    store.update(
        job_id,
        status="done",
        progress=1.0,
        splat_url=f"/jobs/{job_id}/splat",
    )


async def _run_stub(
    job_id: str,
    *,
    store: JobStore,
    storage: Storage,
    sample_splat_path: Path,
    stub_seconds: float,
    note: str = "",
) -> None:
    """Original v0 stub — fallback for dev machines without the trainer."""
    phases = [(0.20, "sfm"), (0.50, "init"), (0.85, "train"), (0.95, "export")]
    per_phase = max(0.1, stub_seconds / len(phases))
    for progress, phase in phases:
        await asyncio.sleep(per_phase)
        store.update(job_id, progress=progress)
        log.info("job=%s [stub] phase=%s progress=%.2f", job_id, phase, progress)
    if not sample_splat_path.exists():
        raise FileNotFoundError(f"Sample splat not found at {sample_splat_path}.")
    storage.write_artifact(job_id, "scene.splat", sample_splat_path)
    store.update(
        job_id,
        status="done",
        progress=1.0,
        splat_url=f"/jobs/{job_id}/splat",
        error=note or None,
    )
