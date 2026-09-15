"""Measure what byte-range work units cost and save, before any of it becomes the default.

The question this answers is narrow and answerable: the routing stage spends 211 s per worker
scanning the whole file to keep one statement in eight, and spends its critical path on one power
net that is 20 % of the file and one work unit. Byte ranges replace the first with one cheap scan
in the parent and the second with packing by bytes - and this measures both, on fixtures built to
the real design's shape by `generate_metal --real-shape`.

It is deliberately not a summary of a summary: every number it prints is a wall clock, a line
count, a byte count or a counter, and the equivalence lines are exact counter comparisons rather
than tolerances, because a range build that produces a different map is not a slower build.

    python sample_data/metal/bench_work_units.py            # both fixtures, jobs up to 8
    python sample_data/metal/bench_work_units.py --jobs 16  # up to the machine's cores
"""
import argparse
import contextlib
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np                                                    # noqa: E402

from vlsi_viewer import parallel                                      # noqa: E402
from vlsi_viewer.metal import build_metal                             # noqa: E402
from vlsi_viewer.parallel import Reader, pack_ranges, scan_work_units  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# Two shapes, because the two terms being fixed respond to different ones. "many small
# statements" is the imbalance-free case, where the per-worker scan is the whole story; "one giant
# statement" is the real design's shape, where a single net is a large share of the file.
# The instance count is deliberately small: components are read in the *parent*, before any pool
# exists, so a fixture with a realistic instance count spends most of its wall in a stage nothing
# here changes - the real design's components stage was 44 s of a 1,780 s routing stage, and a
# fixture that put 12 s of a 41 s wall there would drown out the thing being measured.
FIXTURES = {
    "many small statements": dict(nets=20000, instances=20000, via_forms=2000, via_points=4,
                                  lines_per_form=1, via_nets=300),
    # The giant statement is sized to the real design's share of the file - 58.5 M of 284.9 M
    # lines, 20 % - because that share is the floor the whole change runs into: whatever else
    # improves, one worker still parses all of it.
    "one giant statement": dict(nets=20000, instances=20000, via_forms=6000, via_points=4,
                                lines_per_form=4, via_nets=1),
}


def _fixture(name, settings, out_dir):
    """Write one shaped DEF, reusing the generator the other fixtures come from."""
    import generate_metal

    path = os.path.join(out_dir, "real_shape.def")
    if os.path.exists(path):
        os.unlink(path)
    with contextlib.redirect_stdout(io.StringIO()):
        generate_metal.real_shape(out_dir, gzip_out=False, gc_mode="default", profile=False,
                                  **settings)
    return path


def _measure(fixture, jobs, ranges, tech_path, work_dir):
    """One build, timed, with what the workers reported about themselves."""
    captured = {}

    def wrapper(*args, **kwargs):
        result = _REAL_PARSE_PARALLEL(*args, **kwargs)
        captured["note"] = result[2]
        return result

    real_units = parallel.RANGE_WORK_UNITS
    parallel.parse_parallel = wrapper
    parallel.RANGE_WORK_UNITS = ranges
    try:
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            data = build_metal([fixture], [os.path.join(HERE, "cells.lef")], [tech_path],
                               grid_size=10.0, jobs=jobs, work_dir=work_dir)
        wall = time.perf_counter() - started
    finally:
        parallel.parse_parallel = _REAL_PARSE_PARALLEL
        parallel.RANGE_WORK_UNITS = real_units
    return data, wall, captured.get("note", {})


# Captured before anything wraps it: reading it inside the wrapper would find the wrapper.
_REAL_PARSE_PARALLEL = parallel.parse_parallel


def _scan_costs(path, lines):
    """The statement logic each worker runs today against the scan that replaces it."""
    started = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        for _section, _lines in Reader(path).statements():
            pass
    per_worker = time.perf_counter() - started
    started = time.perf_counter()
    units = scan_work_units(path)
    scan = time.perf_counter() - started
    return per_worker / lines * 1e6, scan / lines * 1e6, units


def _heat(data):
    layers = [layer.name for layer in data.layers]
    data.set_scope("all")
    return np.asarray(data.heat(data.group_kind(layers)), dtype=np.float64)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8, help="highest worker count to try")
    parser.add_argument("--out-dir", default=None, help="where to write the fixtures")
    parser.add_argument("--only", default=None, help="one fixture by name")
    parser.add_argument("--scale", type=int, default=1,
                        help="multiply every fixture's statement and instance counts")
    args = parser.parse_args(argv)
    if args.scale > 1:
        for settings in FIXTURES.values():
            for key in ("nets", "instances", "via_forms"):
                settings[key] *= args.scale
    out_dir = args.out_dir or os.path.join(HERE, "bench")
    os.makedirs(out_dir, exist_ok=True)
    tech_path = os.path.join(HERE, "tech.lef")
    jobs_to_try = [n for n in (1, 2, 4, 8, 16) if n <= args.jobs]

    # The pool is sized from the input unless this is zero, and a benchmark that silently ran in
    # one process would compare a sequential build with a sequential build.
    parallel.BYTES_PER_WORKER = 0

    for name, settings in FIXTURES.items():
        if args.only and args.only != name:
            continue
        fixture = _fixture(name, settings, out_dir)
        lines = sum(1 for _ in open(fixture, "rb"))
        size_mb = os.path.getsize(fixture) / 1e6
        per_worker_us, scan_us, units = _scan_costs(fixture, lines)
        print(f"\n=== {name}: {lines:,} lines, {size_mb:.1f} MB, "
              f"{len(units.starts):,} statement(s)")
        print(f"    statement logic per worker : {per_worker_us:.3f} us/line  "
              f"({per_worker_us * lines / 1e6:.2f} s over this file)")
        print(f"    the scan that replaces it  : {scan_us:.3f} us/line  "
              f"({scan_us * lines / 1e6:.2f} s) - {per_worker_us / scan_us:.1f}x cheaper")
        largest = max((b - a for a, b in zip(units.starts, units.starts[1:])), default=0)
        print(f"    largest statement          : {largest:,} bytes "
              f"({100.0 * largest / units.size:.1f} % of the file)")

        sequential, seq_wall, _note = _measure(fixture, 1, False, tech_path, out_dir)
        reference = _heat(sequential)
        print(f"\n    {'mode':8} {'jobs':>4} {'wall s':>9} {'speedup':>8} "
              f"{'per-worker s':>16} {'per-worker MB':>14} {'read MB':>9}  equivalent")
        print(f"    {'sequential':8} {1:>4} {seq_wall:>9.2f} {1.0:>7.2f}x "
              f"{'-':>16} {'-':>14} {size_mb:>9.1f}  reference")
        for ranges in (False, True):
            for jobs in jobs_to_try:
                if jobs == 1:
                    continue                     # with one worker the two modes are the same
                data, wall, note = _measure(fixture, jobs, ranges, tech_path, out_dir)
                workers = note.get("worker_seconds") or []
                span = (f"{min(workers):.1f}/{max(workers):.1f}" if workers else "     -")
                rss = [value for value in (note.get("worker_rss_mb") or [])
                       if value is not None]
                rss_span = f"{max(rss):.0f}" if rss else "n/a"
                read = note.get("read_bytes", 0) / 1e6
                same = (data.totals == sequential.totals
                        and data.stats["forms"] == sequential.stats["forms"]
                        and data.stats["lines"] == sequential.stats["lines"])
                close = np.allclose(_heat(data), reference, rtol=1e-6, atol=1e-6)
                print(f"    {'ranges' if ranges else 'stride':8} {jobs:>4} {wall:>9.2f} "
                      f"{seq_wall / wall:>7.2f}x {span:>16} {rss_span:>14} {read:>9.1f}  "
                      f"{'yes' if same and close else 'NO'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
