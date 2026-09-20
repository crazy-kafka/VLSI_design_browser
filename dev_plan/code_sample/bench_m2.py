"""Time build_metal on the real gcd DEF, before/after the __points_only fast path.

Run:  python dev_plan/code_sample/bench_m2.py [reps]
"""
import contextlib
import io
import sys
import time

from vlsi_viewer.metal import build_metal

NG = "sample_data/real/nangate45"
ARGS = ([f"{NG}/gcd_nangate45.def"],
        [f"{NG}/NangateOpenCellLibrary.macro.mod.lef"],
        [f"{NG}/NangateOpenCellLibrary.tech.lef"])


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            build_metal(*ARGS, grid_size=3.0, jobs=1)
        times.append(time.perf_counter() - t0)
    print(f"build_metal gcd_nangate45 jobs=1: {min(times):.2f}s "
          f"(best of {reps}: {', '.join(f'{t:.2f}' for t in times)})")


if __name__ == "__main__":
    main()
