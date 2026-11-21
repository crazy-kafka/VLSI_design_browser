Metal-mode turnaround time bottleneck analysis and speedup proposals for 10⁷–10⁸ metal shapes
## Symptom

In metal mode, a run on a merged chip-level DEF (~34M+ lines, `.gz`) appears stuck during
"reading routing": the last log line is `Read DEF 34000000 lines` and nothing else prints
for many minutes, while the job stays `RUNNING` with one core at 100% CPU.

Log excerpt (end of visible output):

```
Parsing lefs/HIS6LC956CSRAMP32X27M1HSB.lef
... (221 LEF files) ...
End parsing 221 LEF file in 10.16s
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 4 layer(s); ...
INFO vlsi_viewer.cli: metal: reading routing in lx956c_ioe
Load DEF file /tmpdata/.../DATAOUT/lx956c_ioe.def.gz
Read DEF 1000000 lines
...
Read DEF 34000000 lines
<silence, cursor only>
```

Job stats snapshot at that point:

```
TASK_STATE            RUNNING
TASK[0].PID           121468,121470
REQ_CPU / REQ_MEM     4 / 20000
CPU_UTIL_RECENT(%)    100        <- one core fully busy
USER_CPU_TIME / MRUN  492 / 500  <- wall time ~= CPU time
SWAP                  0          <- no thrashing
RSS / MEM_MAX         18877 / 19146 MB   <- ~1 GB below the 20 GB request
```

## Problem Statement

Metal mode processes the routing wires of real VLSI designs to produce per-layer utilization
heatmaps. Real designs carry **10⁷–10⁸ wire segments**, and at that scale the current pipeline
spends minutes building the grids before the GUI appears. This document analyzes where the time
goes and proposes concrete changes, ranked by impact.

---

## Current Pipeline

```
DEF files (Pass 1) → block hierarchy + capacity grids
DEF files (Pass 2) → DefParser (line-by-line Python, per-wire regex)
                   → DefWire/DefSWire Python objects
                   → ShapeStream (Python list accumulation per shape)
                   → _GridSink → Bins (np.repeat piece expansion per shape)
                   → MetalData (heat maps composed on demand from cached grids)
```

Everything upstream of the Qt event loop runs synchronously — the window does not exist yet.

---

## Bottleneck Ranking

### 🔴 #1 — DEF Parser line-by-line Python loop (dominant)

**Where:** `vlsi_viewer/parsers/DEF/defParser.py`, `__extractNets()` L538,
`__extractSpecialNets()` L521

**What:** The parser reads the DEF line-by-line in Python (`fetchLine()` L616), matching each
line against regexes, and constructing `DefWire` / `DefSWire` Python objects for every segment.
The as-built doc confirms **half of all segments are zero-length via points** — correctly
dropped later, but the parse cost for them is still paid.

**Scale:** The plan estimates ~1000 s for 10⁸ wiring statements in parsing alone, before any
rasterization.

```
While loop (Python) per line
  → regex match per line (Python)
  → __read_statement joins lines (Python string ops)
  → __scan_tokens tokenizes coordinates (re.finditer + Python tuple creation)
  → DefWire/DefSWire object allocation per segment (Python)
  → sink(net) immediately discards the object — but the allocation already happened
```

**Why the sink pattern helps but doesn't fix it:** The sink discards nets after parsing, so
peak memory stays flat. But every segment still goes through Python object creation and every
coordinate still goes through Python string parsing.

---

### 🔴 #2 — ShapeStream Python list accumulation per shape

**Where:** `vlsi_viewer/parsers/routing.py`, `ShapeStream._emit()` L257

**What:** For every wire segment, `_emit` appends four float values to Python lists
(`bucket[0].append(x0)`, etc.). At 10⁸ shapes that is **4×10⁸ `list.append` calls**. The
lists are converted to numpy arrays only at `flush()` (every 65536 shapes), paying an
additional copy.

```
Per shape:
  _emit → list.append(x0), list.append(y0), list.append(x1), list.append(y1)  (4 Python calls)
  _add_wire → Python arithmetic for keep-out expansion, jog checking, corner sorting
  _is_jog → computes span in microns (unnecessary division before the check)
```

---

### 🟡 #3 — Bins rasterizer piece expansion overhead

**Where:** `vlsi_viewer/raster.py`, `_pieces_in_window()` L163

**What:** Each rectangle is split at bin boundaries into per-bin pieces via ~9 `np.repeat`
calls per window, creating temporary arrays that are immediately consumed by `bincount`. For
routing geometry a segment touches 2–6 bins, so the expansion factor is small. But with 10⁸
shapes, even 3 pieces per shape is 3×10⁸ piece expansions. The difference-array scheme was
measured and **rejected** as slower for routing geometry (recorded in `raster.py` L19–31 and
the as-built doc), so this path is already the faster of the two — but the constant factor of
`np.repeat` still matters.

---

### 🟡 #4 — Synchronous startup (no GUI until build completes)

**Where:** `vlsi_viewer/cli.py`, `_run_metal()` L254

**What:** `build_metal()` runs before `QApplication` is created and before any window is shown.
The plan document and CLI code both acknowledge this as the same "stuck GUI at launch" pattern
the physical-mode performance review identified.

---

### 🟢 #5 — Two-pass DEF reading (minor for flat designs)

**Where:** `vlsi_viewer/metal.py`, `build_metal()` L388–473

**What:** DEF files are read twice: Pass 1 reads only components (stops at `END COMPONENTS`),
Pass 2 reads the full file including wiring. For a single flat DEF the component section is
negligible, so the double I/O cost is small. For gzipped files the decompression cost is paid
twice. For hierarchical designs the two passes are required (sub-block frames must be known
before their wiring can be placed).

---

## Proposed Changes (ordered by impact)

### ✅ Proposal 1 — Block-mode DEF parsing

**Estimated impact:** 3–5× parsing speedup &nbsp;|&nbsp; **Effort:** Medium

Replace the line-by-line `fetchLine()` loop over NETS/SPECIALNETS with block-based regex
scanning:

- Read the section in large blocks (e.g. 1 MB at C speed via `fh.read()`)
- Use `re.finditer` over the block to locate net boundaries (`- netname`)
- The wiring-form regexes (`re_regular_wiring_form`, `re_special_wiring_form`) already use
  `finditer` over statement text — the bottleneck is the outer line-by-line loop

```python
# Current: Python call per line
while line and 'END NETS' not in line:
    if CompiledRe.re_net.search(line):
        statement, line = self.__read_statement(line)  # more Python line-by-line
        ...

# Proposed: block-mode at C speed
block = self.fh.read(1 << 20)
for match in CompiledRe.re_net.finditer(block):
    # extract statement spanning match.start() to next match boundary
    ...
```

**Files:** `vlsi_viewer/parsers/DEF/defParser.py`

---

### ✅ Proposal 2 — Pre-allocated ring buffers for shape accumulation

**Estimated impact:** 2–3× conversion speedup &nbsp;|&nbsp; **Effort:** Low

Replace `ShapeStream._emit()`'s Python `list.append` with pre-allocated numpy arrays:

```python
# Current: 4×10⁸ Python list.append calls
bucket[0].append(x0)

# Proposed: write directly into pre-allocated (batch_size, 4) float64 slot
bucket[self._slot, 0] = x0
self._slot += 1
if self._slot >= self.batch:
    self.flush()
```

This eliminates 4×10⁸ Python method calls and 4×10⁸ memory allocations. Flush slices the
filled portion without a copy.

**Files:** `vlsi_viewer/parsers/routing.py`

---

### ✅ Proposal 3 — Background build with progress

**Estimated impact:** UX (no algorithmic speedup, but perceived responsiveness) &nbsp;|&nbsp; **Effort:** Low

Move `build_metal()` behind a visible window:

```python
app = QApplication(sys.argv)
win = MainWindow(metal=None)  # empty window immediately
win.show()
# build_metal on QThread, progress → status bar, populate MetalData when done
```

The `on_progress` callback already exists in `build_metal()`.

**Files:** `vlsi_viewer/cli.py`, `vlsi_viewer/ui_main.py`

---

### ✅ Proposal 4 — Fuse frame transform into rasterizer

**Estimated impact:** 1.5–2× raster speedup &nbsp;|&nbsp; **Effort:** Low

Currently `ShapeStream.flush()` applies the frame transform to numpy arrays, then passes them
to `Bins.add_rects()`. Move the transform inside `Bins._add_block()` so it happens after
clipping and before bin-index computation, fusing two passes into one and eliminating
intermediate arrays.

**Files:** `vlsi_viewer/parsers/routing.py`, `vlsi_viewer/raster.py`

---

### ✅ Proposal 5 — Parallel band-based rasterization

**Estimated impact:** ~cores× raster speedup &nbsp;|&nbsp; **Effort:** Medium

Split the grid into horizontal bands; each band accumulates into a disjoint slice of the output
grid with no locks. Dispatch via `QThreadPool` or `concurrent.futures`. A wire segment's bin
pieces all fall into one band (segments span ~1 bin vertically), so bands are naturally
independent.

**Files:** `vlsi_viewer/raster.py`, `vlsi_viewer/metal.py`

---

### ✅ Proposal 6 — Optional Numba JIT for rasterizer hot path

**Estimated impact:** 2–4× raster speedup &nbsp;|&nbsp; **Effort:** Medium

The `_pieces_in_window` path creates ~9 temporary arrays via `np.repeat` per window. A `@njit`
kernel could compute bin indices and areas with flat loops and direct indexing, avoiding those
allocations. Detect `numba` at runtime, fall back to the current numpy path. Keep it optional
(no new hard dependency).

**Files:** `vlsi_viewer/raster.py`

---

## Quick Wins (low effort, immediate benefit)

1. **Bump `DEFAULT_BLOCK`** in `raster.py` from `1<<18` (262K) to `1<<20` (1M) — fewer Python
   loop iterations in `_add_block`, ~80 MB working arrays.

2. **Use `np.stack`** in `ShapeStream.flush()` instead of four separate `np.asarray` calls —
   one allocation instead of four per flush.

3. **Cache `origin_x / grid_size`** etc. in `Bins._add_block` — these float divisions are
   recomputed per block.

4. **Move `_is_jog` check before span division** in `ShapeStream._add_wire` — currently
   computes span in microns (dividing by `db_unit`) before checking if the segment should be
   dropped.

---

## Recommended Order

| # | Proposal | Est. Impact | Effort | Cumulative |
|---|----------|------------|--------|------------|
| 1 | Block-mode DEF parsing | 3–5× parse | Medium | 3–5× |
| 2 | Pre-allocated ring buffers | 2–3× convert | Low | 6–15× |
| 3 | Background build + progress | UX | Low | — |
| 4 | Fused frame transform | 1.5–2× raster | Low | 9–30× |
| 5 | Parallel band rasterization | ~cores× raster | Medium | — |
| 6 | Optional Numba JIT | 2–4× raster | Medium | — |

Proposals 1–3 together should reduce turnaround time by **5–10×** for a 10⁸-segment design.

---


