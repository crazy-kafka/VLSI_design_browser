"""One-off end-to-end check: jobs=4 (byte ranges) == sequential, on the sample.

Run:  python dev_plan/code_sample/check_ranges_e2e.py
Needs the __main__ guard on Windows: the pool's workers re-import this module.
"""
import contextlib
import io

import numpy as np

from vlsi_viewer import parallel
from vlsi_viewer.metal import build_metal


def main():
    # Force the pool on the small sample: this is what _force_pool does in the tests.
    parallel.BYTES_PER_WORKER = 1
    args = (["sample_data/metal/top.def", "sample_data/metal/sub.def"],
            ["sample_data/metal/cells.lef"], ["sample_data/metal/tech.lef"])
    with contextlib.redirect_stdout(io.StringIO()):
        seq = build_metal(*args, grid_size=10.0, jobs=1)
    with contextlib.redirect_stdout(io.StringIO()):
        ranged = build_metal(*args, grid_size=10.0, jobs=4)  # >= RANGE_MIN_JOBS
    assert ranged.totals == seq.totals, {
        k: (ranged.totals[k], seq.totals[k])
        for k in ranged.totals if ranged.totals[k] != seq.totals[k]}
    assert ranged.stats["forms"] == seq.stats["forms"]
    assert ranged.stats["lines"] == seq.stats["lines"]
    names = [layer.name for layer in seq.layers]
    a = np.concatenate([seq.heat(f"L:{n}").ravel() for n in names])
    b = np.concatenate([ranged.heat(f"L:{n}").ravel() for n in names])
    assert np.allclose(a, b, rtol=1e-6, atol=1e-6)
    print("jobs=4 byte-range build == sequential build (counters exact, grids allclose)")


if __name__ == "__main__":
    main()
