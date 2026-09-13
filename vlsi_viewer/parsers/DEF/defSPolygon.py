from __future__ import annotations
from typing import AnyStr, List, Tuple


class DefSPolygon:
    """A ``+ POLYGON layer pt pt pt ...`` special-wire shape, stored whole.

    The per-edge ``DefSWire`` objects the parser also emits cannot be reassembled into
    this: they carry no polygon id, and the edge that closes the ring is never emitted
    (a four-vertex ring yields three edges). A filled polygon's **area** - the only thing
    a metal-density map wants from it - is therefore unrecoverable from the edges alone,
    so it has to be captured where the full vertex list still exists.

    The edges are still emitted alongside, because other consumers are wire-oriented and
    existing tests pin that behaviour.

    Points are in DEF database units.
    """

    def __init__(self, layer_name: AnyStr, pts: List[Tuple[int, int]]):
        self.layer_name = layer_name
        self.pts = [(int(x), int(y)) for x, y in pts]

    def ring(self) -> List[Tuple[int, int]]:
        """The vertex list, closed - the first point repeated at the end."""
        return self.pts + self.pts[:1] if self.pts else []

    def area(self) -> float:
        """Area by the shoelace formula, made non-negative.

        The reference requires a convex polygon but nothing enforces it, and shoelace
        handles a simple concave ring just as well.
        """
        count = len(self.pts)
        if count < 3:
            return 0.0
        total = 0
        for i in range(count):
            x0, y0 = self.pts[i]
            x1, y1 = self.pts[(i + 1) % count]
            total += x0 * y1 - x1 * y0
        return abs(total) / 2.0

    def __repr__(self):
        return (f"DefSPolygon {self.layer_name} {len(self.pts)} pt(s) "
                f"area {self.area():.0f}")
