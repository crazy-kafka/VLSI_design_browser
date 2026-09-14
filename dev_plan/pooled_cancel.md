# A cancel that survives the process boundary: `--jobs` and ^C

The plan for the failure reported in [`issue/thread_error.md`](issue/thread_error.md), run
`1645534805` on `lx956c_ioe` (3.36 M instances, 17,385 macros from 221 LEFs). It supersedes section B
of [`parse_once_flow.md`](parse_once_flow.md) - "`parse_parallel` accepts a `cancel` and never uses
it today ... Wire it through" - which is what introduced the defect.

## What the error was

```
INFO vlsi_viewer.cli: metal: reading routing in lx956c_ioe
error: cannot pickle '_thread.lock' object
```

`parallel.py` builds the worker task tuple and its last element was the caller's `cancel` callable.
On the CLI path that is `stop.is_set`, a bound method of a `threading.Event`, and `Event` holds a
`Condition` holding a `_thread.lock` - which pickle refuses. The failure is raised in the call
queue's feeder thread and re-raised in the parent through `future.result()`, which is why the message
names a stdlib file this project never appears in, and why `_run_metal`'s `error: {exc}` says nothing
about `--jobs`.

Reproduced on the committed sample with the pool forced on, and isolated with three controls:

| `cancel` | result |
|---|---|
| `None` | builds, 19,817 emitted (the golden) |
| `bool` - picklable, answers False | builds |
| `stop.is_set` - the CLI's, always | `TypeError: cannot pickle '_thread.lock' object` |

So the pool itself is sound; only the callable cannot cross. **Three further facts:**

- **It is a regression from `ea68fd3`**, the commit that first forwarded `cancel` to the workers,
  and no test pairs `jobs > 1` with a cancel - the only cancel in the suite is a `lambda` on the
  sequential path.
- **It cannot be reached from the sample**: `--jobs 8` collapses to one worker below 8 MB of input,
  so the pool never starts. The real design is the first input big enough. (The log corroborates -
  the "N worker(s) of N requested" line prints only when the count is *reduced*, and it is absent.)
- **A picklable callable would not have fixed it.** A task argument is deserialised *into* the child,
  so a copy can never observe the parent's `set()`.

## The second half: the workers threw away what they measured

`_worker` returns `sink.grids()` only at the end, and `parse_chunk` builds its own sink and returns
it only at the end. A `Cancelled` therefore discarded the in-flight chunk *and* everything that
worker had already banked - so the "cancel reaches the workers" change, had it worked, would have
stopped the work and thrown it away.

## The design

All of it in `vlsi_viewer/parallel.py`, plus one keyword in `metal.py`. `cli.py` and the vendored
parsers do not change.

**One byte of shared memory, measured.** The reader consults the flag once per input line, so the
per-read cost decides the transport. Measured on CPython 3.9.7 (spawn), as a task argument:

| transport | crosses? | per read | against a ~6 us line |
|---|---|---|---|
| `shared_memory.SharedMemory` byte | yes | 64-110 ns | ~1 % |
| `multiprocessing.Event()` | **no** - `RuntimeError: Condition objects should only be shared between processes through inheritance` | 2.7 us (via `initargs` only) | ~45 % |
| `Manager().Event()` | yes | 29.5 us | ~5x the parse |
| sentinel file | yes | 54.8 us (`stat`) | ~9x the parse |

`SharedMemory` pickles by *name*, so a module-level `_Flag` travels in the task tuple exactly where
the callable used to be and each worker attaches to the parent's segment. `__call__ = is_set` is the
surgical part: `Reader._lines` and `DefParser.__count_line` ask `cancel()` and do not move a
character, because the sequential path still passes a real callable into the same parameter.

**The trigger.** `cancel()` is read once, ungated, before the tasks are built - which is also what
makes a cancel that is already set deterministic instead of a race - and after that by one watcher
thread (`CANCEL_POLL_SECONDS = 0.5`), because the parent is the only process that can see the
caller's flag. The parent raises `Cancelled` itself, naming how many workers stopped early, so
`build_metal`'s existing warning survives.

**Workers must not hear ^C.** A pool's children are in the parent's process group (POSIX) and share
its console (Windows), so a terminal ^C reaches them too - where it either kills a worker, turning a
graceful stop into `BrokenProcessPool` with the map discarded, or re-raises `KeyboardInterrupt` in
the parent past both `except Cancelled` and `except Exception`. The pool's `initializer` - which runs
first thing in each worker's main thread - ignores `SIGINT`, as the stdlib does for its own helpers.

**Salvage at both levels.** `parse_chunk` catches `Cancelled` and still flushes the stream: the
stream counts a shape when it is *queued* and hands the whole batch over in `flush()`, so
flush-then-read is a consistent snapshot at any line boundary, and skipping it is the silent
corruption. `_worker` catches it around the chunk loop too, because the reader's per-line check fires
*between* chunks while earlier ones are banked. A stopped worker folds that chunk once and breaks -
folding it and continuing would add geometry no counter accounts for. `check_counts()` is skipped
when stopped: a partial read makes the declared and found counts disagree and every cancelled worker
would print "NETS declares N net(s) but M were read" - the sequential path never reaches its
equivalent, so this is parity, not suppression.

**The stop is reported, not raised** - which the first implementation got wrong, and the salvage test
caught: `parse_parallel` folded the stopped workers' grids into the sink and *then* raised, so the
map held geometry that no counter described (`emitted == 0` over a half-filled grid). It now returns
its totals with `note["interrupted"]` and `note["stopped"]`, and `build_metal` raises after folding
them, so the counters and the grids always tell the same story.

## Adjacent fixes, all visible in the same log

- the blockage line's "(M2, M3, M4 inside the measured range)" parenthetical printed even with 0
  macros falling back;
- the worker-count line reports `os.path.getsize` - compressed bytes for a `.gz` - while the count
  was sized on the uncompressed size;
- `cli.py`'s "stopping after the current block" was stale; the cancel is per-statement, and per
  worker here;
- `--jobs`'s help and the README said "scales nearly linearly with cores" and nothing about matching
  the allocation - this run asked for 8 workers inside `-R 'cpu=4'`, so every core ran two, each
  gzip-decompressing the whole DEF.

## Tests

- **The CLI's exact configuration** - `threading.Event().is_set` with `jobs=3` builds and matches the
  sequential totals. Red before the fix.
- **A cancel means the same thing on both paths** - `lambda: True`, `jobs=1` vs `jobs=3`: both warn,
  both measure nothing, both keep a grid.
- **A partial worker keeps what it measured** - `_worker` called in-process with a counting fake
  flag; the returned grids are a **cellwise minorant** of a full run's (every shape adds positively,
  so a prefix can only be smaller), which is the invariant a counter cannot show.
- **A cancel after the first block keeps that block's wiring** - driven by `on_progress` rather than
  the clock, so it is deterministic.
- **Workers ignore ^C**, and the existing equivalence tests stay green as the control.

## Verification

`python -m pytest -q`; then the reported configuration inverted (`jobs=3` with `stop.is_set` builds,
and with a cancel already set returns the partial map and the warning). The next real `--jobs` run is
the pooled path's first exercise at scale, and since the 09-14 report says `--jobs` was the only new
flag, that day's successful run used the same layer range and is a free oracle for it.
