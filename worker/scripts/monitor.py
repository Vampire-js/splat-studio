#!/usr/bin/env python3
"""Pipeline performance monitor.

Writes a single timestamped log file with:
- CPU% / RSS / peak RSS of the worker process tree
- GPU utilisation + VRAM (via nvidia-smi, optional)
- COLMAP DB row counts (images / keypoints / matches / two_view_geometries)
- Stage transitions (sparse model written, brush PLY exported, .splat ready)
- Disk usage of the job dir
- (optional) any new lines appended to a uvicorn log file you pass with --log

Usage
-----
  ./.venv/bin/python scripts/monitor.py \\
      --job _storage/9d536544502a \\
      --pid 127714 \\
      --out perf.log \\
      --interval 5

Then in another terminal:
  tail -f worker/perf.log
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def fmt_mb(n_bytes: int) -> str:
    return f"{n_bytes / (1024 * 1024):.0f} MB"


def proc_tree_rss_cpu(root_pid: int) -> tuple[float, int, int]:
    """Return (cpu%, rss_bytes, n_procs) for root_pid + all descendants."""
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,rss,pcpu", "--no-headers"],
            text=True,
        )
    except Exception:
        return 0.0, 0, 0

    rows = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3])))
        except ValueError:
            continue

    children = {}
    for pid, ppid, rss, cpu in rows:
        children.setdefault(ppid, []).append((pid, rss, cpu))

    wanted = {root_pid}
    stack = [root_pid]
    while stack:
        p = stack.pop()
        for cpid, _, _ in children.get(p, []):
            if cpid not in wanted:
                wanted.add(cpid)
                stack.append(cpid)

    rss_total_kb = 0
    cpu_total = 0.0
    n = 0
    for pid, _, rss, cpu in rows:
        if pid in wanted:
            rss_total_kb += rss
            cpu_total += cpu
            n += 1
    return cpu_total, rss_total_kb * 1024, n


def gpu_stats() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        util, used, total, temp = [x.strip() for x in out.strip().splitlines()[0].split(",")]
        return f"gpu={util}% vram={used}/{total}MiB temp={temp}C"
    except Exception:
        return None


def db_counts(db_path: Path) -> dict[str, int] | None:
    if not db_path.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        out = {}
        for t in ("images", "keypoints", "matches", "two_view_geometries"):
            try:
                out[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                out[t] = -1
        db.close()
        return out
    except sqlite3.OperationalError:
        return None


def dir_size(p: Path) -> int:
    total = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def disk_free(p: Path) -> int:
    return shutil.disk_usage(p).free


def detect_stage(job: Path) -> str:
    artifacts = job / "artifacts"
    work = job / "work"
    if (artifacts / "scene.splat").exists():
        return "DONE (scene.splat written)"
    if list(artifacts.glob("*.ply")):
        return "EXPORT (PLY written, converting to .splat)"
    if any(work.glob("brush_out/**/point_cloud.ply")):
        return "TRAIN (brush iterations exporting)"
    if (work / "sparse" / "0" / "cameras.bin").exists():
        return "TRAIN (SfM done, brush should be running)"
    if (work / "database.db").exists():
        c = db_counts(work / "database.db") or {}
        m = c.get("matches", 0)
        kp = c.get("keypoints", 0)
        if c.get("images", 0) and not kp:
            return "SFM: extracting features"
        if kp and not m:
            return "SFM: matching (just started)"
        if m:
            return f"SFM: matching ({m} pairs done)"
        return "SFM: initialised DB"
    if (work / "images").exists():
        return "DOWNSCALE"
    return "PENDING"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="Path to _storage/<job_id>/")
    ap.add_argument("--pid", type=int, help="Worker PID to track (default: auto-detect uvicorn)")
    ap.add_argument("--out", default="perf.log", help="Output log file")
    ap.add_argument("--interval", type=float, default=5.0, help="Sample interval seconds")
    ap.add_argument("--log", help="Optional: also tail this file (e.g. uvicorn output)")
    args = ap.parse_args()

    job = Path(args.job).resolve()
    if not job.exists():
        print(f"job dir not found: {job}", file=sys.stderr)
        return 2

    pid = args.pid
    if pid is None:
        try:
            out = subprocess.check_output(["pgrep", "-f", "uvicorn app.main:app"], text=True)
            pid = int(out.strip().splitlines()[0])
            print(f"auto-detected worker pid {pid}", file=sys.stderr)
        except Exception:
            print("could not auto-detect worker pid; pass --pid", file=sys.stderr)
            return 2

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    f = out_path.open("a", buffering=1)  # line-buffered

    tail_fp = None
    if args.log:
        tail_path = Path(args.log)
        if tail_path.exists():
            tail_fp = tail_path.open("r")
            tail_fp.seek(0, 2)

    peak_rss = 0
    last_stage = ""
    start = time.monotonic()

    f.write("\n" + "=" * 78 + "\n")
    f.write(f"[{ts()}] monitor started  job={job.name}  pid={pid}  interval={args.interval}s\n")
    f.write("=" * 78 + "\n")

    try:
        while True:
            elapsed = int(time.monotonic() - start)
            mm, ss = divmod(elapsed, 60)
            hh, mm = divmod(mm, 60)
            elapsed_s = f"{hh:02d}:{mm:02d}:{ss:02d}"

            cpu, rss, n_proc = proc_tree_rss_cpu(pid)
            if rss > peak_rss:
                peak_rss = rss
            gpu = gpu_stats() or "gpu=n/a"
            stage = detect_stage(job)
            jdsz = dir_size(job)
            free = disk_free(job)
            db = db_counts(job / "work" / "database.db")
            db_str = ""
            if db:
                db_str = " db[" + " ".join(f"{k[:3]}={v}" for k, v in db.items()) + "]"

            line = (
                f"[{ts()} +{elapsed_s}] "
                f"stage={stage}  "
                f"cpu={cpu:5.1f}% rss={fmt_mb(rss)} peak={fmt_mb(peak_rss)} procs={n_proc}  "
                f"{gpu}  "
                f"jobsz={fmt_mb(jdsz)} free={fmt_mb(free)}"
                f"{db_str}"
            )
            f.write(line + "\n")

            if stage != last_stage:
                f.write(f"  >>> STAGE CHANGE: {last_stage!r} -> {stage!r}\n")
                last_stage = stage

            if tail_fp is not None:
                for raw in tail_fp:
                    f.write(f"  log| {raw.rstrip()}\n")

            if stage.startswith("DONE"):
                f.write(f"[{ts()}] monitor exiting (job done). peak_rss={fmt_mb(peak_rss)}\n")
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        f.write(f"\n[{ts()}] monitor stopped (Ctrl-C). peak_rss={fmt_mb(peak_rss)}\n")
    finally:
        f.close()
        if tail_fp:
            tail_fp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
