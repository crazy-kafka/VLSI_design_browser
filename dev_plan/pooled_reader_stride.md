# The pooled reader: keep only what this worker will parse

The plan for the last blocker on `--jobs` at scale, and the continuation of
[`metal_read_round2.md`](metal_read_round2.md). Round 2 removed the single-core cost that could be
removed (measured: **8.94x -> 2.05x** of a giant statement's text in peak memory, ~0 % time on
statement shapes matching the real run) and restored 4.5 M shapes that `+ MASK` was reading as a
layer named `ASK`. What is left that moves the clock is the wiring pass across processes.

## The problem is one line of ordering

`Reader.statements()` accumulates **every** statement's lines into `pending` while it scans, and the
stride is applied afterwards, by its consumer:

```python
for position, (section, lines) in enumerate(reader.statements()):
    if position % stride != index:      # after the lines were built
        continue
```

So a worker that will parse one statement in sixteen buffers the other fifteen first. One of them is
a power net of 58,549,358 lines, which is why `--jobs 16` would sit at ~160 GB of memory that is
immediately discarded - comfortable on a 300 GB host, but only just, and entirely wasted.

## The change

The decision moves to a statement's first line, where it can be made (`_NET` is what says a line
opens a net statement), and the lines of a statement this worker does not own are never accumulated:

```python
if not open_statement:
    first = line
    open_statement = True
    keeping = False
    is_net = bool(_NET.match(first))
    if is_net:
        position += 1
        keeping = position % self.stride == self.index
if keeping:
    pending.append(line)
if ";" in line:
    if is_net:
        self._found[section] = self._found.get(section, 0) + 1
        if keeping:
            yield section, pending
    pending, open_statement = [], False
```

Three properties, each of which a test pins:

- **`position` counts only net statements**, incremented where the old `enumerate` counted a yield -
  so the partition between workers is *identical* to today's, not merely valid, and the chunks and
  their float sums do not move.
- **`open_statement` and `keeping` are separate flags**, because the end-of-statement bookkeeping
  (the unterminated-statement warning) has to keep firing for statements nobody buffered.
- **`_found` still counts every net statement**, kept or not: that is what `check_counts()` compares
  against the section's declared count, and it must not depend on how many workers are reading.

`Reader.__init__` gains `index=0, stride=1` - the defaults are today's behaviour, so nothing else
changes - `_chunks` loses the two parameters and its `continue`, and `_worker` moves them from one
call to the other. Nothing outside `vlsi_viewer/parallel.py` sees the stride.

## What it buys

**Memory**: sixteen workers drop from ~160 GB to ~15 GB, because one power net is one statement and
exactly one worker now holds it. **Time**: a few percent at most - every worker still scans every
line, since that scan is what finds the statement ends; what goes away is the allocation and
collection of lists nobody reads. So this is not a speed fix: it is what makes `--jobs 16` a
comfortable run rather than a gamble, and `--jobs` is the only remaining lever worth tens of
minutes on this design.

## Tests

- **The partition is the same one**: for strides 2 and 3, each index's reader yields exactly the
  statements at positions `p % stride == index`, and the union over indexes is every statement once.
- **A skipped statement is still counted**: `check_counts()` reports a short section while the
  reader is skipping statements.
- **The memory bound**: `tracemalloc` shows a stride-4 reader peaking at roughly a quarter of a
  stride-1 reader over a fixture of many-line statements.
- The existing pooled-vs-sequential equivalence tests stay green - they are what says the stride
  still partitions the work correctly.

## Verification

`python -m pytest -q`, then a pooled build of the committed sample compared against the sequential
one (already covered, re-run because it is the equivalence this rests on). The end-to-end check is
the user's: `--jobs 8` and `--jobs 16` on `lx956c_ioe`, read against the 09-14 log - stage seconds,
`peak_rss_mb`, `gc_s` and the per-class counts - with the 2.1 GB `.gz` re-decompressed per worker as
the term to watch as N grows.
