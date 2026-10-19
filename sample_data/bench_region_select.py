"""Time the region-selection pass at three selection sizes.

    python sample_data/bench_region_select.py

Builds the bundled ~100 k-instance physical sample, then measures RegionData
construction (the O(N) mask), the root's raw stats, its metrics, and the child
batch, and projects the per-box cost to the 3.35 M-instance chip-level design
from dev_plan/issue/real_design_log_0921.md.
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vlsi_viewer.metrics import build_design
from vlsi_viewer.physical import build_physical
from vlsi_viewer.region import RegionData, RegionSelection

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "physical")
BLOCKS = [os.path.join(SAMPLE, name) for name in
          ("instance_info.json", "CORE.json", "IFU.json", "IEX.json", "LSU.json")]
CELLS = os.path.join(SAMPLE, "cell_info.json")
REAL_INSTANCES = 3_355_697


def _selection(physical, fraction):
    """A centered square covering ``fraction`` of the die area.

    The whole-die case is expanded by 1 um so boxes lying exactly on the boundary
    (and macros overhanging it) are fully inside, matching the design metrics.
    """
    x0, y0, x1, y1 = physical.extent
    side = fraction ** 0.5
    # Center on the densest tile: the sample is clustered, and a small region at
    # the geometric center can contain no instances at all. This is the "hotspot"
    # case the feature is for.
    ix, iy = np.unravel_index(np.argmax(physical.density), physical.density.shape)
    cx = x0 + (ix + 0.5) * physical.grid_size
    cy = y0 + (iy + 0.5) * physical.grid_size
    hw, hh = (x1 - x0) * side / 2.0, (y1 - y0) * side / 2.0
    pad = 1.0 if fraction >= 1.0 else 0.0
    return RegionSelection((cx - hw - pad, cy - hh - pad,
                            cx + hw + pad, cy + hh + pad), 0, 0, 0, 0)


def _timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def main():
    design, t_design = _timed(lambda: build_design(BLOCKS, CELLS))
    physical, t_physical = _timed(
        lambda: build_physical(BLOCKS, CELLS, grid_size=3.0))
    n = len(physical._geom)
    root = design.roots[0]
    children = design.children.get(root, [])
    print(f"sample: {n:,} boxes, {len(design.hier)} hierarchy nodes, "
          f"grid {physical.rows} x {physical.cols}")
    print(f"build_design {t_design:.2f}s, build_physical {t_physical:.2f}s "
          f"(grid 3.0 um)")

    for label, fraction in (("1%", 0.01), ("10%", 0.10), ("whole die", 1.0)):
        region, t_build = _timed(
            lambda: RegionData(physical, design, _selection(physical, fraction)))
        t_stats = _timed(lambda: region.stats(root))[1]
        t_metrics = _timed(lambda: region.metric_values(root))[1]
        t_children = _timed(lambda: region.prefetch(children))[1]
        memory = region._idx.nbytes + region._frac.nbytes
        k = region.selected_count
        projected = t_build * REAL_INSTANCES / n
        print(f"\n{label}: K={k:,} selected")
        print(f"  RegionData (mask + idx + fractions) {t_build * 1000:.2f} ms "
              f"({t_build / n * 1e6:.3f} us/box; projected "
              f"{projected * 1000:.0f} ms at {REAL_INSTANCES:,})")
        print(f"  root stats {t_stats * 1000:.2f} ms, metrics {t_metrics * 1000:.2f} ms, "
              f"child batch ({len(children)} path(s)) {t_children * 1000:.2f} ms")
        print(f"  idx+frac memory {memory / 1e6:.2f} MB "
              f"(projected {(region._idx.nbytes + region._frac.nbytes) / max(k, 1) * REAL_INSTANCES / 1e6:.1f} MB "
              f"at {REAL_INSTANCES:,} selected)")


if __name__ == "__main__":
    main()
