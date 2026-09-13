"""Placing each block's wiring in global coordinates.

Several DEF files are one design when each is a complete block of a hierarchy. The wiring
inside a sub-block's DEF is written in that block's **local** frame, exactly as its
instances are, so it has to be composed through the same chain of placements to land in the
right place globally.

The composition is sound for wires because every DEF orientation is a rotation by a multiple
of 90 degrees plus an optional axis reflection (:mod:`vlsi_viewer.coordinateProcess` holds
the table). Those maps take axis-aligned rectangles to axis-aligned rectangles - the min/max
of two transformed opposite corners is exact, not an approximation - and take a segment to a
segment while preserving its direction class: axis-x and axis-y swap under a quarter turn,
and a 45-degree diagonal stays one. So a rectangle can be transformed as a rectangle, and
only a diagonal has to be transformed as two separate points.

This module deliberately does not touch :func:`physical.build_physical`. That function's frame
walk is a closure over a dozen side-effect lists with twenty-odd tests pinning it, so the metal
path gets its own walker here rather than a refactor of a working one.
"""
from __future__ import annotations

import logging
from typing import AnyStr, Callable, Dict, List, Sequence, Tuple

import numpy as np

from .coordinateProcess import CoordinateProcess, Orient

logger = logging.getLogger(__name__)


def find_single_top(blocks: Dict[AnyStr, tuple]) -> AnyStr:
    """The one block no other block instantiates.

    Raises ``ValueError`` if there is not exactly one, naming what it found. A design whose
    blocks do not connect - two unrelated DEFs passed together - has no single top and no
    single coordinate system, so there is nothing sensible to draw.
    """
    referenced = set()
    for frame, _boundary in blocks.values():
        referenced.update(frame["cell_name"].dropna().astype(str).unique())
    tops = [name for name in blocks if name not in referenced]
    if len(tops) != 1:
        raise ValueError(
            f"metal mode requires exactly one top-level block; found {len(tops)}"
            + (f": {', '.join(sorted(tops))}" if tops else " (none)"))
    return tops[0]


# The eight DEF orientations as 2x2 linear maps, read straight off
# `CoordinateProcess.dbTransform`'s to_global branch, which is always of the form
# `p -> M p + origin`:
#
#   N  (x0 + x, y0 + y)    W  (x0 - y, y0 + x)    FN (x0 - x, y0 + y)    FW (x0 + y, y0 + x)
#   S  (x0 - x, y0 - y)    E  (x0 + y, y0 - x)    FS (x0 + x, y0 - y)    FE (x0 - y, y0 - x)
#
# Composing these as matrices is not the same as merging the orientation *names*. The
# tempting shortcut is `Orient.mergeOrient`, which combines mirrors by XOR-ing global X and Y
# flags - but a child's mirror axis rotates with a rotated parent, so that is wrong for
# every (rotated parent, mirrored child) pair. The 64-pair test exists because of it.
_ORIENT_MATRIX = {
    "N": ((1, 0), (0, 1)),
    "S": ((-1, 0), (0, -1)),
    "W": ((0, -1), (1, 0)),
    "E": ((0, 1), (-1, 0)),
    "FN": ((-1, 0), (0, 1)),
    "FS": ((1, 0), (0, -1)),
    "FW": ((0, 1), (1, 0)),
    "FE": ((0, -1), (-1, 0)),
}
_MATRIX_ORIENT = {matrix: name for name, matrix in _ORIENT_MATRIX.items()}


class Frame:
    """Where a block sits in global coordinates: ``p -> M p + origin``.

    ``apply_rect`` transforms an axis-aligned rectangle; ``apply_point`` transforms a single
    point. A diagonal needs the point form - transforming it as a rectangle would collapse it
    to its bounding box, which for a 10 um diagonal over-counts by about 25x.
    """

    __slots__ = ("matrix", "origin")

    def __init__(self, orient: AnyStr = "N", origin: Tuple[float, float] = (0.0, 0.0)):
        try:
            self.matrix = _ORIENT_MATRIX[orient or "N"]
        except KeyError:
            raise ValueError(f"unknown DEF orientation {orient!r}") from None
        self.origin = (float(origin[0]), float(origin[1]))

    @classmethod
    def _from_matrix(cls, matrix, origin) -> "Frame":
        frame = cls.__new__(cls)
        frame.matrix = matrix
        frame.origin = origin
        return frame

    @property
    def orient(self):
        """The orientation name for this frame's matrix, for display."""
        return _MATRIX_ORIENT.get(self.matrix)

    def apply_point(self, x: float, y: float) -> Tuple[float, float]:
        (a, b), (c, d) = self.matrix
        x = float(x)
        y = float(y)
        return (a * x + b * y + self.origin[0], c * x + d * y + self.origin[1])

    def apply_rect(self, x0, y0, x1, y1):
        """Transform a batch of rectangles, vectorised.

        Two opposite corners are transformed and re-normalised. That is exact, not an
        approximation: every DEF orientation is a quarter-turn rotation with an optional
        axis reflection, so it maps axis-aligned rectangles to axis-aligned ones and takes
        opposite corners to opposite corners.
        """
        (a, b), (c, d) = self.matrix
        ox, oy = self.origin
        ax = a * np.asarray(x0, dtype=np.float64) + b * np.asarray(y0, dtype=np.float64) + ox
        ay = c * np.asarray(x0, dtype=np.float64) + d * np.asarray(y0, dtype=np.float64) + oy
        bx = a * np.asarray(x1, dtype=np.float64) + b * np.asarray(y1, dtype=np.float64) + ox
        by = c * np.asarray(x1, dtype=np.float64) + d * np.asarray(y1, dtype=np.float64) + oy
        return (np.minimum(ax, bx), np.minimum(ay, by),
                np.maximum(ax, bx), np.maximum(ay, by))

    def compose(self, orient: AnyStr, origin: Tuple[float, float]) -> "Frame":
        """The frame of a child placed at ``origin`` with ``orient`` inside this one.

        A point goes through the child's map and then through this one, so the matrices
        multiply and the child's origin is pushed through this frame:
        ``M = M_parent M_child``, ``t = M_parent t_child + t_parent``.
        """
        try:
            child = _ORIENT_MATRIX[orient or "N"]
        except KeyError:
            raise ValueError(f"unknown DEF orientation {orient!r}") from None
        (a, b), (c, d) = self.matrix
        (e, f), (g, h) = child
        product = ((a * e + b * g, a * f + b * h), (c * e + d * g, c * f + d * h))
        return Frame._from_matrix(product, self.apply_point(*origin))

    def __repr__(self):
        return f"Frame({self.orient or '?'}, {self.origin})"


class HierarchyAssembler:
    """Walks a merged block table, handing each block its global frame.

    ``blocks`` maps a block name to ``(instances_dataframe, boundary)``, the shape
    ``metrics._merge_blocks`` produces. Instances whose ``cell_name`` names another block are
    the edges of the tree; everything else is a leaf.
    """

    def __init__(self, blocks: Dict[AnyStr, tuple], cells=None):
        self.blocks = blocks
        self.cells = cells
        self.missing: List[AnyStr] = []

    def instances(self, name: AnyStr):
        return self.blocks[name][0]

    def boundary(self, name: AnyStr):
        return self.blocks[name][1]

    def walk(self, top: AnyStr, on_block: Callable) -> None:
        """Call ``on_block(name, frame)`` for ``top`` and every block beneath it.

        Depth-first and outermost-first, so a caller accumulating into shared grids sees
        blocks in a stable order. A block reachable by more than one path is visited once
        per path, which is correct: it really does appear in several places, and each
        appearance contributes its own wires.
        """
        self.missing = []
        self._visit(top, Frame(), (), on_block)

    def _visit(self, name: AnyStr, frame: Frame, visiting: Sequence[AnyStr],
               on_block: Callable) -> None:
        if name in visiting:
            raise ValueError(
                "block hierarchy is cyclic: " + " -> ".join(list(visiting) + [str(name)]))
        on_block(name, frame)

        instances = self.instances(name)
        if instances is None or instances.empty:
            return
        chain = tuple(visiting) + (name,)
        for child_name, child_frame in self._child_frames(instances, frame):
            self._visit(child_name, child_frame, chain, on_block)

    def _child_frames(self, instances, frame: Frame):
        """``(block_name, frame)`` for every instance that names a block."""
        known = set(self.blocks)
        for row in instances.itertuples():
            model = str(getattr(row, "cell_name"))
            if model in known:
                yield model, frame.compose(getattr(row, "orient", "N") or "N",
                                           (getattr(row, "location_x", 0.0),
                                            getattr(row, "location_y", 0.0)))
            elif self.cells is not None and model not in self.cells.index:
                self.missing.append(model)
