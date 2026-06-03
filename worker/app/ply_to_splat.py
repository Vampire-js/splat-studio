"""Convert a 3D Gaussian Splatting PLY into the antimatter15 `.splat` format.

The `.splat` format is 32 bytes per splat, little-endian:
    pos       3 × f32 (12)
    scale     3 × f32 (12)       — linear scale (post-exp)
    color    4 × u8 (4)         — RGBA, 0..255
    rotation  4 × u8 (4)         — quaternion, packed as round(q*128 + 128)

Splats are pre-sorted by `-scale * sigmoid(opacity)` (descending) so the web
viewer can stop early on truncation. We follow the same convention used by
antimatter15/splat's PLY converter so the bundled web viewer renders the
output identically to its sample data.

Source PLY is the standard INRIA 3DGS export with these per-vertex properties:
    x,y,z, nx,ny,nz, f_dc_{0,1,2}, [f_rest_*], opacity, scale_{0,1,2}, rot_{0,1,2,3}
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# DC term of band-0 spherical harmonics. f_dc_i values in the PLY are stored
# as SH coefficients; recovering linear RGB requires this offset.
SH_C0 = 0.28209479177387814


def _parse_ply_header(fh) -> tuple[int, list[tuple[str, str]], int]:
    """Return (vertex_count, [(prop_name, dtype_str), ...], header_byte_size)."""
    header_lines: list[str] = []
    while True:
        raw = fh.readline()
        if not raw:
            raise ValueError("Unexpected EOF reading PLY header.")
        line = raw.decode("ascii", errors="replace").rstrip("\n").rstrip("\r")
        header_lines.append(line)
        if line == "end_header":
            break

    if header_lines[0] != "ply":
        raise ValueError("Not a PLY file.")
    fmt_line = header_lines[1]
    if "binary_little_endian" not in fmt_line:
        raise ValueError(f"Only binary_little_endian PLYs are supported, got: {fmt_line}")

    vertex_count = 0
    props: list[tuple[str, str]] = []
    in_vertex_element = False
    type_map = {
        "float": "f4", "float32": "f4",
        "double": "f8", "float64": "f8",
        "uchar": "u1", "uint8": "u1",
        "char": "i1", "int8": "i1",
        "ushort": "u2", "uint16": "u2",
        "short": "i2", "int16": "i2",
        "uint": "u4", "uint32": "u4",
        "int": "i4", "int32": "i4",
    }
    for line in header_lines:
        if line.startswith("element "):
            parts = line.split()
            in_vertex_element = parts[1] == "vertex"
            if in_vertex_element:
                vertex_count = int(parts[2])
        elif line.startswith("property ") and in_vertex_element:
            parts = line.split()
            ply_type = parts[1]
            name = parts[-1]
            if ply_type not in type_map:
                raise ValueError(f"Unsupported PLY property type: {ply_type}")
            props.append((name, type_map[ply_type]))

    header_size = fh.tell()
    return vertex_count, props, header_size


def ply_to_splat(ply_path: Path, splat_path: Path) -> int:
    """Convert a 3DGS PLY file to a .splat file. Returns the number of splats written."""
    ply_path = Path(ply_path)
    splat_path = Path(splat_path)

    with ply_path.open("rb") as fh:
        n, props, header_size = _parse_ply_header(fh)
        dtype = np.dtype([(name, "<" + t) for name, t in props])
        body = np.fromfile(fh, dtype=dtype, count=n)

    if body.shape[0] != n:
        raise ValueError(f"PLY truncated: header said {n}, read {body.shape[0]}.")

    # --- positions ----------------------------------------------------------
    pos = np.stack([body["x"], body["y"], body["z"]], axis=1).astype(np.float32)

    # --- scales (log-space in PLY -> linear) --------------------------------
    scale = np.stack(
        [np.exp(body["scale_0"]), np.exp(body["scale_1"]), np.exp(body["scale_2"])],
        axis=1,
    ).astype(np.float32)

    # --- color (SH band-0 + sigmoid opacity) --------------------------------
    rgb = 0.5 + SH_C0 * np.stack(
        [body["f_dc_0"], body["f_dc_1"], body["f_dc_2"]], axis=1
    )
    rgb = np.clip(rgb, 0.0, 1.0)
    alpha = 1.0 / (1.0 + np.exp(-body["opacity"].astype(np.float32)))
    rgba_u8 = np.empty((n, 4), dtype=np.uint8)
    rgba_u8[:, 0:3] = np.round(rgb * 255.0).astype(np.uint8)
    rgba_u8[:, 3] = np.round(alpha * 255.0).astype(np.uint8)

    # --- rotation (normalize quaternion, pack to u8) ------------------------
    quat = np.stack(
        [body["rot_0"], body["rot_1"], body["rot_2"], body["rot_3"]], axis=1
    ).astype(np.float32)
    norm = np.linalg.norm(quat, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    quat /= norm
    rot_u8 = np.clip(np.round(quat * 128.0 + 128.0), 0, 255).astype(np.uint8)

    # --- importance sort (largest, most opaque first) -----------------------
    importance = -(scale.max(axis=1) * alpha)
    order = np.argsort(importance)

    # --- pack to 32-byte records --------------------------------------------
    buf = bytearray(n * 32)
    out = np.frombuffer(buf, dtype=np.uint8)
    out_view = out.reshape(n, 32)

    pos_b = pos[order].tobytes()
    scale_b = scale[order].tobytes()
    rgba_b = rgba_u8[order].tobytes()
    rot_b = rot_u8[order].tobytes()

    pos_arr = np.frombuffer(pos_b, dtype=np.uint8).reshape(n, 12)
    scale_arr = np.frombuffer(scale_b, dtype=np.uint8).reshape(n, 12)
    rgba_arr = np.frombuffer(rgba_b, dtype=np.uint8).reshape(n, 4)
    rot_arr = np.frombuffer(rot_b, dtype=np.uint8).reshape(n, 4)

    out_view[:, 0:12] = pos_arr
    out_view[:, 12:24] = scale_arr
    out_view[:, 24:28] = rgba_arr
    out_view[:, 28:32] = rot_arr

    splat_path.parent.mkdir(parents=True, exist_ok=True)
    splat_path.write_bytes(bytes(buf))
    return n
