"""Time the pin-density pass, on the real DEF's own cell mix, at any instance count.

    python sample_data/bench_pin_density.py --scale 500     # ~234k instances
    python sample_data/bench_pin_density.py --scale 7173    # the chip-level design's 3.36M

The pass is vectorised per block and orientation, so its cost is linear in the number of
*pin points* - one per pin of every placed instance - not in the number of instances. A
small design therefore measures almost nothing but the per-block overhead, which is why
this replicates the real DEF's instances (its cells, orientations and pin counts, and the
real design's die) until the point count is the one being asked about. That is a fixture
for a performance question, not a layout: where a tile lands and what overlaps is
irrelevant, and the cell mix is a real one.

``--scale 1`` is the untouched DEF, and is the check that the real parse path is what runs.
"""
import argparse
import ctypes
import ctypes.wintypes
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vlsi_viewer.parsers.convert import cell_info_from_lef, instance_info_from_def
from vlsi_viewer.physical import build_physical

NANGATE = "sample_data/real/nangate45"
LEF = f"{NANGATE}/NangateOpenCellLibrary.macro.mod.lef"
DEF = f"{NANGATE}/gcd_nangate45.def"

# The die of the chip-level design this mode is used on, and its instance count
# (dev_plan/issue/real_design_log_0916.md): 1060.2 x 1226.64 um, 3,355,697 instances.
REAL_DIE = (1060.2, 1226.64)
REAL_INSTANCES = 3355697


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.wintypes.DWORD), ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _mem_info():
    """The Windows pair of VmRSS and VmHWM, with the handle types ctypes needs to work."""
    kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(_PMC),
                                           ctypes.wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL

    def read():
        c = _PMC()
        c.cb = ctypes.sizeof(c)
        psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return c.WorkingSetSize / 1e6, c.PeakWorkingSetSize / 1e6
    return read


rss_mb = _mem_info()


def replicate(block, scale, seed=20260916):
    """``block``'s instances, ``scale`` times over, scattered across the real design's die."""
    instances = block["instances"]
    if scale == 1:
        return block
    rng = np.random.default_rng(seed)
    offsets = rng.random((scale, 2)) * np.array(REAL_DIE)
    out = {}
    for tile in range(scale):
        ox, oy = float(offsets[tile][0]), float(offsets[tile][1])
        for name, attrs in instances.items():
            row = dict(attrs)
            row["location_x"] = float(row.get("location_x", 0.0)) + ox
            row["location_y"] = float(row.get("location_y", 0.0)) + oy
            out[f"{name}_{tile}"] = row
    return {"top_name": block["top_name"], "boundary": [(0, 0), REAL_DIE], "instances": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=1,
                    help=f"how many times to replicate the DEF's instances "
                         f"({REAL_INSTANCES} is the chip-level design)")
    ap.add_argument("--grid", type=float, default=3.0)
    args = ap.parse_args()

    t0 = time.perf_counter()
    cells, pins = cell_info_from_lef([LEF], with_pins=True)
    t_lef = time.perf_counter() - t0
    print(f"LEF: {len(cells)} cell(s), {len(pins)} with signal pin(s), "
          f"{sum(len(v) for v in pins.values())} pin(s), {t_lef:.3f}s")

    t0 = time.perf_counter()
    block = replicate(instance_info_from_def(DEF), args.scale)
    n_inst = len(block["instances"])
    print(f"DEF: {n_inst:,} instance(s) at scale {args.scale}, {time.perf_counter() - t0:.1f}s")

    base, peak0 = rss_mb()
    t0 = time.perf_counter()
    data = build_physical([block], cells, grid_size=args.grid, pins=pins)
    t_build = time.perf_counter() - t0
    built, peak1 = rss_mb()
    print(f"build: {t_build:.2f}s, grid {data.rows} x {data.cols}, "
          f"rss {base:.0f} -> {built:.0f} MB (peak {peak1:.0f})")

    assert data._pins is None, "the pin grid must not be built during the build"
    t0 = time.perf_counter()
    grid = data.heat("pins")
    t_pins = time.perf_counter() - t0
    after, peak2 = rss_mb()
    total = float(grid.sum())

    print(f"pins: {total:,.0f} point(s) for {n_inst:,} instance(s) = "
          f"{total / n_inst:.2f} per instance")
    print(f"      {t_pins:.2f}s  ({1e6 * t_pins / max(1.0, total):.3f} s per million point(s)); "
          f"busiest grid cell {grid.max():.0f} pin(s)")
    print(f"      rss {built:.0f} -> {after:.0f} MB, peak {peak2:.0f} MB "
          f"(the pass adds {after - built:.0f} MB over the build)")

    if n_inst >= REAL_INSTANCES:
        return
    per = total / n_inst
    rate = t_pins / max(1.0, total)
    print(f"\nprojection for {REAL_INSTANCES:,} instances at this mix "
          f"({per:.2f} pin(s)/instance, {REAL_INSTANCES * per / 1e6:.1f} M points): "
          f"{REAL_INSTANCES * per * rate:.2f}s")
    for extra in (6.0, 10.0):
        t = REAL_INSTANCES * extra * rate
        print(f"      {extra:5.2f} pin(s)/instance -> "
              f"{REAL_INSTANCES * extra / 1e6:7.1f} M point(s) -> {t:6.2f}s")


if __name__ == "__main__":
    main()
