# Six-placement quickstart samples (x-flip / y-flip orientations)

## Goal

Expose block-level flip orientations in the quickstart demos. Both bundled samples grow
from a 2x2 to a 3x2 array so all four rotations stay and both axis flips appear:
`N, W, S, E, FN, FS` (FN = x flip, mirror about Y; FS = y flip, mirror about X).

No viewer code changes are needed; the transform paths are matrix-driven and the
`placement_origin` fix anchors flipped blocks correctly. This is sample data plus tests,
docs and screenshots.

## Physical sample (750 x 495)

- `CORE_GAP = 45`; slots at `x = 15 + col*255`, `y = 15 + row*255`; orientations N, W, S,
  E, FN, FS row-major.
- Uncore cross for two vertical gaps: four 45x210 strips sharing 15,000 cells; full-width
  band (15, 225, 720, 45) with 8 L2 SRAMs at x=21 and x=531, 3,000 arm cells.
- 153,600 std cells + 50 SRAMs; 153,650 expanded leaves; density ~0.597.
- `verify()` count bound 140k-170k.

## Metal sample (920 x 620)

- `SUB_ORIENTS = ("N","W","S","E","FN","FS")`; die (920, 620), slots at x=30/330/630,
  y=30/330.
- Totals 6*19,817 + 9 = 118,911 emitted, 6*135 = 810 jogs. The top-level shape counters
  (9/8/1/3, area 15,242.88) are unchanged because `area_um2` sums rectangles and the
  stripes keep their length (die height stays 620).

## Verification

- Both generators print `verify: OK`; only the physical `instance_info.json` and the metal
  `top.def` change.
- Sample tests updated from four to six placements; new assertions pin the six-orientation
  set.
- New direct block-level FN/FS coverage: a metal wire, an L-shaped block outline, and a
  physical pin/box under a flipped parent.
- Full pytest suite; regenerate the physical and metal screenshots.
