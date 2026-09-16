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
import time
from dataclasses import dataclass, field
from typing import AnyStr, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import __version__

# Bump when the header's meaning changes. A db written by another format is *refused with a
# message*, never read as if the number still meant what it used to.
DB_FORMAT = 1
DB_SUFFIX = ".db"

# The DEF orientations, in the order the component array's codes use. Re-exported from the layout
# of the array rather than from `coordinateProcess`, so a db's codes cannot move under it.
ORIENTATIONS = ("N", "S", "W", "E", "FN", "FS", "FW", "FE")

_HEADER_KEY = "header"
_COMPONENTS_KEY = "components"
_GRID_PREFIX = "grid__"
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


def save(path, db: BlockDb) -> None:
    """Write one db. Compressed: the grids are mostly zeros."""
    arrays = {_HEADER_KEY: np.asarray(json.dumps(db.header, sort_keys=True)),
              _COMPONENTS_KEY: (np.zeros((0, 4), dtype=np.float64) if db.components is None
                                else np.asarray(db.components, dtype=np.float64))}
    for (layer, scope), grid in db.grids.items():
        arrays[f"{_GRID_PREFIX}{layer}__{scope}"] = np.asarray(grid, dtype=np.float32)
    directory = os.path.dirname(os.path.abspath(str(path)))
    if directory:
        os.makedirs(directory, exist_ok=True)
    # Through a file object, not a name: `savez` appends `.npz` to a name it is given, and the
    # name here is the DEF's own - `A.def.gz` becomes `A.def.db`, not `A.def.db.npz`.
    with open(str(path), "wb") as handle:
        np.savez_compressed(handle, **arrays)


def load(path) -> BlockDb:
    """Read one db. ``allow_pickle=False``: a db is data, never code.

    Raises ``ValueError`` for a file this build cannot read - a different format version, a missing
    header, a truncated file - so a caller can turn it into the reason a block is being re-parsed.
    """
    with open(str(path), "rb") as handle, np.load(handle, allow_pickle=False) as data:
        if _HEADER_KEY not in data.files:
            raise ValueError("no header: not a metal db")
        header = json.loads(str(data[_HEADER_KEY].item()))
        got = header.get("format")
        if got != DB_FORMAT:
            raise ValueError(f"db format {got!r}, this build writes {DB_FORMAT}")
        components = data[_COMPONENTS_KEY] if _COMPONENTS_KEY in data.files else None
        grids = {}
        for key in data.files:
            if not key.startswith(_GRID_PREFIX):
                continue
            layer, _, scope = key[len(_GRID_PREFIX):].rpartition("__")
            grids[(layer, scope)] = data[key]
    return BlockDb(header, grids, components)


def mismatch(db: BlockDb, *, params: Dict, def_note: Dict = None,
             tech_key: str = None, lef_key: str = None,
             layers: Sequence[AnyStr] = None, frames=None) -> Optional[str]:
    """Why this db cannot be used for this run, or ``None`` when it can.

    One sentence, in the order a user would want to read it: the DEF they changed, then the knobs
    they changed, then the layer range, then the libraries, and last the hierarchy - which is the
    one case where the *design* changed rather than the invocation.
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
    for key in _PARAM_KEYS:
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
    if frames is not None and [tuple(frame) for frame in frames] != db.frames:
        return (f"the hierarchy places this block {_fmt_frames(frames)}, the db was written for "
                f"{_fmt_frames(db.frames)}")
    return None


def header_for(*, block: AnyStr, top_name: AnyStr, rows: int, cols: int,
               extent: Sequence[float], grid_size: float, params: Dict,
               def_note: Dict, tech_key: str, tech_count: int, lef_key: str, lef_count: int,
               layers: Sequence[AnyStr], boundary, frames, component_cells: Sequence[AnyStr],
               totals: Dict, layer_stats: Dict, stats: Dict) -> Dict:
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
        "component_cells": [str(name) for name in component_cells],
        "totals": {str(key): int(value) for key, value in totals.items()},
        "layer_stats": {"rows": {name: [int(v) for v in row] for name, row in
                                 layer_stats["rows"].items()},
                        "filtered_by_layer": dict(layer_stats["filtered_by_layer"]),
                        "via_points_by_layer": dict(layer_stats["via_points_by_layer"]),
                        "via_unattributed": int(layer_stats["via_unattributed"])},
        "stats": dict(stats, layers_used=sorted(stats["layers_used"])),
    }
