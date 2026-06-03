# =============================================================================
# Gaussian Splats Worker
# =============================================================================
# Two build modes via INSTALL_BRUSH:
#   --build-arg INSTALL_BRUSH=0  (default)
#       CPU-only image, ~600 MB. SfM works (pycolmap is CPU). The 3DGS training
#       stage falls back to the bundled sample (stub mode). Use on cheap CPU VMs
#       for shaking out plumbing / hosting the API.
#   --build-arg INSTALL_BRUSH=1
#       Adds the brush trainer (~170 MB) + Vulkan loader. Requires a host with
#       a Vulkan-capable GPU mounted in (or vendor-specific wgpu support).
#       Use on GPU VMs for real splat generation.
#
# Build:
#   docker build -t splats-worker:cpu .
#   docker build --build-arg INSTALL_BRUSH=1 -t splats-worker:gpu .
#
# Run (CPU):
#   docker run --rm -p 8000:8000 -v $(pwd)/_storage:/data/_storage splats-worker:cpu
# =============================================================================

FROM python:3.12-slim-bookworm AS base

# pycolmap needs libgomp1 (OpenMP) + libgl1 (image IO); curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so they cache across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Optional brush trainer + Vulkan runtime
# -----------------------------------------------------------------------------
ARG INSTALL_BRUSH=0
RUN if [ "$INSTALL_BRUSH" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libvulkan1 \
            mesa-vulkan-drivers \
            xz-utils \
        && rm -rf /var/lib/apt/lists/* ; \
    fi

COPY scripts/ ./scripts/
RUN if [ "$INSTALL_BRUSH" = "1" ]; then \
        bash scripts/install-brush.sh ; \
    fi

# -----------------------------------------------------------------------------
# App code + always-bundled small assets (vocab tree, sample splat)
# -----------------------------------------------------------------------------
COPY app/ ./app/
COPY samples/ ./samples/
COPY models/ ./models/

# Runtime knobs (override at `docker run -e ...`)
ENV STORAGE_ROOT=/data/_storage \
    SAMPLE_SPLAT_PATH=/app/samples/sample.splat \
    HOST=0.0.0.0 \
    PORT=8000 \
    PIPELINE_MATCHER=auto \
    PIPELINE_MAPPER=auto \
    PIPELINE_VOCAB_TREE_PATH=/app/models/vocab_tree_faiss_flickr100K_words32K.bin \
    BRUSH_BIN=/app/bin/brush \
    WGPU_BACKEND=VULKAN \
    CORS_ORIGINS=http://localhost:3000

# Persisted artifacts live here — mount a host volume.
VOLUME ["/data/_storage"]
RUN mkdir -p /data/_storage

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
