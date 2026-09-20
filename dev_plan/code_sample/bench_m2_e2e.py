"""End-to-end M2 measurement: build_metal on a via-array-heavy synthetic DEF.

Generates the real design's shape mix (via arrays of 512 points, the shape that
dominates a chip-level DEF) once, then times the sequential build.

Run:  python dev_plan/code_sample/bench_m2_e2e.py [reps]
"""
import contextlib
import io
import os
import subprocess
import sys
import time

from vlsi_viewer.metal import build_metal

DEF = "dev_plan/code_sample/real_shape.def/real_shape.def"
NG = "sample_data/real/nangate45"
LEFS = [f"{NG}/NangateOpenCellLibrary.macro.mod.lef"]
TECH = [f"{NG}/NangateOpenCellLibrary.tech.lef"]


def make_def():
    if os.path.exists(DEF):
        return
    cmd = [sys.executable, "sample_data/metal/generate_metal.py", "--real-shape",
           "--nets", "4000", "--instances", "20000", "--via-forms", "400",
           "--via-points", "512", "--via-nets", "4", "--out", DEF]
    subprocess.run(cmd, check=True)


def main():
    make_def()
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            build_metal([DEF], LEFS, TECH, grid_size=3.0, jobs=1)
        times.append(time.perf_counter() - t0)
    print(f"build_metal (via-array DEF, jobs=1): best {min(times):.2f}s "
          f"of {', '.join(f'{t:.2f}' for t in times)}")


if __name__ == "__main__":
    main()
