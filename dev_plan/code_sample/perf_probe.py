"""One-off measurements behind the performance plan (dev_plan/perf_plan_contour_metal.md).

Run:  python perf_probe.py [contour|gil|def]
Synthetic shapes only; no design data.
"""
import sys
import time

import numpy as np


def synth_boxes(n, seed=7):
    """Rows of abutting std cells with row gaps, like a real placement."""
    rng = np.random.default_rng(seed)
    w, h, gap_y = 1.0, 2.0, 1.0
    per_row = int(np.sqrt(n))
    rows = n // per_row
    x0 = np.tile(np.arange(per_row) * w, rows)[:n]
    y0 = np.repeat(np.arange(rows) * (h + gap_y), per_row)[:n]
    n = len(x0)
    # a few macros scattered
    x1 = x0 + w
    y1 = y0 + h
    boxes = np.column_stack([x0, y0, x1, y1]).astype(np.float64)
    # sprinkle jittered overlap so the merge has something to do
    idx = rng.choice(n, n // 20, replace=False)
    boxes[idx, 0] -= 0.5
    return boxes


def merge_boxes_np(boxes):
    """Same two-pass run-merge as contour.merge_boxes, pure numpy (no pandas)."""
    arr = np.round(np.asarray(boxes, dtype=float), 9)
    if arr.size == 0:
        return np.empty((0, 4))

    def runs(a, keys, s, hi):
        # sort by keys + start col
        order = np.lexsort((a[:, s], a[:, keys[1]], a[:, keys[0]]))
        b = a[order]
        # group boundaries on keys
        new_grp = np.ones(len(b), dtype=bool)
        new_grp[1:] = (b[1:, keys[0]] != b[:-1, keys[0]]) | (b[1:, keys[1]] != b[:-1, keys[1]])
        grp = np.cumsum(new_grp)
        run_max = np.maximum.accumulate(np.where(new_grp, -np.inf, 0.0) + b[:, hi])
        # running max must reset per group: use segment-reduce trick
        run_max = b[:, hi].copy()
        np.maximum.accumulate(run_max, out=run_max)
        # correct per-group cummax
        starts = np.flatnonzero(new_grp)
        for st in starts[1:]:
            np.minimum(run_max[st - 1], 0)  # noop marker
        # simpler exact approach: loop groups (few groups relative to rows)
        prev = np.empty(len(b))
        m = -np.inf
        gi = 0
        out_seg = np.empty(len(b), dtype=np.int64)
        for i in range(len(b)):
            if new_grp[i]:
                m = -np.inf
                gi += 1
            prev[i] = m
            if b[i, hi] > m:
                m = b[i, hi]
        seg = np.cumsum(b[:, s] > prev) + gi * 0  # segment id within group
        # merge rows with same (group, seg): min start, max hi
        key = grp * (seg.max() + 1) + seg
        uniq, inv = np.unique(key, return_inverse=True)
        lo = np.minimum.reduceat(b[:, s], np.flatnonzero(np.r_[True, inv[1:] != inv[:-1]]))
        hi2 = np.maximum.reduceat(b[:, hi], np.flatnonzero(np.r_[True, inv[1:] != inv[:-1]]))
        first = np.flatnonzero(np.r_[True, inv[1:] != inv[:-1]])
        return b[first][:, keys[0]], b[first][:, keys[1]], lo, hi2

    # pass 1: merge x within (y0, y1)
    y0, y1, x0, x1 = runs(arr, (1, 3), 0, 1)  # keys y0,y1 ; start x0 ; hi x1
    mid = np.column_stack([x0, y0, x1, y1])
    # pass 2: merge y within (x0, x1)
    order = np.argsort(mid[:, 0], kind="stable")
    mid = mid[order]
    x0b, x1b, y0b, y1b = runs(mid, (0, 2), 1, 3)  # keys x0,x1 ; start y0 ; hi y1
    return np.column_stack([x0b, y0b, x1b, y1b])


def sweep_union_area(rects):
    """Exact union area of axis-aligned rects via x-sweep, numpy-batched per segment."""
    a = np.asarray(rects, dtype=np.float64)
    if a.size == 0:
        return 0.0
    xs = np.unique(a[:, [0, 2]])
    total = 0.0
    # event sweep: for each x slab, union of y-intervals active
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        m = (a[:, 0] <= x0) & (a[:, 2] >= x1)
        if not m.any():
            continue
        ys = np.sort(a[m][:, [1, 3]].ravel())
        # merge y intervals
        y0s = a[m][:, 1]
        y1s = a[m][:, 3]
        order = np.argsort(y0s)
        y0s, y1s = y0s[order], y1s[order]
        cum = np.maximum.accumulate(y1s)
        prev = np.r_[-np.inf, cum[:-1]]
        new = y0s > prev
        seg_hi = np.maximum.reduceat(y1s, np.flatnonzero(new))
        seg_lo = y0s[new]
        total += (x1 - x0) * float((seg_hi - seg_lo).sum())
    return total


def bench_contour():
    from vlsi_viewer import contour
    print("== contour: merge_boxes (pandas) vs numpy, union cost ==")
    for n in (100_000, 1_000_000, 3_000_000):
        boxes = synth_boxes(n)
        t = time.perf_counter()
        merged = contour.merge_boxes(boxes)
        t_pd = time.perf_counter() - t
        t = time.perf_counter()
        from shapely.geometry import box as sb
        from shapely.ops import unary_union
        g = unary_union([sb(*b) for b in merged])
        area_sh = g.area
        t_un = time.perf_counter() - t
        m = np.asarray(merged)
        t = time.perf_counter()
        area_sw = sweep_union_area(m)
        t_sw = time.perf_counter() - t
        print(f"N={n:>9,}  merged->{len(merged):>6,}  "
              f"merge_boxes(pandas) {t_pd:7.3f}s  unary_union {t_un:6.3f}s  "
              f"sweep-area {t_sw:6.3f}s  area match: {abs(area_sh - area_sw) < 1e-6 * max(1, area_sh)}")


def bench_gil():
    """How much does a background merge_boxes / unary_union slow a GUI-like loop?"""
    import threading
    from vlsi_viewer import contour
    boxes = synth_boxes(1_000_000)

    def gui_like(seconds):
        end = time.perf_counter() + seconds
        ticks = 0
        worst = 0.0
        last = time.perf_counter()
        while time.perf_counter() < end:
            # ~60fps paint tick: a little python work then yield
            sum(i * i for i in range(200))
            ticks += 1
            now = time.perf_counter()
            worst = max(worst, now - last)
            last = now
            time.sleep(0.001)
        return ticks, worst

    def worker_merge(stop):
        while not stop.is_set():
            contour.merge_boxes(boxes)

    def worker_union(stop):
        from shapely.geometry import box as sb
        from shapely.ops import unary_union
        merged = contour.merge_boxes(boxes)
        geoms = [sb(*b) for b in merged]
        while not stop.is_set():
            unary_union(geoms)

    for name, fn, n_th in (("solo", None, 0), ("+ 1 merge_boxes thread", worker_merge, 1),
                           ("+ 4 merge_boxes threads", worker_merge, 4),
                           ("+ 1 unary_union thread", worker_union, 1),
                           ("+ 4 unary_union threads", worker_union, 4)):
        stop = threading.Event()
        ths = []
        if fn:
            for _ in range(n_th):
                th = threading.Thread(target=fn, args=(stop,), daemon=True)
                th.start()
                ths.append(th)
        ticks, worst = gui_like(2.0)
        if ths:
            stop.set()
            for th in ths:
                th.join()
        print(f"{name:>26}: gui ticks {ticks:4d}/2s  worst tick gap {worst*1000:6.1f} ms")


def bench_def():
    from vlsi_viewer.parsers.DEF.compiledRe import CompiledRe
    print("== DEF: regex scan cost per character ==")
    rng = np.random.default_rng(1)
    # typical special-wiring statement: ROUTED forms + long VIA arrays
    forms = []
    for i in range(300):
        layer = f"M{1 + i % 8}"
        n_pts = 512 if i % 3 else 8
        pts = " ".join(f"( {int(v)} {int(w)} )" for v, w in
                       zip(rng.integers(0, 10**7, n_pts), rng.integers(0, 10**7, n_pts)))
        if i % 3 == 0:
            forms.append(f"+ ROUTED {layer} 140 {pts} ")
        else:
            forms.append(f"+ VIA VIA{1 + i % 5} {pts} ")
    statement = "- VDD ( u1 A ) " + "".join(forms) + "+ USE POWER"
    n_char = len(statement)
    print(f"statement {n_char/1e6:.2f} MB")

    t = time.perf_counter()
    n = 0
    for m in CompiledRe.re_special_wiring_form.finditer(statement):
        n += 1
    dt = time.perf_counter() - t
    print(f"re_special_wiring_form.finditer: {dt:6.3f}s  {n} forms  {dt/n_char*1e9:5.1f} ns/char")

    # token scan over a tail
    tail = " ".join(f"( {int(v)} {int(w)} )" for v, w in
                    zip(rng.integers(0, 10**7, 4000), rng.integers(0, 10**7, 4000)))
    t = time.perf_counter()
    toks = 0
    for _ in CompiledRe.re_wire_token.finditer(tail):
        toks += 1
    dt = time.perf_counter() - t
    print(f"re_wire_token.finditer:        {dt:6.3f}s  {toks} tokens  {dt/len(tail)*1e9:5.1f} ns/char")

    # alternative: single simple point regex over the same tail
    re_pts_only = CompiledRe.re_pt
    t = time.perf_counter()
    pts = re_pts_only.findall(tail)
    dt = time.perf_counter() - t
    print(f"re_pt.findall (points only):   {dt:6.3f}s  {len(pts)} pts   {dt/len(tail)*1e9:5.1f} ns/char")

    # alternative: numpy bulk integer extraction
    import re as _re
    re_ints = _re.compile(r"-?\d+")
    t = time.perf_counter()
    vals = re_ints.findall(tail)
    ints = np.array(vals, dtype=np.int64)
    dt = time.perf_counter() - t
    print(f"ints findall + np.array:       {dt:6.3f}s  {len(ints)} ints  {dt/len(tail)*1e9:5.1f} ns/char")

    # non-wiring clause scan over the full statement (the __split_statement pass)
    t = time.perf_counter()
    cut = CompiledRe.re_non_wiring_clause.search(statement, 20)
    dt = time.perf_counter() - t
    print(f"re_non_wiring_clause.search:   {dt:6.3f}s  {dt/n_char*1e9:5.1f} ns/char")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("contour", "all"):
        bench_contour()
    if which in ("gil", "all"):
        bench_gil()
    if which in ("def", "all"):
        bench_def()
