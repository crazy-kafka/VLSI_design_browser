"""What a geometry-carrying metal db would cost, measured before any of it is built.

    python sample_data/metal/bench_db_geometry.py --scale 50
    python sample_data/metal/bench_db_geometry.py --scale 200

The question is whether a db should store a block's shapes *before* the placement frames are
applied - which would let every block be dumped on its own, with no parent - and what that costs
in bytes and in time. So this measures three things on a real routed DEF:

- **the raster share**: the time spent inside the sink (the rasteriser) as a fraction of the
  routing stage. A replay pays exactly this share, because it re-runs the same rasterisation on
  stored shapes; it is the floor of any replay.
- **bytes per rect**: the shapes as int32 database units, raw and zlib-compressed, sampled from
  the batches `ShapeStream.flush` is about to hand to the sink.
- **the parse rate**: shapes measured per second of the routing stage, which turns their log's
  shape counts into what those shapes would cost to parse.

The fixture repeats the sample's `NETS`/`SPECIALNETS` bodies `--scale` times. That is a fixture for
a throughput question, not a layout: the shape-per-line ratio is real routing's, the coordinates are
reused, and nothing here is read for its placement.
"""
import argparse
import contextlib
import io
import logging
import os
import re
import sys
import time
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from vlsi_viewer.metal import build_metal
from vlsi_viewer.parsers.routing import ShapeStream
from vlsi_viewer.parsers.routing import TechRouting
from vlsi_viewer.raster import Bins

SAMPLE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.join(SAMPLE, "sub.def")
CELLS = os.path.join(SAMPLE, "cells.lef")
TECH = os.path.join(SAMPLE, "tech.lef")

# dev_plan/issue/real_design_log_0917.md: the shape counts the runs reported. Only the top block's
# is known - the two runs refused or never reached the sub-blocks' - so the design projection is
# given per 100M shapes and for the top, not invented for the rest.
CORE_WRAP_SHAPES = 44_395_406


class TimedSink:
    """The sink with its rasterising calls timed.

    A wrapper rather than an instrumented copy, so what is measured is the real call the stream
    makes - `add_rects(layer, scope, x0, y0, x1, y1)` - and not a re-implementation of it.
    """

    def __init__(self, sink):
        self._sink = sink
        self.seconds = 0.0
        self.calls = 0
        for name in ("add_rects", "add_diagonal", "add_polygon", "add_grids"):
            setattr(self, name, self._timing(getattr(sink, name)))

    def _timing(self, original):
        def call(*args, **kwargs):
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.seconds += time.perf_counter() - started
                self.calls += 1
        return call

    def grids(self):
        return self._sink.grids()


def scaled(text, scale):
    """The DEF with its wiring statements repeated `scale` times, counts corrected.

    Names are left alone: nothing in the reader keys on a net name, and a fixture that had to
    rewrite coordinates to tile the design would be measuring the rewriter as much as the parser.
    """
    for section in ("NETS", "SPECIALNETS"):
        pattern = re.compile(rf"^{section} (\d+) ;$", re.MULTILINE)
        match = pattern.search(text)
        if match is None:
            continue
        end = text.index(f"END {section}", match.end())
        body = text[match.end():end]
        text = (text[:match.start()]
                + f"{section} {int(match.group(1)) * scale} ;"
                + body * scale
                + text[end:])
    return text


def planted_flush(captured, limit=200_000):
    """A `ShapeStream.flush` that keeps a bounded sample of the pre-frame batches.

    All four coordinates, not the first: a rect is four numbers, and the section's size is a
    question about the rectangle. They are kept interleaved as (n, 4) so the compression measured
    is the compression of the data that would actually be written, where x1 sits next to x0.
    """
    original = ShapeStream.flush

    def flush(self):
        for key, coords in self._pending.items():
            kept = captured.setdefault(key, [])
            room = limit - sum(len(part) for part in kept)
            if room > 0:
                kept.append(np.stack([np.asarray(axis[:room], dtype=np.float64)
                                      for axis in coords[:4]], axis=1))
        return original(self)

    return original, flush


def timed_bins_flush(timings):
    """Wrap `Bins.flush` into the sink's time: the rasteriser works there, not in `add_rects`.

    `_GridSink.add_rects` queues into the layer's `Bins`, which rasterises when its queue fills or
    when the grid is asked for - so timing the queueing alone measures the wrong thing by a wide
    margin, which is exactly what the first version of this benchmark did.
    """
    original = Bins.flush

    def flush(self):
        started = time.perf_counter()
        try:
            return original(self)
        finally:
            timings["sink"] = timings.get("sink", 0.0) + time.perf_counter() - started
    return original, flush


def replay_cost(captured, tech, extent, grid_size, db_unit, temp_path):
    """Time the path a stored geometry section actually takes on the way back in.

    The projection above multiplies a share of the *build* by a shape count, which assumes a
    replay costs what the rasterisation inside a parse costs. It does not: a replay also reads and
    inflates the records and iterates the batches, and none of that exists inside the build's own
    measurement. So the sampled batches go out through the code that would write them - a
    `SectionWriter` into a part, `metal_db.write` into a db - and come back through the code that
    reads them: `BlockDb.geometry` yields one batch at a time, and `ShapeStream.add_batch` queues
    it for the next `flush` exactly as a parse would have. What it returns is microseconds per
    shape, which is the number to multiply.
    """
    from vlsi_viewer import metal as metal_module
    from vlsi_viewer import metal_db
    from vlsi_viewer.parsers.routing import POWER, SIGNAL

    # Stored by layer *name* and read back by name, as the format does: the capture is keyed by
    # the trimmed stack's position, and a name is what survives a differently ordered stack.
    names = {layer.index: layer.name for layer in tech.layers}
    scopes = {SIGNAL: "signal", POWER: "power"}
    part = str(temp_path) + ".part0"
    db_path = str(temp_path) + ".db"
    try:
        writer = metal_db.SectionWriter(part)
        for (layer_index, scope), parts in sorted(captured.items()):
            writer.batch("rects", names[layer_index], scopes[scope],
                         np.round(np.concatenate(parts, axis=0) * db_unit).astype(np.int32))
        writer.close()
        metal_db.write(db_path,
                       header={"format": metal_db.DB_FORMAT, "block": "bench", "frames": []},
                       grids={}, parts=[part])
        db = metal_db.load(db_path)

        index = {layer.name: layer.index for layer in tech.layers}
        back = {name: scope for scope, name in scopes.items()}
        sink = metal_module._GridSink(extent, grid_size)
        stream = ShapeStream(tech, sink, frames=(None,))
        stream.configure(db_unit, {})
        shapes = 0
        started = time.perf_counter()
        for kind, layer, scope, packed in db.geometry():
            stream.add_batch(kind, index[layer], back[scope], packed)
            stream.flush()
            shapes += len(packed)
        sink.grids()
        elapsed = time.perf_counter() - started
    finally:
        # This instrument writes a real db, and a benchmark that leaves one behind is a benchmark
        # somebody later mistakes for data.
        for leftover in (part, db_path):
            try:
                os.unlink(leftover)
            except OSError:                          # pragma: no cover - best effort
                pass
    return elapsed, shapes


class StageSeconds(logging.Handler):
    """The build's own stage timings, read off the log it already emits.

    ``metal: stage routing  1696.70s ...`` is the wiring pass as the tool measured it, so this
    works on a DEF too large to repeat - which is the case the numbers are for.
    """

    def __init__(self):
        super().__init__()
        self.seconds = {}
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        # `search`, not `match`: the line reads "metal: stage routing ...".
        found = re.search(r"stage (\S+)\s+([\d.]+)s", record.getMessage())
        if found:
            self.seconds[found.group(1)] = float(found.group(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=50,
                    help="times the wiring is repeated (the sample's sub.def by default)")
    ap.add_argument("--def", dest="def_path", default=SUB,
                    help="a routed DEF to measure instead of the sample's: point it at your own "
                         "and the projection below becomes your design's")
    ap.add_argument("--lef", dest="lef_paths", nargs="+", default=[CELLS])
    ap.add_argument("--tech-lef", dest="tech_paths", nargs="+", default=[TECH])
    ap.add_argument("--shapes", type=int, default=CORE_WRAP_SHAPES,
                    help="shape count the projection is for (default: the 09-17 log's top block)")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="build each configuration N times and use the fastest (default: "
                         "%(default)s). The raster share is a difference of two long builds, and "
                         "one pair of them on a shared machine spreads wider than the number "
                         "being measured")
    args = ap.parse_args()

    text = scaled(open(args.def_path, "r", encoding="utf-8").read(), args.scale)
    path = os.path.join(SAMPLE, ".bench_db_geometry.def")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    db_unit = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", text).group(1))

    tech = TechRouting.read(args.tech_paths)
    captured = {}
    original, flush = planted_flush(captured)
    real_build = build_metal
    timings = {}

    def build_with_timing(def_paths, lef_paths, tech_paths, null_sink=False, **kwargs):
        """`build_metal`, with the sink the routing pass uses wrapped in `TimedSink`.

        With ``null_sink`` the rasteriser is replaced by one that drops every shape, which is the
        only way to isolate it: the difference between the two builds *is* the rasterisation, and
        an independent check on the timed wrapper rather than a second reading of the same guess.
        """
        sink_holder = {}
        from vlsi_viewer import metal as metal_module
        real_sink = metal_module._GridSink

        class Null:
            def __init__(self, extent, grid_size):
                pass

            def add_rects(self, *a, **k):
                pass

            add_diagonal = add_polygon = add_rects

            def add_grids(self, grids):
                pass

            def grids(self):
                return {}

        class Timed:
            """A stand-in for `_GridSink` that forwards, so the wrapper is the only new code.

            Not a subclass: overriding the very methods the wrapper forwards to is recursive.
            """

            def __init__(self, extent, grid_size):
                inner = TimedSink(real_sink(extent, grid_size))
                self._timed = inner
                sink_holder["sink"] = inner

            def add_rects(self, *a, **k):
                return self._timed.add_rects(*a, **k)

            def add_diagonal(self, *a, **k):
                return self._timed.add_diagonal(*a, **k)

            def add_polygon(self, *a, **k):
                return self._timed.add_polygon(*a, **k)

            def add_grids(self, grids):
                return self._timed.add_grids(grids)

            def grids(self):
                return self._timed.grids()

        metal_module._GridSink = Null if null_sink else Timed
        ShapeStream.flush = flush
        bins_flush, bins_original = timed_bins_flush(timings)
        Bins.flush = bins_flush
        try:
            started = time.perf_counter()
            data = real_build(def_paths, lef_paths, tech_paths, **kwargs)
            total = time.perf_counter() - started
        finally:
            metal_module._GridSink = real_sink
            ShapeStream.flush = original
            Bins.flush = bins_original
        timings["total"] = total
        if "sink" in sink_holder:
            timings["sink"] = timings.get("sink", 0.0) + sink_holder["sink"].seconds
            timings["calls"] = sink_holder["sink"].calls
        return data

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        stage = StageSeconds()
        metal_log = logging.getLogger("vlsi_viewer.metal")
        # INFO, or the handler never sees the line: a logger's own level filters before handlers.
        metal_log.setLevel(logging.INFO)
        metal_log.addHandler(stage)
        try:
            # The fastest of N, not the mean: this measures a difference of two long builds, and
            # a busy machine can only make a build slower, never faster.
            totals, withouts, routings, bares = [], [], [], []
            for attempt in range(args.repeat):
                data = build_with_timing([path], args.lef_paths, args.tech_paths, grid_size=10.0)
                totals.append(timings["total"])
                routings.append(stage.seconds.get("routing", float("nan")))
                if attempt == 0:
                    sink, calls = timings["sink"], timings["calls"]
                build_with_timing([path], args.lef_paths, args.tech_paths, grid_size=10.0,
                                  null_sink=True)
                withouts.append(timings["total"])
                bares.append(stage.seconds.get("routing", float("nan")))
        finally:
            logging.getLogger("vlsi_viewer.metal").removeHandler(stage)
        total, without_raster = min(totals), min(withouts)
        routing, bare = min(routings), min(bares)
        if args.repeat > 1:
            print(f"  {args.repeat} run(s) each: build {min(totals):.2f}-{max(totals):.2f}s, "
                  f"without the rasteriser {min(withouts):.2f}-{max(withouts):.2f}s")
    os.unlink(path)

    # The wiring pass comes from the run's own stage line - so this works at `--scale 1` too,
    # which is what a DEF too big to repeat needs. The null-sink run is the independent check on
    # it: with the rasteriser dropping every shape, the same stage measures the parse alone.
    raster = max(total - without_raster, 0.0)
    if args.repeat > 1:
        print(f"  routing stage {min(routings):.2f}-{max(routings):.2f}s, without the rasteriser "
              f"{min(bares):.2f}-{max(bares):.2f}s")
    lines = text.count("\n") + 1
    shapes = data.totals["emitted"]
    print(f"fixture: scale {args.scale}, {lines:,} lines, {shapes:,} shape(s) measured")
    print(f"  build {total:.2f}s; stage routing {routing:.2f}s")
    print(f"  the same build with the rasteriser replaced by one that drops every shape: "
          f"{without_raster:.2f}s, stage routing {bare:.2f}s")
    print(f"  -> rasterisation {raster:.2f}s = {100 * raster / routing:.1f}% of the wiring pass "
          f"(the timed sink wrapper said {sink:.2f}s over {calls:,} calls)")
    per_shape = routing / max(1, shapes)
    print(f"  {per_shape * 1e6:.2f} us per measured shape (parse + classify + rasterise)")

    # Bytes per rect, as the geometry section would store them: int32 database units.
    raw = compressed = count = 0
    for (layer, scope), parts in sorted(captured.items()):
        for part in parts:
            as_int = np.round(part * db_unit).astype(np.int32)      # (n, 4) DB units
            raw += as_int.nbytes
            compressed += len(zlib.compress(as_int.tobytes(), 6))
            count += len(as_int)
    if count:
        print(f"rects sampled: {count:,} in {len(captured)} layer/scope batches")
        print(f"  {raw / count:.1f} B/rect raw, {compressed / count:.1f} B/rect zlib 6 "
              f"({100 * compressed / raw:.0f}% of raw)")

    # The direct answer: read a stored section back and push it through a real sink.
    replay_seconds, replay_shapes = replay_cost(captured, tech, data.extent, 10.0, db_unit,
                                                path + ".replay")
    if replay_shapes:
        per_shape_replay = replay_seconds / replay_shapes
        print(f"\nreplay of the sampled section: {replay_shapes:,} shape(s) in "
              f"{replay_seconds:.2f}s = {per_shape_replay * 1e6:.2f} us/shape "
              f"(read + inflate + rasterise), against {per_shape * 1e6:.2f} us to parse them")
        print(f"  so a section of {args.shapes:,} shape(s) replays in "
              f"{args.shapes * per_shape_replay / 60:.1f} min, where parsing them costs "
              f"{args.shapes * per_shape / 60:.1f} min")

    print("\nprojection, from this fixture's measured rates:")
    for label, n_shapes in (("per 100M shape(s)", 100_000_000),
                            (f"the design these shapes came from ({args.shapes:,})", args.shapes),
                            ("twice that", args.shapes * 2),
                            ("four times that", args.shapes * 4)):
        if not label:
            continue
        if count:
            raw_mb = n_shapes * (raw / count) / 1e6
            zip_mb = n_shapes * (compressed / count) / 1e6
            size = f"{zip_mb / 1000:.2f} GB (raw {raw_mb / 1000:.2f})"
        else:
            size = "n/a (no rects captured)"
        parse_s = n_shapes * per_shape
        replay_s = parse_s * raster / max(routing, 1e-9)
        print(f"  {label}: {size}; parse+raster {parse_s / 60:.1f} min, "
              f"replay at this raster share {replay_s / 60:.1f} min")


if __name__ == "__main__":
    main()
