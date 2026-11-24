# Filler instance drop rule: master name, instance name, physical flag and DIST

Status: current.

## Problem

A post-filler-insertion DEF from the physical-design flow used both `FILL*` and `DCAP*`
master cells for row fill, and every inserted instance carried a `FILL*` instance name.
The DEF converter dropped only components whose **master cell name** started with `FILL`,
so the `DCAP*` row fill survived.

`cell_info_from_lef` marks `DCAP*` cells `is_physical_only`, and physical mode counts
physical-only area in the density grid (it zeroes their leakage/dynamic/ULVT and omits
them from the contour and `Density%`). The surviving decap row fill therefore tiled the
core and drove the density heat map to ~90–100% everywhere.

## Rule

A DEF component is filler and is dropped at conversion when either condition holds:

1. its LEF master (`model_name`) starts with `FILL*`; or
2. its own leaf instance name starts with `FILL*`, **and** the instance is physical-only
   — the LEF cell table's `is_physical_only` flag, or the DEF component's
   `+ SOURCE DIST` clause.

Matching is case-insensitive. The leaf name is the segment after the last `/`, because
flattened DEFs write components such as `u0/b0/fill_16_25`. `DCAP*`/`GDCAP*`/`TAP*`
instances whose own names do not start with `FILL` are kept and flagged physical-only, as
before.

Rule 2 is deliberately `AND (is_physical_only OR DIST)`: a `FILL*`-named logic instance
without a physical flag or `DIST` survives. A DEF that marks every component
`+ SOURCE DIST` (both sample generators do) will drop any `FILL*`-named instance, which
is the requested behavior.

## Implementation

- `vlsi_viewer/parsers/convert.py::_is_filler_instance(comp, cells=None)` holds the two
  rules.
- `instance_info_from_def(def_path, top=None, cells=None)` uses it. `cells` is the
  `cell_info_from_lef` table; only `is_physical_only` is read. When it is omitted, or the
  model is absent from it, `_is_physical_only_name` (the same name heuristic that builds
  the table) stands in, so `metal.py`, the sample generator and existing callers keep
  their behavior. A supplied table entry is authoritative.
- `vlsi_viewer/cli.py::resolve_inputs` passes the already-computed LEF table for both the
  primary and the compare DEF conversions.
- `DefParser.IGNORE_FILLER` (default `False`, no caller sets it) is untouched; the
  conversion filter remains the single authority. `--json`-filled instance flags run
  after conversion and cannot affect the drop.

## Tests

- `tests/test_parsers_eda.py::test_def_filler_drop_uses_master_instance_name_and_flags`:
  the rule matrix — master `FILL*`, FILL-named decap (cell flag), mixed case, FILL-named
  logic with `DIST`, FILL-named logic without either (kept), hierarchy leaf not `FILL`
  (kept), plain `dcap_*`/`tap_*` (kept).
- `...::test_def_filler_drop_reads_is_physical_only_from_the_cell_table`: a supplied
  `is_physical_only` on an unrecognized master is authoritative; without the table the
  instance is kept.
- `...::test_def_filler_drop_without_cells_uses_the_name_heuristic`: the `metal.py`
  calling shape.
- `...::test_fill_named_decap_row_fill_no_longer_pegs_density`: five FILL-named `DCAP_4`
  row-fill instances tiling the die plus one logic cell; after conversion the
  `build_physical` density max is < 0.5 (it reaches 1.0 before the fix).
- `tests/test_cli.py::test_def_flow_passes_the_cell_table_to_both_conversions`: both DEF
  conversions receive the same `cells` object.

## Notes / limits

- Leaf extraction assumes `/` as the hierarchy divider; the rest of the converter already
  does (`_resolve`, flattened sample names).
- The `cells` lookup is an exact, case-sensitive model-name match (as are LEF/DEF names);
  a miss falls back to the name heuristic.
- `metal.py` gets the fallback behavior without a code change; its component counts can
  change on DEFs containing `FILL*`-named physical instances.

See [eda_file_support_asbuilt.md](eda_file_support_asbuilt.md) for the phase history and
`README.md`/`PARSERS.md` for the user-facing behavior.
