# Dynamic / leakage power metrics in the hierarchy tree

## Goal

Roll up the per-instance `dynamic_power` and `leakage_power` attributes to every hierarchy
node, shown as two new tree columns. When the loaded input carries no power data, both
columns start hidden; they remain available in the existing Metrics menu.

## Semantics (user decisions)

- Power includes macros and excludes physical-only and missing instances — the same rule as
  the leakage/dynamic heat maps and the selected-region tree.
- Compare mode shows the power and Δpower columns when either design carries power, and
  hides them when neither does.

## Presence detection

The loader replaces absent attributes with their `0.0` default, so presence must be
recorded before that:

- `loader._block_from_data` sets `df.attrs["has_power"]` when any instance dict actually
  carries `leakage_power` or `dynamic_power` (a supplied `0.0` counts).
- `metrics._merge_blocks` and `metrics.load_blocks` OR the flag explicitly
  (`combine_first`/`concat` drop attrs).
- `DesignData` gains `has_power`; `CACHE_VERSION` is bumped and `load_or_build` rejects old
  pickles that lack the attribute.

## Aggregation and columns

- `RAW_COLS` gains `leakage_power`, `dynamic_power`; `_flatten` sums them over
  non-missing, non-physical-only leaves in a separate frame (the std/macro assignment
  overwrites, so power must not share those lists).
- `schema.METRICS` gains two `kind="power"` specs after `bi_area`, so all views (tree,
  search, region, compare) pick them up from the registry.
- `format_metric` / `format_delta_abs` render power like area (two decimals, signed for
  deltas).
- `RegionData.stats` supplies both raw keys from the physical per-box arrays, weighted by
  the selection overlap.

## Visibility

- `MainWindow` seeds `_hidden_metrics` with the power keys when `design1.has_power` is
  false and applies them to the main and region trees before the first settings pass; the
  Metrics menu then shows them unchecked and can re-enable them.
- `CompareWidget` hides V1/V2 power keys and Diff `_abs`/`_rel` keys when neither design
  has power; `model.diff_columns` gives Δabsolute columns a key so they can be targeted.

## Verification

- New tests: presence (including zero-valued keys), aggregation (macro inclusion,
  physical-only/missing exclusion), formatting, cache round-trip, region equality,
  default-hidden/shown behaviour in single, region and compare views.
- Full suite, plus a headless check that the bundled physical sample reports
  `has_power=True` and the bundled compare sample `False`.
