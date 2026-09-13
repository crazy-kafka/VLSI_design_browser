# DEF net parsing audit and fix

An audit of `DefParser.__extractNets` / `__extractSpecialNets` against
`dev_plan/LEF_DEF_syntax reference.md` (DEF 5.8). Every defect was reproduced against the
actual compiled regexes, then fixed. Spec line numbers below refer to that document.

## Why this was latent

`parse_net` and `parse_specialnet` default to `False`, and `__parsingStart` deletes those
entries from the dispatch table, so neither function ever ran; nothing outside the DEF
package reads `getAllNets`/`wiring`/`connect_pins`. The defects would have surfaced the
moment anyone enabled net parsing for a congestion or connectivity view. The flags are
still `False` by default - the fix changes no shipped behaviour (verified below).

## The defects

The root cause was architectural rather than a handful of sloppy patterns: both functions
parsed **one line at a time with no state**, and the wiring regexes were written for one
narrow shape of the grammar. So the grammar's cross-point semantics (`*` = "reuse the last
coordinate"), multi-segment wires, and three of the four special-wiring forms could not be
expressed at all.

| # | defect | spec |
|---|---|---|
| 1 | `NAME` excluded `[` `]`, so `- data[3]` became `data` - all of `data[0..7]` **merged into one net** - and `( u1 A[2] )` matched nothing, silently dropping the connection | 481 |
| 2 | wiring coordinate classes `[*\d]+` rejected `-`, so a negative-origin design lost **all** wiring | 833-837 |
| 3 | `+ RECT` / `+ POLYGON` / `+ VIA` special-wiring forms unhandled (`+ RECT` and `+ VIA` are the common PG shapes) | 632-643 |
| 4 | `+ SHAPE` between the width and the routing points made the whole wire unmatchable - i.e. RING / PADRING / BLOCKRING / STRIPE / FOLLOWPIN | 636-641 |
| 5 | only the first segment of a multi-point wire survived (one `search` per line, regex capped at two points) | 604-611 |
| 6 | `( * * extValue )` produced `None` coordinates | 837 |
| 7 | `*` resolved per-pair instead of against the last coordinate, giving wrong geometry | 835-836 |
| 8 | SPECIALNETS connections were never parsed - `connect_pins` stayed empty for every power/ground net | 617 |
| 9 | the via capture conflated a via name with its orientation | 609, 637 |
| 10 | `_rule` was computed then ignored, so a per-wire `TAPERRULE` was discarded | 599-601 |
| 11 | `+ COVER` / `+ NOSHIELD` wires were dropped | 599 |
| 12 | connections were lost whenever the statement also carried `+ NONDEFAULTRULE` (the `if/elif` chain short-circuited) | 581-583 |
| 13 | `RECT` point forms broke the consecutive-point pairing | 609-610 |

## The fix

**Read the statement, then parse it.** `__read_statement` joins a statement's lines up to
its `;` (also stopping at an `END <SECTION>` marker, so a malformed statement cannot
swallow the rest of the file). `__split_statement` then divides it into a header and the
wiring text. Everything else follows:

- **Header** (`__statement_net`): the net name and all `( comp pin )` / `( PIN pin )`
  connections, found independently of the other clauses. Connections are read from the
  header only, because a routing point `( 0 0 )` has exactly the same shape as a
  connection `( u1 A )` - a trap the first version of this fix fell into.
- **Wiring text** is cut at the next non-wiring clause (`+ SOURCE`, `+ USE`, `+ VOLTAGE`,
  …) so a trailing clause cannot be read as a via.
- **Forms** (`__add_special_wiring` / `__add_regular_wiring`): `finditer` over a form-start
  pattern, one slice per form, so every segment is emitted and a form cannot be
  re-matched twice. All four special forms are handled, plus `NEW` continuations and
  `SHAPE`/`MASK`/`STYLE`/`TAPER`/`TAPERRULE`.
- **Points** (`__scan_tokens`): one ordered pass yielding points and vias, carrying
  `last_x`/`last_y` across the statement so `*` means what the reference says. A `*` with
  no previous coordinate raises `ValueError` instead of leaking `None` or a literal `'*'`.

Data model: `DefSWire` gains `via_orient` and `shape` (`PATH` / `RECT` / `POLYGON` /
`VIA`), `DefWire` gains `via` / `via_orient`. Both stay one-segment-per-instance. A via
rides the segment **starting** at its point - a choice, not a spec requirement, since
either adjacent segment could claim it.

`compiledRe.py` gained the form-start and point-or-via patterns, `NAME` now admits the bus
brackets, and the wiring coordinates accept negatives. `__decodeWire` was removed: its
per-pair `*` handling was the bug being replaced, and leaving a second, wrong
implementation of the same rule would have invited its reuse.

## Known limits (recorded, not fixed)

- The `;` split is not quote-aware, so a `+ PROPERTY` string value containing `;` would
  still truncate a statement - unchanged from before.
- `MUSTJOIN ( comp pin )` is recorded as an ordinary connection; the "fuse" semantics are
  not represented.
- `+ SUBNET` wiring and `+ VOLTAGE` are not modelled (`DefNet` has no voltage field).
- `VIRTUAL ( x y )` is treated as an ordinary point.
- `DefSWire`'s `RECT` shape is stored as its diagonal and `POLYGON` as its edges - a
  segment-oriented view, which is what a wire model can honestly express. `shape` is
  recorded so a consumer can tell them apart.
- A net appearing in both SPECIALNETS and NETS would accumulate duplicate connections (the
  nets dict is shared, as before).
- `re_routing_point_0` / `re_routing_point_1` in `compiledRe.py` were already unused
  before this work and are left alone.

## Verification

- `tests/test_def_nets.py` (new, 25 tests): one test per finding above, plus the spec's own
  example path `( 100 100 ) ( * 300 ) ( 500 * )` decoding to `(100,100)→(100,300)` then
  `(100,300)→(500,300)`, a statement spanning several lines, trailing clauses not becoming
  vias, and a guard that net parsing is still off by default.
- `python -m pytest -q` → **143 passed** (119 before).
- No product change: `sample_data/eda/core.def` parses identically with and without the
  flags - 4822 components, the same `DESIGN` name, dbUnit and 4-point `DIEAREA`, and the
  same parse time (0.022 s). `instance_info_from_def` still yields 3994 instances.
