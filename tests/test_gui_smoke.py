"""Headless (offscreen) smoke tests for the Qt frontend."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from vlsi_viewer import theme
from vlsi_viewer.model import match_paths, view_for_diff, view_for_single
from vlsi_viewer.ui_main import MainWindow
from vlsi_viewer.ui_search import SearchDialog
from vlsi_viewer.ui_tree import BAR_COLOR_ROLE, BAR_ROLE, HierarchyTree


def _tiny_physical(tmp_path, pins=None):
    import json
    from vlsi_viewer.physical import build_physical
    cell = tmp_path / "cell.json"
    cell.write_text(json.dumps({"C1": {"area": 4, "size_x": 2, "size_y": 2}}))
    top = tmp_path / "top.json"
    top.write_text(json.dumps({
        "top_name": "TOP",
        "boundary": [(0, 0), (20, 20)],
        "instances": {"c": {"cell_name": "C1", "location_x": 0, "location_y": 0,
                            "leakage_power": 1.0, "dynamic_power": 2.0}},
    }))
    return build_physical([str(top)], str(cell), grid_size=4.0, pins=pins)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_tree_constructs(app, design):
    view = view_for_single(design)
    tree = HierarchyTree()
    tree.set_view(view)

    assert tree.columnCount() == 12  # Hierarchy + 11 std metrics
    assert tree.topLevelItemCount() == 1

    top = tree.topLevelItem(0)
    assert top.data(0, Qt.UserRole) == "TOP"
    assert top.childCount() == 2   # root expanded one level

    kids = {top.child(i).data(0, Qt.UserRole): top.child(i) for i in range(top.childCount())}
    assert set(kids) == {"TOP/MACROA", "TOP/UNIT2"}
    # children are collapsed, showing only a placeholder (expand arrow)
    assert kids["TOP/MACROA"].childCount() == 1
    assert kids["TOP/MACROA"].child(0).data(0, Qt.UserRole) is None
    assert kids["TOP/UNIT2"].childCount() == 0


def test_include_macros_adds_columns(app, design):
    view = view_for_single(design, include_macros=True)
    tree = HierarchyTree()
    tree.set_view(view)
    assert tree.columnCount() == 14  # Hierarchy + 11 std + 2 macro


def test_threshold_filters_children(app, design):
    view = view_for_single(design)
    tree = HierarchyTree()
    tree.set_threshold(100)
    tree.set_view(view)
    assert tree.topLevelItemCount() == 1       # root always shown
    assert tree.topLevelItem(0).childCount() == 0  # all children < 100 hidden


def test_expand_to(app, design):
    tree = HierarchyTree()
    tree.set_view(view_for_single(design))
    tree.expand_to("TOP/MACROA/UNIT1")
    assert tree.currentItem().data(0, Qt.UserRole) == "TOP/MACROA/UNIT1"


def test_match_paths(design):
    view = view_for_single(design)
    assert match_paths(view.paths, "TOP/MACROA/UNIT1", "exact") == ["TOP/MACROA/UNIT1"]
    assert match_paths(view.paths, "*unit1*", "wildcard") == ["TOP/MACROA/UNIT1"]
    assert match_paths(view.paths, "MACROA/UNIT", "regex") == ["TOP/MACROA/UNIT1"]
    assert match_paths(view.paths, "*", "wildcard") == sorted(view.paths)


def test_search_dialog(app, design):
    view = view_for_single(design)
    dlg = SearchDialog(view, None, "*unit1*", "wildcard")
    table = dlg.tables["v1"]
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "TOP/MACROA/UNIT1"


def test_search_dialog_compare(app, design):
    v1 = view_for_single(design)
    v2 = view_for_single(design, include_macros=True)
    dlg = SearchDialog(v1, v2, "*unit1*", "wildcard")
    assert dlg.tables["v1"].rowCount() == 1
    assert dlg.tables["v2"].rowCount() == 1
    # v2 table has macro columns (11 std + 2 macro)
    assert dlg.tables["v2"].columnCount() == 1 + 13
    assert dlg.tables["v1"].columnCount() == 1 + 11


def test_jump_to_switches_compare_tab(app, design):
    w = MainWindow(design, design, threshold=0)
    assert w._compare.currentIndex() == 0  # V1 tab
    w._jump_to("TOP/MACROA/UNIT1", "v2")
    assert w._compare.currentIndex() == 1  # switched to V2
    assert w._compare.v2.currentItem().data(0, Qt.UserRole) == "TOP/MACROA/UNIT1"


def test_gradient_range_sync_between_tabs(app, design):
    from vlsi_viewer import schema
    try:
        w = MainWindow(design, design, threshold=0)
        schema.set_gradient_range("ulvt_ratio", 0.0, 1.0)
        w._compare.v1.gradient_range_changed.emit()  # simulate edit on V1
        # V2 tab's ULVT bar now reflects the widened range (raw value 7/11.5)
        top_v2 = w._compare.v2.topLevelItem(0)
        assert top_v2.data(3, BAR_ROLE) == pytest.approx(7 / 11.5)
    finally:
        schema.set_gradient_range("ulvt_ratio", 0.0, 0.35)


def test_layout_view_builds(app, tmp_path):
    from vlsi_viewer.genericView import GenericGraphicsView
    from vlsi_viewer.ui_layout import LayoutView
    pd_ = _tiny_physical(tmp_path)
    view = LayoutView(pd_)
    assert isinstance(view._view, GenericGraphicsView)
    assert len(view._view.scene().items()) >= 2  # pixmap + boundary outline
    assert len(view._boundary_items) == 1
    assert view._pix_item.pixmap() is not None and not view._pix_item.pixmap().isNull()


def test_pin_density_map_is_offered_only_where_pins_exist(app, tmp_path):
    """The fifth entry is appended - never inserted - and only for data that has pins."""
    from vlsi_viewer.ui_layout import HEAT_TYPES, LayoutView

    keys = [key for key, _label in HEAT_TYPES]
    plain = LayoutView(_tiny_physical(tmp_path))
    assert [key for key, _label in plain._kinds] == keys
    assert plain.type_combo.count() == len(keys)

    pinned = LayoutView(_tiny_physical(tmp_path, pins={"C1": [(1.0, 1.0)]}))
    assert [key for key, _label in pinned._kinds] == keys + ["pins"]
    assert pinned.type_combo.itemText(len(keys)) == "Pin density"
    # The count map must not put the source on the fixed [0, 1] ramp metal's metric uses:
    # that flag is what `physical.kinds()` would have flipped, for every map at once.
    assert pinned._fixed_ratio is False
    pinned.set_kind("pins")
    assert pinned._fixed_ratio is False
    assert pinned._kind == "pins"
    # selecting it renders: a count map autoscales to its own maximum
    assert not pinned._pix_item.pixmap().isNull()
    assert pinned._hi >= 1.0


def test_tree_click_without_physical_does_not_raise(app, design):
    """In default (non-physical) mode, clicking a tree node is a no-op."""
    w = MainWindow(design)
    assert w._layout is None
    w._on_node_clicked("TOP/MACROA/UNIT1")   # must not raise AttributeError


def _pump_events(app, ms=400):
    from PyQt5.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def _tiny_layout(tmp_path):
    import json as _json
    from vlsi_viewer.physical import build_physical
    from vlsi_viewer.ui_layout import LayoutView
    cell = tmp_path / "cell.json"
    cell.write_text(_json.dumps({"C1": {"area": 4, "size_x": 2, "size_y": 2}}))
    top = tmp_path / "top.json"
    top.write_text(_json.dumps({
        "top_name": "TOP",
        "boundary": [(0, 0), (20, 20)],
        "instances": {
            "a": {"cell_name": "C1", "location_x": 0, "location_y": 0},
            "b": {"cell_name": "C1", "location_x": 2, "location_y": 0},
        },
    }))
    return LayoutView(build_physical([str(top)], str(cell), grid_size=4.0))


def test_layout_contour_toggle(app, tmp_path):
    view = _tiny_layout(tmp_path)
    assert view._contour_path is None
    view.toggle_contour("TOP")           # show (async: selected immediately)
    assert view._contour_path == "TOP"
    assert view._contour_items == []     # not computed synchronously
    _pump_events(app)                     # let the background worker deliver
    assert len(view._contour_items) >= 1
    assert view._contour_items[0].zValue() == 20   # above boundary outlines
    view.toggle_contour("TOP")           # click again -> clears immediately
    assert view._contour_path is None
    assert view._contour_items == []


def test_contour_stale_token_ignored(app, tmp_path):
    """A stale background result must not overwrite a newer selection."""
    view = _tiny_layout(tmp_path)
    loop = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    view.toggle_contour("TOP")            # token 1
    view.toggle_contour("TOP/a")          # token 2, supersedes
    assert view._contour_path == "TOP/a"
    view._on_contour_ready("TOP", 1, [loop])     # stale -> ignored
    assert view._contour_items == []
    view._on_contour_ready("TOP/a", 2, [loop])   # current -> drawn
    assert len(view._contour_items) == 1


def test_layout_legend_overlay(app, tmp_path):
    from vlsi_viewer.ui_layout import LayoutView
    pd_ = _tiny_physical(tmp_path)
    view = LayoutView(pd_)
    # legend is a fixed child of the graphics view (not a scene item)
    assert view._legend is not None
    assert view._legend.parent() is view._view
    # set_range stores the range (drives the 0/25/50/75/100% tick values)
    view._legend.set_range(0.2, 0.8)
    assert view._legend._lo == 0.2
    assert view._legend._hi == 0.8


def test_layout_range_kept_across_map_switch(app, tmp_path):
    """A user-edited Min/Max survives switching map type away and back."""
    from vlsi_viewer.ui_layout import LayoutView
    view = LayoutView(_tiny_physical(tmp_path))
    view.min_spin.setValue(0.25)
    view.max_spin.setValue(0.75)
    assert (view._lo, view._hi) == (0.25, 0.75)

    view.type_combo.setCurrentIndex(1)           # density -> leakage (auto-ranges)
    assert view._kind == "leakage"
    view.type_combo.setCurrentIndex(0)           # back to density

    assert view._kind == "density"
    assert (view.min_spin.value(), view.max_spin.value()) == (0.25, 0.75)
    assert (view._lo, view._hi) == (0.25, 0.75)
    assert (view._legend._lo, view._legend._hi) == (0.25, 0.75)


def test_the_range_spin_boxes_are_visible(app, tmp_path):
    """The controls row ends in a stretch, so an `Ignored` width policy leaves 0 px for these.

    Measured: `Preferred` with `setMaximumWidth(96)` lays them out 96 px wide, `Ignored` lays
    them out at nothing - and the suite could not see it, because setting a value works fine at
    zero width. Only a shown window tells the two apart.
    """
    from vlsi_viewer.ui_layout import LayoutView

    view = LayoutView(_tiny_physical(tmp_path))
    view.resize(900, 500)
    view.show()
    app.processEvents()
    assert view.min_spin.width() > 0
    assert view.max_spin.width() > 0
    view.close()


def test_layout_first_visit_to_map_autotanges(app, tmp_path):
    """A map type never visited before still derives its range from the data."""
    from vlsi_viewer.ui_layout import LayoutView
    pd_ = _tiny_physical(tmp_path)
    view = LayoutView(pd_)
    view.type_combo.setCurrentIndex(1)           # leakage: not visited yet

    assert view._kind == "leakage"
    assert view._lo == 0.0
    assert view._hi == pytest.approx(float(pd_.heat("leakage").max()))


def test_mainwindow_physical(app, design, tmp_path):
    pd_ = _tiny_physical(tmp_path)
    w = MainWindow(design, physical=pd_)
    assert hasattr(w, "_layout")
    assert w.statusBar().currentMessage().startswith("Physical mode")
    # hierarchy tree is populated beside the layout
    assert w._tree.topLevelItemCount() == 1
    assert w._tree.topLevelItem(0).data(0, Qt.UserRole) == "TOP"
    # hover readout label is pinned in the status bar
    assert w._hover_label is not None


def test_the_last_column_is_fully_visible(app, design, tmp_path):
    """Density% is the last column in physical mode, and it must not be the one that pays.

    Qt's default for a tree view stretches the last section, and with that on Qt never shrinks it:
    the column stayed at the width it was created with while the other twelve shared the rest, so
    the header overflowed the pane by exactly that difference and the column's right edge - where
    the value's tail is, the bar cells being right-aligned - sat behind the scrollbar. The pane
    looks like it has room because the overflow went to the *other* stretch columns.
    """
    w = MainWindow(design, physical=_tiny_physical(tmp_path))
    try:
        w.resize(1920, 900)
        w.show()
        _pump_events(app)
        w.centralWidget().setSizes([1130, 790])      # the pane width the report came from
        _pump_events(app)

        tree, header = w._tree, w._tree.header()
        last = tree.columnCount() - 1
        assert tree.topLevelItem(0).text(last).endswith("%")     # the column under test is there
        assert tree.horizontalScrollBar().maximum() == 0
        assert header.sectionPosition(last) + header.sectionSize(last) <= tree.viewport().width()
    finally:
        w.close()


def test_layout_hover_reports_coords_and_grid(app, tmp_path):
    from PyQt5.QtCore import QPointF
    from vlsi_viewer.ui_layout import LayoutView

    pd_ = _tiny_physical(tmp_path)      # extent (0,0,20,20), grid 4 -> 5x5
    view = LayoutView(pd_)
    msgs = []
    view.hover_changed.connect(msgs.append)
    # scene point for physical (2, 2): y flipped -> scene (2, 20-2) = (2, 18)
    view._on_hover(QPointF(2.0, 18.0))
    assert msgs and "x=2.00" in msgs[-1]
    assert "y=2.00" in msgs[-1]
    assert "density[0,0] = 0.250" in msgs[-1]  # 2x2 cell fills 1/4 of the bin
    # out-of-die hover reports coordinates only
    view._on_hover(QPointF(50.0, 50.0))
    assert "x=50.00" in msgs[-1] and "density" not in msgs[-1]


def test_diff_view(app, design):
    view = view_for_diff(design, design)
    assert len(view.columns) == 22  # 11 metrics x {abs, rel}
    # Δrel columns carry a gradient; Δabs columns do not
    rel_col = view.columns[1]    # ΔArea% (index 1 = first rel after ΔArea at 0)
    assert rel_col.gradient == "lower_better"
    assert rel_col.key == "area_rel"
    # MB/D1D2 Δrel are higher-better
    mb_rel = view.columns[7]     # area,count,ulvt,mb,d1d2,bits,ckb,icg,pul,bi,bi
    assert mb_rel.label == "ΔMB%"
    assert mb_rel.gradient == "higher_better"
    tree = HierarchyTree()
    tree.set_view(view)
    # diff against itself -> area delta is 0
    top = tree.topLevelItem(0)
    assert top.text(1) == "+0.00"  # ΔArea formatted signed


def test_mainwindow_preloaded(app, design):
    w = MainWindow(design)
    assert w._stack.currentWidget() is w._tree
    assert w._tree.topLevelItemCount() == 1
    assert w._tree.topLevelItem(0).data(0, Qt.UserRole) == "TOP"
    assert w.statusBar().currentMessage().startswith("1 block(s)")


def test_mainwindow_compare(app, design):
    w = MainWindow(design, design, threshold=0)
    assert w._stack.currentWidget() is w._compare
    assert w._compare.v1.topLevelItemCount() == 1
    assert w._compare.diff.topLevelItemCount() == 1
    assert w._compare.diff.columnCount() == 23  # Hierarchy + 22 diff columns


def test_deep_hierarchy_expand_arrow(app, tmp_path):
    import json
    from vlsi_viewer.metrics import build_design

    inst = {"top_name": "TOP",
            "instances": {"A/B/C/l1": {"cell_name": "C1"},
                          "A/B/C/l2": {"cell_name": "C1"}}}
    cell = {"C1": {"area": 1.0}}
    (tmp_path / "instance_info.json").write_text(json.dumps(inst))
    (tmp_path / "cell_info.json").write_text(json.dumps(cell))
    design = build_design([str(tmp_path / "instance_info.json")], str(tmp_path / "cell_info.json"))

    tree = HierarchyTree()
    tree.set_view(view_for_single(design))

    top = tree.topLevelItem(0)   # TOP (expanded)
    a = top.child(0)             # TOP/A (level 2, collapsed -> placeholder arrow)
    assert a.childCount() == 1
    assert a.child(0).data(0, Qt.UserRole) is None

    tree.expand_to("TOP/A/B/C")
    assert tree.currentItem().data(0, Qt.UserRole) == "TOP/A/B/C"


def test_toggle_macros_preserves_expansion(app, design):
    tree = HierarchyTree()
    tree.set_view(view_for_single(design))
    top = tree.topLevelItem(0)
    # collapse both first-level children -> only TOP remains expanded
    for i in range(top.childCount()):
        top.child(i).setExpanded(False)
    assert tree._expanded_paths() == ["TOP"]

    tree.set_view(view_for_single(design, include_macros=True))
    assert tree._expanded_paths() == ["TOP"]       # expansion preserved
    assert tree.columnCount() == 14                # +2 macro columns
    assert tree.topLevelItem(0).childCount() == 2


def test_bar_ratios_stored(app, design):
    tree = HierarchyTree()
    tree.set_view(view_for_single(design))
    top = tree.topLevelItem(0)
    assert top.data(0, BAR_ROLE) is None                # hierarchy column: no bar
    assert top.data(2, BAR_ROLE) == pytest.approx(1.0)  # Count = 5/5
    assert top.data(1, BAR_ROLE) == pytest.approx(1.0)  # Area = 11.5/11.5
    assert top.data(3, BAR_ROLE) == pytest.approx(1.0)  # ULVT% 0.6087 clamps to range [0, 0.35]
    macroa = top.child(0)  # TOP/MACROA
    assert macroa.data(2, BAR_ROLE) == pytest.approx(0.8)   # Count = 4/5


def test_quality_color():
    red = theme.quality_color(0.0)
    green = theme.quality_color(1.0)
    assert red.red() > red.green()        # red channel dominates at "bad"
    assert green.green() > green.red()    # green channel dominates at "good"


def test_gradient_bar_color(app, design):
    tree = HierarchyTree()
    tree.set_view(view_for_single(design))
    top = tree.topLevelItem(0)
    count_color = top.data(2, BAR_COLOR_ROLE)   # Count -> fixed teal
    ulvt_color = top.data(3, BAR_COLOR_ROLE)    # ULVT% -> quality gradient
    assert count_color == theme.BAR_COLOR
    assert ulvt_color is not None and ulvt_color != theme.BAR_COLOR


def test_tree_opens_sorted_by_area_desc(app, tmp_path):
    """The first population sorts by Area descending, not by hierarchy path."""
    import json
    from vlsi_viewer.metrics import build_design

    inst = {"top_name": "TOP",
            "instances": {"A_small/x": {"cell_name": "S1"},
                          "Z_big/y": {"cell_name": "B1"}}}
    cell = {"S1": {"area": 1.0}, "B1": {"area": 4.0}}
    (tmp_path / "instance_info.json").write_text(json.dumps(inst))
    (tmp_path / "cell_info.json").write_text(json.dumps(cell))
    design = build_design([str(tmp_path / "instance_info.json")],
                          str(tmp_path / "cell_info.json"))

    tree = HierarchyTree()
    tree.set_view(view_for_single(design))

    top = tree.topLevelItem(0)
    # lexicographic order would put A_small first; the area sort puts the bigger one first
    assert [top.child(i).data(0, Qt.UserRole) for i in range(top.childCount())] == [
        "TOP/Z_big", "TOP/A_small"]
    assert tree._sort_column == 1 and tree._sort_order == Qt.DescendingOrder
    assert tree.header().sortIndicatorSection() == 1
    assert tree.header().sortIndicatorOrder() == Qt.DescendingOrder


def test_sort_records_and_signals(app, design):
    tree = HierarchyTree()
    tree.set_view(view_for_single(design))
    msgs = []
    tree.sort_changed.connect(msgs.append)
    tree._on_header_clicked(2)  # Count column
    assert tree._sort_active
    assert tree._sort_column == 2
    assert msgs and "Count" in msgs[-1]
    tree.expand_to("TOP/MACROA/UNIT1")  # auto-sort on expand does not crash


def test_copy_to_clipboard(app, design):
    tree = HierarchyTree()
    tree.set_view(view_for_single(design))
    tree._copy("TOP/MACROA")
    assert QApplication.clipboard().text() == "TOP/MACROA"


def test_gradient_fill_scaled_to_range(app, design):
    from vlsi_viewer import schema
    try:
        tree = HierarchyTree()
        tree.set_view(view_for_single(design))
        top = tree.topLevelItem(0)
        # TOP ULVT = 7/11.5 ≈ 0.6087; default range [0, 0.35] -> clamped to 1.0
        assert top.data(3, BAR_ROLE) == pytest.approx(1.0)
        schema.set_gradient_range("ulvt_ratio", 0.0, 1.0)
        tree.rebuild()
        top = tree.topLevelItem(0)
        assert top.data(3, BAR_ROLE) == pytest.approx(7 / 11.5)
    finally:
        schema.set_gradient_range("ulvt_ratio", 0.0, 0.35)
