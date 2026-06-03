# Splat Studio — POC v0

Turn a set of photos into an **embeddable 3D Gaussian Splat** of an object.
Drop the generated `<iframe>` into any website — like Spline or Sketchfab, but
photorealistic because the model comes from real photos (lighting, reflections,
and view-dependent effects baked into per-splat spherical harmonics).

This repo is the **proof-of-concept** that proves the full loop end-to-end:

```
upload photos → create job → COLMAP SfM → 3DGS training → .splat → embeddable viewer → copy snippet
```

The reconstruction pipeline is **real**: it runs COLMAP via `pycolmap` for
structure-from-motion, then trains a 3D Gaussian Splatting model with
[`brush`](https://github.com/ArthurBrussee/brush) (Rust + wgpu/Vulkan — **no
CUDA toolkit required**), converts the result to `.splat`, and serves it to
the embeddable viewer.

If either `pycolmap` or the `brush` binary is missing, the worker **falls back
to a stub** that publishes a bundled sample splat after a short delay. This
keeps the demo runnable on any dev machine.

---

## Architecture

```
┌─────────────────────┐        HTTP        ┌──────────────────────────┐
│  Next.js 14 (web/)  │ ─────────────────► │  FastAPI worker (worker/) │
│  - upload UI        │   POST /jobs       │  - jobs registry          │
│  - results page     │   GET  /jobs/:id   │  - storage (local FS)     │
│  - /embed/:id page  │   GET  /splat      │  - pipeline:              │
│  - API proxy routes │                    │     COLMAP -> brush -> .splat │
└─────────────────────┘                    └──────────────────────────┘
        ▲
        │ <iframe src=".../embed/:id">
        │
   user's website
```

- **Web:** Next.js 14 App Router, TypeScript, React 18. Renders splats with
  [`@mkkellogg/gaussian-splats-3d`](https://github.com/mkkellogg/GaussianSplats3D)
  (Three.js-based, supports `.ply`/`.splat`/`.ksplat`, has built-in orbit
  controls). The browser never talks to the worker directly — Next.js API
  routes proxy everything, so the worker URL can stay private.
- **Worker:** FastAPI + uvicorn. Owns uploads on disk, runs the pipeline, and
  serves the resulting splat. Job state lives in process memory in v0.
- **Shared contracts:** [web/src/lib/types.ts](web/src/lib/types.ts) ↔
  [worker/app/models.py](worker/app/models.py) — hand-mirrored; swap for
  generated OpenAPI bindings later.
- **Storage:** behind a `Storage` interface ([worker/app/storage.py](worker/app/storage.py),
  [web/src/lib/storage.ts](web/src/lib/storage.ts)); local FS in v0, S3 later.

---

## Run it locally

You'll need:

- Node.js ≥ 18
- Python ≥ 3.10
- A WebGL2-capable browser (any modern Chromium/Firefox/Safari)

### 1. Start the worker (terminal A)

```bash
cd worker
cp .env.example .env
./run.sh            # creates a venv, installs deps, runs uvicorn on :8000
```

You should see `Uvicorn running on http://0.0.0.0:8000`.

#### Enable the real ML pipeline (optional but recommended)

`run.sh` already installs `pycolmap`, `Pillow`, and `numpy` via
`requirements.txt`. The only extra step is fetching the `brush` trainer
binary (~44 MB download, 164 MB unpacked):

```bash
cd worker
./scripts/install-brush.sh    # downloads to worker/bin/brush
```

Hardware requirements for the real pipeline:
- A GPU with **Vulkan** support (any NVIDIA with recent driver, Intel Arc, AMD,
  Apple Silicon). **No CUDA toolkit needed** — brush talks to the driver
  directly via wgpu.
- ~4–8 GB VRAM (controlled by `PIPELINE_MAX_SPLATS` and
  `PIPELINE_TRAIN_MAX_RES` in `.env.example`).
- A display server (X/Wayland on Linux). On headless boxes, run brush under
  `xvfb-run`.

If you skip `install-brush.sh`, the worker still starts and serves jobs —
each job's `error` field will contain `stub: brush binary not found` and the
bundled sample splat is returned. Great for frontend work.

### 2. Start the web app (terminal B)

```bash
cd web
cp .env.example .env.local
npm install
npm run dev         # http://localhost:3000
```

### 3. Use it

1. Open <http://localhost:3000>.
2. Drag-drop any folder of images (they're not actually used in v0 — the
   stubbed pipeline always returns the bundled sample — but the upload, count,
   resolution, and blur pre-flight checks are real).
3. You'll be redirected to `/jobs/:id` where a progress bar shows the stubbed
   training. After ~4 seconds the splat viewer loads.
4. Below the viewer, copy the `<iframe>` snippet and paste it anywhere — the
   embed page at `/embed/:id` is iframe-ready (chrome-less, full-bleed).

---

## What's bundled vs. stubbed

| Feature                                    | Status                  |
| ------------------------------------------ | ----------------------- |
| Drag-drop upload UI                        | ✅ real                  |
| Client-side pre-flight (count/res/blur)    | ✅ real                  |
| Job model + REST API                       | ✅ real (in-memory)      |
| Worker → Next.js HTTP plumbing             | ✅ real                  |
| Splat web viewer + orbit controls          | ✅ real                  |
| Embeddable `/embed/:id` page + iframe snip | ✅ real                  |
| **COLMAP SfM** (via `pycolmap`)            | ✅ real                  |
| **3DGS training** (via `brush`)            | ✅ real (Vulkan, no CUDA)|
| **PLY → `.splat` conversion**              | ✅ real                  |
| Sample splat fallback if trainer missing   | ✅ bundled `.splat`      |
| Auth, billing, multi-tenancy               | ❌ out of scope          |
| S3 / cloud storage                         | ❌ stubbed (`Storage` IF)|
| Job queue at scale (Celery/Redis)          | ❌ in-process tasks      |
| Splat compression / LOD streaming          | ❌ future core feature   |
| Guided mobile capture app                  | ❌ future moat           |

---

## The real pipeline, step by step

When both `pycolmap` and `brush` are available, every `POST /jobs` triggers
[worker/app/pipeline.py](worker/app/pipeline.py):

| # | Stage         | Tool / code                                | Tunable env                       |
|---|---------------|--------------------------------------------|-----------------------------------|
| 0 | Downscale     | `Pillow` (EXIF-aware, JPEG re-encode)      | `PIPELINE_MAX_IMAGE_EDGE`         |
| 1 | SfM           | `pycolmap.extract_features → match_exhaustive → incremental_mapping` (`SIMPLE_RADIAL`, single-camera) | — |
| 2 | Train         | `brush <dataset> --total-steps N ...`       | `PIPELINE_TRAIN_STEPS`, `PIPELINE_MAX_SPLATS`, `PIPELINE_SH_DEGREE`, `PIPELINE_TRAIN_MAX_RES` |
| 3 | Convert       | `app/ply_to_splat.py` (INRIA PLY → antimatter15 `.splat`) | — |
| 4 | Cleanup       | rm `uploads/`, `work/`, intermediate PLY   | `PIPELINE_CLEANUP=0` to keep      |

Progress is reported live to the frontend: 0.10 after downscale, 0.40 after
SfM, 0.40 → 0.90 during training (parsed from brush's step log, with a
time-based fallback), 1.0 after `.splat` is on disk.

### Capacity & timing (RTX 4050 6 GB laptop, 30–60 photos)

- Downscale: < 5 s
- COLMAP SfM: 1–4 min (CPU)
- Brush training (7 000 steps, 300 k splats, SH degree 2): 5–15 min
- `.splat` output: typically 5–30 MB

For paper-quality output, raise `PIPELINE_TRAIN_STEPS=30000`,
`PIPELINE_MAX_SPLATS=2000000`, and `PIPELINE_SH_DEGREE=3` — expect 30–60 min
and a noticeably larger artifact.

### Getting test images

Smallest path: shoot a 20–40 s video orbiting one object on a turntable,
then:

```bash
ffmpeg -i orbit.mp4 -vf "fps=2,scale='min(1600,iw)':-1" frames/frame_%04d.jpg
```

Drop the resulting folder into the upload UI.

Public object-capture datasets:
- **CO3D v2** — turntable-style real captures: <https://github.com/facebookresearch/co3d>
- **OmniObject3D** — 6 k scanned objects: <https://omniobject3d.github.io/>
- **Mip-NeRF 360** scenes (`garden`, `bonsai`, …): <https://jonbarron.info/mipnerf360/>
- **INRIA 3DGS inputs** (tandt + db, 651 MB): <https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/datasets/input/tandt_db.zip>

---

## Folder layout

```
gaussian-splats/
├── README.md                   ← you are here
├── web/                        ← Next.js 14 (TS, App Router)
│   ├── public/samples/         ← bundled sample.splat
│   └── src/
│       ├── app/                ← pages + API routes
│       │   ├── page.tsx              upload UI
│       │   ├── jobs/[id]/page.tsx    results + embed snippet
│       │   ├── embed/[id]/page.tsx   chrome-less iframe viewer
│       │   └── api/jobs/…            REST proxy to the worker
│       ├── components/         ← Uploader, SplatViewer, EmbedSnippet
│       └── lib/                ← types, worker client, preflight, storage IF
└── worker/                     ← FastAPI service
    ├── samples/sample.splat
    ├── bin/brush                ← trainer binary (164 MB, gitignored)
    ├── scripts/install-brush.sh ← fetches the brush binary
    ├── run.sh                   ← venv + uvicorn helper
    ├── tests/test_ply_to_splat.py
    └── app/
        ├── main.py              ← FastAPI routes
        ├── models.py            ← pydantic schemas (mirror lib/types.ts)
        ├── jobs.py              ← in-memory job registry
        ├── pipeline.py          ← REAL pipeline: downscale → SfM → brush → .splat
        ├── ply_to_splat.py      ← INRIA PLY → antimatter15 .splat converter
        └── storage.py           ← local FS; swap for S3 later
```

---

## Production / "what's next" notes

- Run the GPU pipeline on a separate worker fleet (RunPod / Modal / on-prem).
  The current `BackgroundTasks` call becomes a queue push (Redis + RQ, SQS,
  or Temporal).
- Move storage to S3 + CloudFront for splat artifacts; pre-signed PUTs so
  files never traverse the API.
- Splat compression / LOD streaming — investigate
  [SOG](https://github.com/Sharath-girish/efficientgaussian),
  [Self-Organizing Gaussians](https://github.com/fraunhoferhhi/Self-Organizing-Gaussians),
  or [HAC](https://github.com/YihangChen-ee/HAC) for 5–20× size reduction.
- Add auth (Clerk/Auth.js) and per-tenant rate limits before opening up.


## MVP v1
- Feature extraction + matching: ~53 mins
- Brush: ~6 mins 
- Conversion: 1 sec

