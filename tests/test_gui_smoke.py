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
    dlg = SearchDialog(view, "*unit1*", "wildcard")
    assert dlg.table.rowCount() == 1
    assert dlg.table.item(0, 0).text() == "TOP/MACROA/UNIT1"


def test_diff_view(app, design):
    view = view_for_diff(design, design)
    assert len(view.columns) == 22  # 11 metrics x {abs, rel}
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
