"""Benchmark hierarchy contour and density on the bundled physical sample.

    python sample_data/bench_contour_density.py --repeat 3
    python sample_data/bench_contour_density.py --repeat 3 --check
    python sample_data/bench_contour_density.py --scale 8 --repeat 3

Reports, per hierarchy node: box count, merged rectangle count, merge time, area time,
loop count/points, and the area's difference from the shapely reference. Also reports
the sequential cost of computing all hierarchy densities and of the initial visible set
(root + first-level children above the default threshold), plus an optional scaled
merge/area measurement on the largest node.

The script works against both the old (pandas merge + shapely area) and the optimized
(numpy merge + sweep area) implementations, so the same command records before/after.
"""
import argparse
import os
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vlsi_viewer import contour
from vlsi_viewer.metrics import build_design
from vlsi_viewer.physical import build_physical

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "physical")
BLOCKS = [os.path.join(SAMPLE, name) for name in
          ("instance_info.json", "CORE.json", "IFU.json", "IEX.json", "LSU.json")]
CELLS = os.path.join(SAMPLE, "cell_info.json")
REAL_INSTANCES = 3_355_697


def _merge(boxes, gap):
    """Current merge entry point (new API when present, old otherwise)."""
    if hasattr(contour, "merge_rects"):
        return contour.merge_rects(boxes, gap)
    return contour.merge_boxes(contour._expanded(boxes, gap))


def _timed(fn, repeat):
    times = []
    out = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t0)
    return out, statistics.median(times)


def _loop_points(loops):
    return sum(len(loop) for loop in loops)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--scale", type=int, default=1,
                    help="replicate the largest node's boxes K times for merge/area")
    ap.add_argument("--shapely", action="store_true",
                    help="also time the shapely area reference at scale")
    ap.add_argument("--check", action="store_true",
                    help="gate geometry error and the plan's timing targets")
    args = ap.parse_args()

    design, t_design = _timed(lambda: build_design(BLOCKS, CELLS), 1)
    physical, t_physical = _timed(
        lambda: build_physical(BLOCKS, CELLS, grid_size=3.0), 1)
    paths = list(design.hier.index)
    gap = physical.contour_gap
    print(f"sample: {len(physical._geom):,} boxes, {len(paths)} hierarchy nodes, "
          f"grid {physical.rows} x {physical.cols}, gap {gap:g}")
    print(f"build_design {t_design:.2f}s, build_physical {t_physical:.2f}s")

    failures = []
    per_node = {}
    print(f"\n{'node':34s} {'boxes':>8s} {'merged':>7s} {'merge':>9s} "
          f"{'area':>9s} {'loops':>8s} {'points':>7s} {'dA':>9s}")
    for path in paths:
        boxes = physical.boxes_for(path)
        if len(boxes) == 0:
            continue
        merged, t_merge = _timed(lambda: _merge(boxes, gap), args.repeat)
        area, t_area = _timed(lambda: contour.contour_area(boxes, gap), args.repeat)
        loops, t_loops = _timed(
            lambda: contour.contour_loops(boxes, gap), args.repeat)
        ref, _ = _timed(lambda: contour._union(boxes, gap).area, 1)
        diff = area - ref
        per_node[path] = (len(boxes), len(merged), t_area)
        print(f"{path:34s} {len(boxes):8d} {len(merged):7d} "
              f"{t_merge * 1000:8.2f}ms {t_area * 1000:8.2f}ms "
              f"{len(loops):8d} {_loop_points(loops):7d} {diff:9.2e}")
        if abs(diff) > 1e-9 * max(1.0, abs(ref)):
            failures.append(f"sweep/shapely area mismatch on {path}: {diff}")

    # All hierarchy densities, sequential, as the tree would ask for them.
    physical.clear_contour_cache()
    values = {}
    t0 = time.perf_counter()
    for path in paths:
        values[path] = physical.density_for(path)
    t_all = time.perf_counter() - t0
    print(f"\nall {len(paths)} hierarchy densities: {t_all * 1000:.0f} ms")

    # Initial visible set: root and first-level children passing the default threshold.
    root = design.roots[0]
    visible = [root] + [child for child in design.children.get(root, [])
                        if float(design.hier.loc[child, "count"]) >= 100]
    physical.clear_contour_cache()
    t0 = time.perf_counter()
    for path in visible:
        physical.density_for(path)
    t_initial = time.perf_counter() - t0
    print(f"initial visible set ({len(visible)} nodes): {t_initial * 1000:.0f} ms CPU")

    # Optional scale probe on the largest node's boxes.
    if args.scale > 1:
        largest = max(per_node, key=lambda p: per_node[p][0])
        boxes = physical.boxes_for(largest)
        x0, _, x1, _ = physical.extent
        shift = (x1 - x0 + 10.0)
        big = np.concatenate([
            boxes + np.array([i * shift, 0.0, i * shift, 0.0], dtype=boxes.dtype)
            for i in range(args.scale)])
        merged, t_merge = _timed(lambda: _merge(big, gap), args.repeat)
        area, t_area = _timed(lambda: contour.contour_area(big, gap), args.repeat)
        print(f"\nscale {args.scale}x on {largest}: {len(big):,} boxes, "
              f"{len(merged):,} merged; merge {t_merge * 1000:.0f} ms, "
              f"area {t_area * 1000:.0f} ms "
              f"({t_area / len(big) * 1e6:.3f} us/box)")
        if args.shapely:
            ref, t_ref = _timed(lambda: contour._union(big, gap).area, 1)
            print(f"  shapely area {t_ref * 1000:.0f} ms, diff {area - ref:.2e}")
            if abs(area - ref) > 1e-9 * max(1.0, abs(ref)):
                failures.append(f"scaled sweep/shapely mismatch: {area - ref}")

    if args.check:
        root_area = per_node.get(root, (0, 0, 0.0))[2] * 1000
        smallest = min((v[2] for v in per_node.values()), default=0.0) * 1000
        checks = [
            ("root area <= 250 ms", root_area),
            ("smallest node <= 1 ms", smallest),
            ("all densities <= 0.9 s", t_all * 1000),
        ]
        print()
        for label, value in checks:
            ok = value <= {"root area <= 250 ms": 250.0,
                           "smallest node <= 1 ms": 1.0,
                           "all densities <= 0.9 s": 900.0}[label]
            print(f"{'PASS' if ok else 'FAIL'}  {label}: {value:.2f}")
            if not ok:
                failures.append(f"{label}: {value:.2f}")
        if failures:
            print("\nfailures:")
            for failure in failures:
                print(" -", failure)
            return 1
        print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
