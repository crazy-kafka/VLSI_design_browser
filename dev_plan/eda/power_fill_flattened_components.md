# Power-JSON fill: flattened components and the incremental-addon rule

Status: implemented (see `dev_plan/eda/power_json_fill.md` for the base format).

## Problem

A real DEF case (`dev_plan/issues/real_design_case_power_json_flattened_block.md`) had its
leakage/dynamic values missing from both `gpu_sp_top` placements. DEF writes sub-block
instances as flattened, multi-segment component names
(`U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp`); `_resolve` in
`vlsi_viewer/parsers/convert.py` split the record key at the first `/` only, so it never
found the multi-segment container. The records were reported as "filled no instance".

The matching fix alone was not enough: the fill wrote into the shared block table, so every
placement of a reused block got the same value. The real case can have a different switching
toggle per placement.

## Rule of the incremental JSON addon

`--json` fills attributes into the converted DEF/Verilog blocks. There are two scopes:

| file form | key | power attrs | structural attrs |
|---|---|---|---|
| per-block (`top_name` = a sub-block) | block-relative (`u1`) | one shared value for every placement | shared block definition; every placement |
| flattened top (`top_name` = a design root), key resolves to the top's own leaf | root-relative or root-prefixed | shared/top table (the top is placed once) | shared/top table (unique) |
| flattened top, key resolves inside a sub-block | root-relative or root-prefixed | per-placement override keyed by the absolute hierarchy path | an absent value only when that block has exactly one placement; on a multi-instantiated block it is a placement conflict: not written, counted, warned |

Power (`leakage_power`, `dynamic_power`) is the only attribute class that may differ per
placement. Everything else (`cell_name`, `orient`, `location_x/y`, `is_physical_only`)
describes the block definition and must go through a block-level file when the block is
reused.

Mixed files are allowed: a block-level default plus flattened overrides; the override wins
for the named placement. Two files setting the same override differently: the first wins,
the second is a conflict.

## Implementation

1. **Resolver** (`convert.py::_resolve`, `_target`): whole-key match first, then every
   `/`-prefix longest first, descending into a block only when the prefix names one.
   `_resolve` returns `(owner_block, entry)`; `_target` returns the resolution plus the
   relative key of the successful form, so the absolute path is `top + "/" + relative_key`.
2. **Fill** (`convert.py::fill_instances`): root files resolving into a descendant write
   power to a per-placement `power_overrides` map on the root block dict; structural
   attributes are written only when the owner block has one placement, otherwise counted in
   `FillSummary.placement_conflicts` and warned. Block-level files keep the old shared
   behavior. `_shape` walks each placement with its absolute prefix and counts shared fills
   plus this run's override paths.
3. **Readers**: the loader reads `power_overrides` from a block dict into
   `df.attrs["power_overrides"]`; `metrics.load_blocks` and `physical.walk` apply it by
   absolute leaf path (power columns / per-box power). `_merge_blocks` merges the map.
4. **Round trip**: `--out` writes the block dicts verbatim, so the map is in the dump and
   the `json` subcommand reloads it.
5. Docs: README power section and input-format table; `dev_plan/eda/power_json_fill.md`;
   `PARSERS.md`.

## Tests

- Real-shaped synthetic: two flattened sp records with different values land on the two
  placements; equal values light both; a block-level file lights both with one value; a
  block-level default plus one override keeps the other default.
- Resolver: multi-segment container, longest-prefix fallback, top-prefixed form, flat
  top-level leaf still wins by whole-key match.
- Structural guard: multi-instantiated flattened structural value rejected and warned;
  single-placement accepted; block-level accepted.
- Summary counts: one flattened key counts one design instance; block-level counts every
  placement.
- `--out`/`json` round trip of per-placement values.
