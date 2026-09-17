"""The metal mode's intermediate db: the DEF-derived half of a build, kept for the next run.

A chip-level DEF costs ~28 minutes of routing parse for a map of a few hundred kilobytes of grids.
This module writes those grids and the facts around them to one file per DEF - ``A.def.gz`` becomes
``A.def.db`` - so a later run rebuilds the map in seconds.

**Only DEF-derived facts are stored.** The layer names, directions, pitches, the capacity grid and
the macro blockage are rebuilt from the live LEFs on every run, so nothing in a db can disagree with
the LEF the user is holding: what a db records about its LEFs is their *identity*, used to refuse it,
never to stand in for them. The one place a LEF-derived number is needed - the macro blockage, which
also depends on where the macros are placed - is recomputed from the components kept here.

**The components kept are not the whole instance table.** That table is the largest thing in a DEF
(3M rows, hundreds of megabytes), and what the hierarchy needs from it is where each block sits and
which blocks a block instantiates. So a db keeps the rows that can matter, in the block's own local
coordinates: every instance whose cell is a LEF macro (the blockage's input), or is not in the LEF at
all (which is what a sub-block looks like when its own DEF is not part of the run).

**A db is used only for the design it was written for.** Its validity is a comparison, not a guess:
the DEF's size and mtime, the measured layer set, the grid size, ``--min-segment-length``,
``--macro-block-layers``, the LEF identities and the frames the block was placed at must all match.
Anything else is refused with the difference named, and the caller decides whether to re-parse the
DEF or to stop.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import time
import zlib
from dataclasses import dataclass, field
from typing import AnyStr, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import __version__
from .parsers.routing import POWER, SIGNAL

# Bump when the header's meaning changes. A db written by another format is *refused with a
# message*, never read as if the number still meant what it used to.
DB_FORMAT = 1
DB_SUFFIX = ".db"

# The container is a record stream with a footer, because the writer cannot know in advance how
# many batches a parse will produce - the parse decides that. The footer holds the header JSON, an
# index of every record, and this magic, so a reader starts at the end; and because the index
# carries offsets, loading a db for its grids seeks straight to them instead of reading past half a
# gigabyte of shapes. A file without the magic at its end is tried as the v1 npz, which is what
# dumps written before this existed are.
MAGIC = b"VLSIDB2\n"
_FILE_END = len(MAGIC) + 8                                   # + the footer's uint64 header length
_HEADER_KEY = "header"
_COMPONENTS_KEY = "components"
_GRID_PREFIX = "grid/"
# The batch kind the stream calls it -> the record name it is stored under.
_RECORD_KIND = {"rects": "rect", "diagonals": "diag", "polygons": "poly"}
_KIND_OF_RECORD = {record: kind for kind, record in _RECORD_KIND.items()}
_DTYPE_CODES = {"i4": 1, "f4": 2, "f8": 3}
_CODE_DTYPES = {code: np.dtype(name) for name, code in _DTYPE_CODES.items()}
# Compression level for a section. 6 is what the cost of a replay was measured at: a dump pays it
# once, a load pays the (much cheaper) inflate.
_ZLIB = 6

# The DEF orientations, in the order the component array's codes use. Re-exported from the layout
# of the array rather than from `coordinateProcess`, so a db's codes cannot move under it.
ORIENTATIONS = ("N", "S", "W", "E", "FN", "FS", "FW", "FE")

# The v1 container's grid keys; the reader below still reads them.
_V1_GRID_PREFIX = "grid__"
_PARAM_KEYS = ("grid_size", "min_layer", "max_layer", "min_segment", "macro_block_layers")


def db_path_for(def_path, directory) -> str:
    """``<directory>/A.def.db`` for ``A.def.gz`` - the DEF's own name, minus the compression."""
    name = os.path.basename(str(def_path))
    if name.endswith(".gz"):
        name = name[: -len(".gz")]
    return os.path.join(str(directory), name + DB_SUFFIX)


def source_note(path) -> Dict:
    """Path, size and mtime - the change test for one input file.

    The same test `metrics._source_key` applies to its pickle cache: metadata, never contents.
    Hashing a 2 GB `.gz` costs more than the parse the db exists to avoid.
    """
    st = os.stat(path)
    return {"path": os.path.abspath(str(path)),
            "size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns)}


def set_key(paths) -> str:
    """One identity for a group of files - the macro LEFs, the tech LEFs."""
    h = hashlib.sha256()
    for path in paths:
        note = source_note(path)
        h.update(f"{note['path']}|{note['size']}|{note['mtime_ns']}\n".encode("utf-8"))
    return h.hexdigest()[:16]


def _stamp(ns) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ns) / 1e9))


def _fmt_frames(frames) -> str:
    """``N at (0, 0)``, or a count when a block is placed many times."""
    if not frames:
        return "nowhere"
    head = ", ".join(f"{orient} at ({x:g}, {y:g})" for orient, x, y in frames[:2])
    return head if len(frames) <= 2 else f"{head} (+{len(frames) - 2} more)"


def _fmt_names(names) -> str:
    names = sorted(names)
    return ", ".join(names[:4]) + (f", +{len(names) - 4}" if len(names) > 4 else "")


@dataclass
class BlockDb:
    """One block's stored build: the header (everything scalar) plus the arrays.

    ``grids`` is keyed by ``(layer name, scope)`` - by name, never by stack position, so a db
    loaded against a differently indexed stack cannot mis-key a layer: the name either matches the
    live tech LEF or the db is refused.
    """

    header: Dict
    grids: Dict[Tuple[str, str], np.ndarray] = field(default_factory=dict)
    components: Optional[np.ndarray] = None      # (n, 4): cell code, orient code, x, y
    path: Optional[AnyStr] = None                # where the shape records live, if any
    has_geometry: bool = False                   # the block's own shapes, before any frame

    @property
    def block(self) -> str:
        return str(self.header["block"])

    @property
    def frames(self) -> List:
        return [tuple(frame) for frame in self.header["frames"]]

    def component_rows(self):
        """``(cell_name, orient, x, y)`` for each remembered component."""
        if self.components is None or not len(self.components):
            return []
        cells = self.header["component_cells"]
        return [(cells[int(code)], ORIENTATIONS[int(o)], float(x), float(y))
                for code, o, x, y in self.components]

    def geometry(self):
        """Yield ``(kind, layer name, scope, packed)`` for every stored batch, one at a time.

        Streamed, and that is the point: a section is hundreds of megabytes, and a replay holds
        one batch - the same bound a parse works under. The layer travels as a *name*, so it is
        the loading run's tech LEF that turns it back into a stack position.
        """
        if not self.has_geometry:
            return
        with open(str(self.path), "rb") as handle:
            for name, positions in self.header.get("index", {}).items():
                kind = _KIND_OF_RECORD.get(name.split("/", 1)[0])
                if kind is None:
                    continue
                for position in positions:
                    handle.seek(position)
                    _name, dtype, shape, flags, nbytes = _read_record(handle)
                    array = _decode(handle.read(nbytes), dtype, flags).reshape(shape)
                    layer, _, scope = _name.split("/", 1)[1].rpartition("/")
                    yield kind, layer, scope, array


def batch_hook(tech, writer: "SectionWriter"):
    """Route a stream's batches into a section writer, keyed by layer *name* and scope name.

    Names, not stack positions: a section is DEF data, and the run that loads it may order its
    stack differently. Defined here rather than in the metal build because a *worker* needs it -
    the shapes never leave the process that parsed them - and a closure made in the parent could
    not travel there.
    """
    names = {layer.index: layer.name for layer in tech.layers}
    scopes = {SIGNAL: "signal", POWER: "power"}

    def on_batch(kind, layer_index, scope, packed):
        # Indexed, not defaulted: a scope this does not know is a wrong map waiting to be drawn,
        # and the parse raises where it happens rather than filing power as signal.
        writer.batch(kind, names[layer_index], scopes[scope], packed)
    return on_batch


def _pack_record(name: str, array: np.ndarray, flags: int, nbytes: int) -> bytes:
    """One record's header. Little-endian, whatever the machine wrote it on."""
    encoded = name.encode("ascii")
    return (struct.pack("<HBB", len(encoded), _DTYPE_CODES[array.dtype.str[1:]], array.ndim)
            + encoded
            + struct.pack(f"<{array.ndim}I", *array.shape)
            + struct.pack("<BQ", flags, nbytes))


def _read_record(handle):
    """``(name, dtype, shape, flags, payload nbytes)`` for the record at the cursor, or a raise."""
    raw = handle.read(4)
    if len(raw) < 4:
        raise ValueError("record stream ends mid-header")
    name_len, code, ndim = struct.unpack("<HBB", raw)
    name = handle.read(name_len).decode("ascii")
    if len(name) < name_len or code not in _CODE_DTYPES:
        raise ValueError("truncated or unreadable record header")
    shape = struct.unpack(f"<{ndim}I", handle.read(4 * ndim))
    flags, = struct.unpack("<B", handle.read(1))
    nbytes, = struct.unpack("<Q", handle.read(8))
    return name, _CODE_DTYPES[code], shape, flags, nbytes


def _decode(payload: bytes, dtype, flags: int) -> np.ndarray:
    if flags & 1:
        payload = zlib.decompress(payload)
    return np.frombuffer(payload, dtype=dtype)


def _encode(array: np.ndarray):
    """``(payload, nbytes)`` for one array: little-endian, compressed."""
    array = np.ascontiguousarray(array).astype(array.dtype.newbyteorder("<"), copy=False)
    return zlib.compress(array.tobytes(), _ZLIB), array


def _walk_records(handle):
    """``(name, header offset, shape)`` for each record, hopping header to header."""
    while True:
        offset = handle.tell()
        try:
            name, _dtype, shape, _flags, nbytes = _read_record(handle)
        except ValueError:
            return
        yield name, offset, shape
        handle.seek(nbytes, 1)


class SectionWriter:
    """Streams one block's geometry into a body file, a batch at a time.

    A dump holds one batch and never a block's geometry: a chip-level block is hundreds of
    megabytes of shapes, and writing a db must not mean building a second copy of it in memory
    first. Workers own one of these each, and their files are concatenated by the parent, which is
    all a merge needs to be - every accumulator downstream is a sum.
    """

    def __init__(self, path: AnyStr):
        self.path = str(path)
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        # Truncating, so a part left behind by an earlier run is never appended to.
        self._handle = open(self.path, "wb")
        self.counts = {kind: 0 for kind in _RECORD_KIND}
        # Set by whoever parses into it: the DEF's database unit, which only a parse learns.
        self.db_unit = None

    def batch(self, kind: AnyStr, layer_name: AnyStr, scope: AnyStr, packed) -> None:
        """One batch from the stream, in the DEF's own integers."""
        array = np.ascontiguousarray(packed)
        payload, array = _encode(array)
        self._handle.write(_pack_record(f"{_RECORD_KIND[kind]}/{layer_name}/{scope}",
                                        array, 1, len(payload)))
        self._handle.write(payload)
        # A ring is one shape, however many vertices it has - so it counts like `emitted` does.
        self.counts[kind] += 1 if kind == "polygons" else len(array)

    def close(self) -> None:
        self._handle.close()


def write(path, *, header: Dict, grids: Dict, components=None, parts: Sequence = ()) -> Dict:
    """Assemble one db: the geometry parts, then the grids and components, then the footer.

    Returns the header as written, which carries two things this computes: the record index that
    lets a reader find a grid without reading the shapes, and what the geometry holds, so a load
    can say whether a db can stand in on its own coordinates.
    """
    index: Dict[AnyStr, List[int]] = {}
    counts = {kind: 0 for kind in _RECORD_KIND}
    with open(str(path), "wb") as out:
        for part in parts:
            base = out.tell()
            with open(str(part), "rb") as source:
                for name, offset, shape in _walk_records(source):
                    index.setdefault(name, []).append(base + offset)
                    kind = _KIND_OF_RECORD.get(name.split("/", 1)[0])
                    if kind is not None:
                        # Shapes, not coordinates: a rectangle record is `(n, 4)` and a diagonal
                        # `(n, 5)`, and this is the number the load compares with `emitted`.
                        counts[kind] += (1 if kind == "polygons"
                                         else int(shape[0]) if shape else 0)
                source.seek(0)
                shutil.copyfileobj(source, out, 8 << 20)
        for (layer, scope), grid in grids.items():
            array = np.ascontiguousarray(grid, dtype=np.float32)
            payload, array = _encode(array)
            index[f"{_GRID_PREFIX}{layer}/{scope}"] = [out.tell()]
            out.write(_pack_record(f"{_GRID_PREFIX}{layer}/{scope}", array, 1, len(payload)))
            out.write(payload)
        if components is not None and len(components):
            array = np.ascontiguousarray(components, dtype=np.float64)
            payload, array = _encode(array)
            index[_COMPONENTS_KEY] = [out.tell()]
            out.write(_pack_record(_COMPONENTS_KEY, array, 1, len(payload)))
            out.write(payload)
        header = dict(header, geometry=counts, index=index)
        blob = json.dumps(header, sort_keys=True).encode("utf-8")
        out.write(blob)
        out.write(struct.pack("<Q", len(blob)))
        out.write(MAGIC)
    return header


def load(path) -> BlockDb:
    """Read one db.

    Two containers live here: this build's record stream - found by the magic it ends with - and
    the v1 npz that dumps written before it use. ``allow_pickle=False`` throughout: a db is data,
    never code. Raises ``ValueError`` for a file this build cannot read - another format version,
    a missing header, a truncated file - so a caller can turn it into the reason a block is being
    re-parsed.
    """
    with open(str(path), "rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        if end >= _FILE_END:
            handle.seek(end - len(MAGIC))
            if handle.read(len(MAGIC)) == MAGIC:
                return _load_records(handle, str(path))
        handle.seek(0)
        return _load_v1(handle)


def _load_records(handle, path) -> BlockDb:
    handle.seek(0, os.SEEK_END)
    handle.seek(-_FILE_END, os.SEEK_END)
    header_len, = struct.unpack("<Q", handle.read(8))
    handle.seek(-_FILE_END - header_len, os.SEEK_END)
    header = json.loads(handle.read(header_len).decode("utf-8"))
    got = header.get("format")
    if got != DB_FORMAT:
        raise ValueError(f"db format {got!r}, this build writes {DB_FORMAT}")
    index = header.get("index", {})
    grids, components = {}, None
    for name, positions in index.items():
        # Only what a load needs: the shapes stay on disk until a replay asks for them.
        if not name.startswith(_GRID_PREFIX) and name != _COMPONENTS_KEY:
            continue
        handle.seek(positions[0])
        _name, dtype, shape, flags, nbytes = _read_record(handle)
        array = _decode(handle.read(nbytes), dtype, flags).reshape(shape)
        if name == _COMPONENTS_KEY:
            components = array
        else:
            layer, _, scope = name[len(_GRID_PREFIX):].rpartition("/")
            grids[(layer, scope)] = array
    return BlockDb(header, grids, components, path=path,
                   has_geometry=any(header.get("geometry", {}).values()))


def _load_v1(handle) -> BlockDb:
    """The npz a dump written before the record stream uses."""
    with np.load(handle, allow_pickle=False) as data:
        if _HEADER_KEY not in data.files:
            raise ValueError("no header: not a metal db")
        header = json.loads(str(data[_HEADER_KEY].item()))
        got = header.get("format")
        if got != DB_FORMAT:
            raise ValueError(f"db format {got!r}, this build writes {DB_FORMAT}")
        components = data[_COMPONENTS_KEY] if _COMPONENTS_KEY in data.files else None
        grids = {}
        for key in data.files:
            if not key.startswith(_V1_GRID_PREFIX):
                continue
            layer, _, scope = key[len(_V1_GRID_PREFIX):].rpartition("__")
            grids[(layer, scope)] = data[key]
    return BlockDb(header, grids, components)



def _die_note(extent) -> str:
    """`` over 2526.2 x 1887.8 um``, or nothing when the db recorded no extent."""
    if not extent:
        return ""
    return f" over {extent[2] - extent[0]:g} x {extent[3] - extent[1]:g} um"


def _same_extent(one, other) -> bool:
    if one is None or other is None:
        return one is other
    return all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(one, other))


def mismatch(db: BlockDb, *, params: Dict, def_note: Dict = None,
             tech_key: str = None, lef_key: str = None,
             layers: Sequence[AnyStr] = None, frames=None,
             geometry: Tuple[int, int, Sequence[float]] = None,
             param_keys: Sequence = _PARAM_KEYS) -> Optional[str]:
    """Why this db cannot be used for this run, or ``None`` when it can.

    One sentence, in the order a user would want to read it: the DEF they changed, then the knobs
    they changed, then the layer range, then the libraries, and last the design itself - the grid
    the db was rasterised on, and the hierarchy it was rasterised for.

    ``geometry`` is ``(rows, cols, extent)``, the run's own grid. It is what catches the db of a
    block dumped on its own: its grids cover *its* die, and a block that sits at the origin of its
    design records the same frame a standalone dump does, so the frame check cannot tell them
    apart. Both are compared, because the same cell count over a shifted die puts every grid in
    the wrong place.

    ``param_keys`` is which recorded knobs apply. The grids path checks all of them; a db loaded
    for its *geometry* checks `min_segment` alone, because everything else either acts on the live
    rasterisation (the grid size, the die) or is recomputed from the live LEFs (the blockage) - a
    section of shapes is DEF data, and a DEF fact does not care what grid it will be drawn on. The
    two arguments that are *not* knobs stay meaningful either way: the layer set and the tech LEF
    decided which shapes were stored, so the replay is refused for those as well, while the macro
    LEFs only decided the blockage.
    """
    header = db.header
    if def_note is not None:
        recorded = header.get("def", {})
        if (recorded.get("size") != def_note.get("size")
                or recorded.get("mtime_ns") != def_note.get("mtime_ns")):
            return (f"the DEF changed (size {recorded.get('size')} -> {def_note.get('size')}, "
                    f"mtime {_stamp(recorded.get('mtime_ns', 0))} -> "
                    f"{_stamp(def_note.get('mtime_ns', 0))})")
    recorded_params = header.get("params", {})
    for key in param_keys:
        if recorded_params.get(key) != params.get(key):
            remedy = ""
            if key in ("min_layer", "max_layer"):
                # The user's remedy differs by direction, and one of the two is not a re-dump:
                # a whole-stack db answers a range-limited question through the layer checkboxes.
                remedy = ("; the db covers the whole stack - select layers with the checkboxes "
                          "instead of --min-layer/--max-layer"
                          if recorded_params.get(key) is None and params.get(key) is not None
                          else "; re-dump, or pass the same --min-layer/--max-layer")
            return (f"{key} is {params.get(key)!r}, the db was written with "
                    f"{recorded_params.get(key)!r}{remedy}")
    if layers is not None:
        recorded_layers = header.get("layers", [])
        if sorted(recorded_layers) != sorted(layers):
            return (f"the measured layers are {_fmt_names(layers)}, the db has "
                    f"{_fmt_names(recorded_layers)}")
    if tech_key is not None and header.get("tech_key") != tech_key:
        return "the tech LEF changed since the db was written"
    if lef_key is not None and header.get("lef_key") != lef_key:
        return "the macro LEFs changed since the db was written"
    if geometry is not None:
        rows, cols, extent = geometry
        if (header.get("rows"), header.get("cols")) != (int(rows), int(cols)) \
                or not _same_extent(header.get("extent"), extent):
            # The remedy is a re-dump only when the grids are all there is: a db that carries the
            # shapes is one the caller can rasterise here, and telling its user to re-dump a block
            # the run is about to draw anyway is the kind of advice that teaches nothing.
            remedy = ("" if db.has_geometry else
                      " - re-dump it with its design's db (--db <design's db> --def <this DEF>)")
            return (f"the db covers a {header.get('rows')} x {header.get('cols')} grid"
                    f"{_die_note(header.get('extent'))}, this run's is {int(rows)} x {int(cols)}"
                    f"{_die_note(extent)}; a block dumped on its own is written in its own "
                    f"coordinates{remedy}")
    if frames is not None and [tuple(frame) for frame in frames] != db.frames:
        return (f"the hierarchy places this block {_fmt_frames(frames)}, the db was written for "
                f"{_fmt_frames(db.frames)}")
    return None


def header_for(*, block: AnyStr, top_name: AnyStr, rows: int, cols: int,
               extent: Sequence[float], grid_size: float, params: Dict,
               def_note: Dict, tech_key: str, tech_count: int, lef_key: str, lef_count: int,
               layers: Sequence[AnyStr], boundary, frames, component_cells: Sequence[AnyStr],
               totals: Dict, layer_stats: Dict, stats: Dict, db_unit=None) -> Dict:
    """The JSON half of a db, assembled in one place so `save` and `load` cannot drift.

    ``layer_stats["rows"]`` is positional in the live build - one row per layer of the *trimmed*
    stack - so it is stored keyed by layer name, and put back into position by the loader.

    No warnings are stored, deliberately: every warning this build raises is derived from live
    data - the LEF, the components, the totals - so a reused block regenerates exactly the ones
    that still apply, and a stored copy could only go stale.
    """
    return {
        "format": DB_FORMAT,
        "version": __version__,
        "block": str(block),
        "top_name": str(top_name),
        "rows": int(rows),
        "cols": int(cols),
        "extent": [float(v) for v in extent],
        "grid_size": float(grid_size),
        "params": dict(params),
        "def": dict(def_note),
        "tech_key": tech_key,
        "tech_count": int(tech_count),
        "lef_key": lef_key,
        "lef_count": int(lef_count),
        "layers": [str(name) for name in layers],
        "orientations": list(ORIENTATIONS),
        "boundary": None if boundary is None else [[float(x), float(y)] for x, y in boundary],
        "frames": [[str(orient), float(x), float(y)] for orient, x, y in frames],
        # The DEF's database unit, because a stored section is in its own integers: a replay
        # divides by this to get microns, and only the run that read the DEF knew it.
        "db_unit": None if db_unit is None else float(db_unit),
        "component_cells": [str(name) for name in component_cells],
        "totals": {str(key): int(value) for key, value in totals.items()},
        "layer_stats": {"rows": {name: [int(v) for v in row] for name, row in
                                 layer_stats["rows"].items()},
                        "filtered_by_layer": dict(layer_stats["filtered_by_layer"]),
                        "via_points_by_layer": dict(layer_stats["via_points_by_layer"]),
                        "via_unattributed": int(layer_stats["via_unattributed"])},
        "stats": dict(stats, layers_used=sorted(stats["layers_used"])),
    }
