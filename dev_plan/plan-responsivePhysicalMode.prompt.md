## Plan: Responsive Physical-Mode Exploration

Improve the 10M-instance physical-mode experience while preserving exact contours and current row-click toggle behavior. The primary goal is GUI responsiveness with immediate, truthful progress feedback.

**Steps**

### Phase 1: Measure
1. Instrument physical startup, contour merging/union, density jobs, tree expansion, column resizing, and contour rendering.
2. Record leaf counts, merged-box counts, cache hits, queue depth, loop counts, memory, and timings.
3. Benchmark p95 click feedback, exact-contour completion, density completion, GUI stalls, CPU usage, and memory on representative designs.
4. Identify whether delays come from GUI-thread work, CPU contention, geometry processing, tree construction, or rendering.

### Phase 2: Asynchronous Contours
5. Move `PhysicalData.contour_for()` out of the GUI thread into a bounded physical-mode worker.
6. Add request tokens so obsolete contour results cannot overwrite newer selections.
7. Preserve the current contour while a new one is computing.
8. Show states such as `Computing exact contour...`, then replace the overlay atomically.
9. Clear the contour immediately when the same hierarchy is clicked again.
10. For exceptionally expensive nodes, optionally offer a clearly labeled approximate preview before the exact contour.

### Phase 3: Prioritized Background Work
11. Replace `_LazyDensity`’s use of `QThreadPool.globalInstance()` with a bounded scheduler.
12. Prioritize the selected contour over density calculations.
13. Cancel or deprioritize density work for collapsed or no-longer-visible rows.
14. Ignore stale density results after tree rebuilds or settings changes.
15. Show queued, running, and completed density status in the status bar or layout view.

### Phase 4: Reduce GUI Pauses
16. Batch child insertion in `HierarchyTree._populate()`.
17. Suppress unnecessary updates and sorting during expansion.
18. Remove unconditional `resizeColumnToContents(0)` after every expansion; use a bounded sample or explicit fit action.
19. If large expansions remain slow, migrate toward a lazy `QAbstractItemModel`/virtualized tree.
20. Measure contour `QGraphicsPolygonItem` creation separately from contour calculation and bound rendering cost for very large overlays.

### Phase 5: Remove Redundant Work
21. Reuse parsed block and cell data between normal metrics and physical-mode construction.
22. Deduplicate in-flight contour requests.
23. Share reusable contour intermediates where practical while retaining area-only density calculation when beneficial.
24. Add versioned physical artifact caching keyed by source data, grid size, contour gap, and algorithm version.
25. Optimize `merge_boxes()`, Shapely union, rasterization, or hierarchy construction only after profiling identifies a dominant hotspot.

**Relevant files**

- [vlsi_viewer/ui_layout.py](vlsi_viewer/ui_layout.py) — asynchronous contour lifecycle and overlay rendering.
- [vlsi_viewer/physical.py](vlsi_viewer/physical.py) — contour/density caching, deduplication, instrumentation, and physical cache.
- [vlsi_viewer/model.py](vlsi_viewer/model.py) — bounded density scheduling and stale-result handling.
- [vlsi_viewer/ui_tree.py](vlsi_viewer/ui_tree.py) — batched expansion and column-resize changes.
- [vlsi_viewer/ui_main.py](vlsi_viewer/ui_main.py) — status and progress aggregation.
- [vlsi_viewer/cli.py](vlsi_viewer/cli.py) — startup worker sequencing and shared input loading.
- [vlsi_viewer/contour.py](vlsi_viewer/contour.py) — measured geometry optimization.
- [tests/test_gui_smoke.py](tests/test_gui_smoke.py), [tests/test_physical.py](tests/test_physical.py), and [tests/test_contour.py](tests/test_contour.py) — asynchronous behavior, cache reuse, and exactness tests.
- [README.md](README.md) and [dev_plan/hierarchy_contour.md](dev_plan/hierarchy_contour.md) — document user-visible states and verified performance claims.

**Verification**

1. Run `python -m pytest -q`.
2. Test rapid hierarchy clicks, same-node toggling, collapse during computation, and stale worker completion.
3. Verify density work remains bounded and does not update discarded tree rows.
4. Add a Qt heartbeat test to detect GUI event-loop stalls.
5. Benchmark 10M-like designs before and after the changes.
6. Manually test expansion, contour switching, heat-map changes, pan/zoom, and warm-cache relaunch.

**Decisions**

- Exact contours remain the default source of truth.
- Row clicks continue to toggle contours.
- GUI responsiveness is prioritized over maximum worker concurrency.
- Approximate previews are optional, explicitly labeled, and never silently substituted.
- Existing vectorized rasterization, compact geometry storage, exact pre-merge, and lazy density should be measured on real data before further algorithm changes.
- Compare mode and unrelated metric work are out of scope.

Recommended initial targets are visible feedback under 100 ms, no sustained GUI stall over 100 ms during background work, and first useful density results within approximately 1 second when the hierarchy data is already available.
