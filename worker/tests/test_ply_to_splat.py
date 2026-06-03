"""Sanity test for the PLY -> .splat converter. Synthetic 5-splat input."""
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ply_to_splat import ply_to_splat

N = 5
verts = np.zeros(N, dtype=[
    ("x","<f4"),("y","<f4"),("z","<f4"),
    ("nx","<f4"),("ny","<f4"),("nz","<f4"),
    ("f_dc_0","<f4"),("f_dc_1","<f4"),("f_dc_2","<f4"),
    ("opacity","<f4"),
    ("scale_0","<f4"),("scale_1","<f4"),("scale_2","<f4"),
    ("rot_0","<f4"),("rot_1","<f4"),("rot_2","<f4"),("rot_3","<f4"),
])
verts["x"] = [0,1,2,3,4]
verts["f_dc_0"] = 0.5; verts["f_dc_1"] = 0.0; verts["f_dc_2"] = -0.5
verts["opacity"] = 2.0
verts["scale_0"] = verts["scale_1"] = verts["scale_2"] = -2.0
verts["rot_0"] = 1.0

header = (
    "ply\n"
    "format binary_little_endian 1.0\n"
    f"element vertex {N}\n"
    "property float x\nproperty float y\nproperty float z\n"
    "property float nx\nproperty float ny\nproperty float nz\n"
    "property float f_dc_0\nproperty float f_dc_1\nproperty float f_dc_2\n"
    "property float opacity\n"
    "property float scale_0\nproperty float scale_1\nproperty float scale_2\n"
    "property float rot_0\nproperty float rot_1\nproperty float rot_2\nproperty float rot_3\n"
    "end_header\n"
)

with tempfile.TemporaryDirectory() as td:
    ply = Path(td) / "in.ply"
    splat = Path(td) / "out.splat"
    with ply.open("wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(verts.tobytes())
    n_out = ply_to_splat(ply, splat)
    data = splat.read_bytes()
    assert n_out == N
    assert len(data) == N * 32
    px, py, pz, sx, sy, sz = struct.unpack_from("<6f", data, 0)
    r, g, b, a = struct.unpack_from("<4B", data, 24)
    rx, ry, rz, rw = struct.unpack_from("<4B", data, 28)
    print(f"OK n={n_out} bytes={len(data)}")
    print(f"  pos=({px:.2f},{py:.2f},{pz:.2f}) scale=({sx:.4f},{sy:.4f},{sz:.4f})")
    print(f"  rgba=({r},{g},{b},{a}) rot_u8=({rx},{ry},{rz},{rw})")
    assert 0.10 < sx < 0.20, sx
    assert 200 < a < 240, a
    assert 240 <= rx <= 255, rx
    assert 120 <= ry <= 135, ry
    print("converter sanity checks passed.")
