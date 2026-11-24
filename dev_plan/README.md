# `dev_plan` index

Development notes for the VLSI design browser: requirements, approved plans, as-built
records, measurements, real-design logs, and reference material. The files are grouped by
the code area they describe; a plan, its evaluations, and its as-built record stay
together.

Statuses:

- **current** — describes the code as it is now, or the decision in force.
- **historical** — shipped and kept for the measurement/decision trail.
- **superseded** — replaced by another document; kept for history.
- **reference** — syntax/reference material, not project history.

When adding a document, put it in the matching folder and add a row here. Use
`<area>_plan.md` for an approved plan, `<area>_asbuilt.md` for what shipped, and keep
issue reports under `issues/` with a cross-link to their fix.

## Issues and real-design evidence (`issues/`)

Reports and logs from runs on real designs. Fix records live with their subsystem and are
linked from here.

| document | summary | status |
|---|---|---|
| [real_design_case_record.md](issues/real_design_case_record.md) | 2026-09-13 first real metal run on `lx956c_ioe`, log and GUI snapshot. | historical |
| [real_design_log_0914.md](issues/real_design_log_0914.md) | Two 09-14 runs with turnaround and cProfile analysis. | historical |
| [real_design_log_0915.md](issues/real_design_log_0915.md) | First `--jobs 8` run: 1,780 s routing against 5,941 s single-core. | historical |
| [real_design_log_0916.md](issues/real_design_log_0916.md) | Second 8-worker run: per-layer statistics and job statistics. | historical |
| [real_design_log_0917.md](issues/real_design_log_0917.md) | Two DB-only runs; one completes, one fails with a grid mismatch. | historical |
| [real_design_log_0921.md](issues/real_design_log_0921.md) | `def --json` silence: the quadratic fill diagnosis. | historical |
| [real_design_subblock_layout_1119.md](issues/real_design_subblock_layout_1119.md) | FN `gen_sp_1_u_sp` missing from the layout map. | superseded by [oriented_block_placement_fix.md](physical/oriented_block_placement_fix.md) |
| [issue.tech_layer_detect.md](issues/issue.tech_layer_detect.md) | Region layers misclassified as routing; wrong W/S/P for several layers. | superseded by [tech_lef_layer_extraction.md](eda/tech_lef_layer_extraction.md) |
| [thread_error.md](issues/thread_error.md) | `--jobs 8` aborts on `_thread.lock` pickling. | superseded by [pooled_cancel.md](performance/pooled_cancel.md) |
| [real_design_case_power_json_flattened_block.md](issues/real_design_case_power_json_flattened_block.md) | Flattened component names leave both `gpu_sp_top` placements without power. | superseded by [power_fill_flattened_components.md](eda/power_fill_flattened_components.md) |

Known dangling references: the flattened-power report links
`real_design_case_fn_block_placement.md` and `../../issue_reproduce/…`, and the 09-21 log
mentions `dev_plan/bench_fill.py`; none of these exists in this checkout.

## EDA files, parsers, and power fill (`eda/`)

LEF/DEF/Verilog support, parser audits, and the incremental `--json` fill.

| document | summary | status |
|---|---|---|
| [EDA_file_support.md](eda/EDA_file_support.md) | Requirements and proposed CLI for LEF/DEF/Verilog input. | superseded by [eda_file_support_asbuilt.md](eda/eda_file_support_asbuilt.md) |
| [eda_file_support_asbuilt.md](eda/eda_file_support_asbuilt.md) | What was built: parser relocation, converters, CLI, verification, limits. | current |
| [def_net_parsing_audit.md](eda/def_net_parsing_audit.md) | Audit and fix of latent DEF `NETS`/`SPECIALNETS` parsing defects. | historical |
| [tech_lef_layer_extraction.md](eda/tech_lef_layer_extraction.md) | Fix for three tech-LEF layer-extraction defects. | historical |
| [power_json_fill.md](eda/power_json_fill.md) | `--json` fill for `def`/`verilog`, including the O(N²) and flattened-component fixes. | current |
| [power_fill_flattened_components.md](eda/power_fill_flattened_components.md) | Resolver and per-placement power fix for flattened block component names. | current |
| [filler_instance_drop_rule.md](eda/filler_instance_drop_rule.md) | Corrected DEF filler drop: FILL master, or FILL instance name with physical-only/DIST. | current |

## Metal mode (`metal/`)

Metal-density map, routing/db performance, layer statistics, and the metal GUI. The
as-built record is the operative phase-by-phase history.

| document | summary | status |
|---|---|---|
| [metal_density_mode.md](metal/metal_density_mode.md) | Initial metal-mode requirements: density metric, layer groups, UI, testing. | superseded by [metal_density_plan.md](metal/metal_density_plan.md) |
| [metal_density_plan.md](metal/metal_density_plan.md) | Approved metal-density plan: metric, parser/raster/assembly, GUI, samples. | superseded by [metal_density_asbuilt.md](metal/metal_density_asbuilt.md) |
| [metal_density_asbuilt.md](metal/metal_density_asbuilt.md) | Master phase-by-phase metal record (0a–21): implementation, performance, bugs. | current |
| [metal_def_db.md](metal/metal_def_db.md) | Intermediate metal db so map rebuilds skip routing reparse. | current |
| [metal_def_db_eval.md](metal/metal_def_db_eval.md) | Measured pre/post cost of a geometry-carrying metal db. | historical |
| [metal_gui_layout_split.md](metal/metal_gui_layout_split.md) | Cell detail to the left, layer range to the toolbar (Phase 10). | historical |
| [metal_gui_polish.md](metal/metal_gui_polish.md) | Blank sidebar, boundary bug, readability (Phase 9). | historical |
| [metal_layer_range.md](metal/metal_layer_range.md) | `--min-layer`/`--max-layer` filtering (Phase 18). | historical |
| [metal_layer_table.md](metal/metal_layer_table.md) | Per-layer shape statistics at the end of routing. | historical |
| [metal_layer_table_followup.md](metal/metal_layer_table_followup.md) | Corrections after the 09-16 run: placement counts, discrepancy, formatting. | historical |
| [macro_obs_blockage.md](metal/macro_obs_blockage.md) | Real macro LEF `OBS` geometry replaces the layer-count heuristic (Phase 13). | historical |
| [metal_read_round2.md](metal/metal_read_round2.md) | Round 2: single-core cost of the chip-level read (Phase 20). | historical |
| [metal_round3.md](metal/metal_round3.md) | Round 3: diagonal counts, routing imbalance, byte-range work units, readable logs. | historical |
| [metal_routing_performance.md](metal/metal_routing_performance.md) | The 7,005-second routing read: locate and remove the cost (Phase 15). | historical |
| [metal_work_units_eval.md](metal/metal_work_units_eval.md) | Byte-range work-unit evaluation against a pre-registered bar; left disabled. | historical |

## Physical mode, heat maps, and contours (`physical/`)

Physical layout, heat-map grids and legends, contours, and placement fixes.

| document | summary | status |
|---|---|---|
| [physical_mode.md](physical/physical_mode.md) | Initial physical-mode spec: layout view, coordinates/orientations, CLI, tests. | historical |
| [heatmap_innovus_gradient.md](physical/heatmap_innovus_gradient.md) | INNOVUS heat-map ramp and per-map min/max preservation. | current |
| [heatmap_interactive_feature_plan.md](physical/heatmap_interactive_feature_plan.md) | Selectable heat-map region, region hierarchy tree, measured results. | current |
| [hierarchy_contour.md](physical/hierarchy_contour.md) | Contour display and the hierarchy Density% metric. | current |
| [contour_density_performance.md](physical/contour_density_performance.md) | Contour/density performance plan and its measured as-built. | current |
| [pin_density_map.md](physical/pin_density_map.md) | Hierarchy area sort and the pin-density map. | current |
| [ulvt_density_map.md](physical/ulvt_density_map.md) | ULVT density as a fourth physical-mode heat map. | current |
| [bi_dynamic_power.md](physical/bi_dynamic_power.md) | Data-path B/I dynamic-power metric + heat map; density-first map order. | current |
| [thermal_gradient_128.md](physical/thermal_gradient_128.md) | The earlier 7-stop, 128-step thermal ramp. | superseded (colors) by [heatmap_innovus_gradient.md](physical/heatmap_innovus_gradient.md) |
| [vertical_fixed_legend.md](physical/vertical_fixed_legend.md) | Vertical top-right color legend with five value ticks. | current |
| [grid_cli_and_hover.md](physical/grid_cli_and_hover.md) | Grid size via CLI and the hover coordinate/grid readout. | current |
| [oriented_block_placement_fix.md](physical/oriented_block_placement_fix.md) | Correct oriented-placement origin; fixes issue 1119. | current |

## User interface (`ui/`)

Cross-mode UI behavior and documentation work.

| document | summary | status |
|---|---|---|
| [metrics_menu.md](ui/metrics_menu.md) | Metrics menu of checkboxes to show/hide hierarchy columns. | current |
| [power_tree_metrics.md](ui/power_tree_metrics.md) | Dynamic/leakage power rollups as tree columns, hidden when absent. | current |
| [search_results_ui.md](ui/search_results_ui.md) | Sortable search-results popup with correct row-to-path jump. | current |
| [readme_for_visitors.md](ui/readme_for_visitors.md) | README rewrite around three real captures, anchors preserved. | historical |

## Performance (`performance/`)

Cross-subsystem parser and parallel-reader performance work. Metal-specific studies are
under `metal/`.

| document | summary | status |
|---|---|---|
| [performance_improvement.md](performance/performance_improvement.md) | Static bottleneck ranking and six speedup proposals for metal turnaround. | historical |
| [parse_once_flow.md](performance/parse_once_flow.md) | Eliminate duplicate LEF/block/DEF reads in the `--jobs` flow (Phase 17). | historical |
| [pooled_cancel.md](performance/pooled_cancel.md) | Cross-process cancel/^C for `--jobs`; fixes `thread_error.md` (Phase 19). | historical |
| [pooled_reader_stride.md](performance/pooled_reader_stride.md) | Workers read only their stride; the final `--jobs` blocker (Phase 21). | historical |

## Sample data (`samples/`)

The committed samples, their provenance, and the quickstart scenarios.

| document | summary | status |
|---|---|---|
| [cpu_cluster_sample.md](samples/cpu_cluster_sample.md) | Six-core, 153,650-instance physical sample; nested frame composition fix. | current |
| [orientation_sample_expansion.md](samples/orientation_sample_expansion.md) | Six-placement quickstart samples covering rotations and x/y flips. | current |
| [realistic_sample_placement.md](samples/realistic_sample_placement.md) | Rework of the flat physical sample into a realistic density field. | historical (sample superseded by [cpu_cluster_sample.md](samples/cpu_cluster_sample.md)) |
| [real_sample_sources.md](samples/real_sample_sources.md) | Survey and provenance of real DEF/LEF sources and the vendored files. | current |

## Reference (`reference/`)

Syntax and color references, not project history.

| document | summary | status |
|---|---|---|
| [LEF_DEF_syntax reference.md](reference/LEF_DEF_syntax%20reference.md) | Condensed LEF/DEF 5.8 syntax guide: layers, macros, vias, nets, orientations, units. | reference |
| [lefdefref.pdf](reference/lefdefref.pdf) | Cadence LEF/DEF 5.8 Language Reference (proprietary, reference-only). | reference |
| [extractCellInfo.py](reference/code_sample/extractCellInfo.py) | Illustrative LEF-to-`cell_info.json` generator. | reference |
| [heatmap_color.py](reference/code_sample/heatmap_color.py) | 127-entry INNOVUS `QColor` ramp used as the heat-map color reference. | reference |

## Archive (`archive/`)

Superseded early plans and prompt drafts, kept for history.

| document | summary | status |
|---|---|---|
| [initial.md](archive/initial.md) | Original project requirements and architecture. | superseded by [initial_plan.md](archive/initial_plan.md) |
| [initial_plan.md](archive/initial_plan.md) | Formal v1 plan: data model, metrics, tree GUI, search/sort/diff, tests. | superseded by the shipped design |
| [plan-performanceOptimization.prompt.md](archive/plan-performanceOptimization.prompt.md) | Static performance-review prompt for physical mode. | superseded by later performance work |
| [plan-responsivePhysicalMode.prompt.md](archive/plan-responsivePhysicalMode.prompt.md) | Prompt/plan for physical-mode responsiveness. | superseded by [contour_density_performance.md](physical/contour_density_performance.md) and [heatmap_interactive_feature_plan.md](physical/heatmap_interactive_feature_plan.md) |
