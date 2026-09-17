"""Metal mode in the window: no hierarchy, a layer panel, and a readout that reconciles.

`QT_QPA_PLATFORM` is set before any PyQt5 import, as the other GUI tests do. Nothing here
calls `.show()`; the widgets are built and inspected directly.

The point of these tests is not that the widgets exist but that they agree with each other:
the checkbox selection, the map on screen, and the numbers in the readout are three views of
one thing, and a GUI is exactly where three views drift apart.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from PyQt5.QtWidgets import QApplication, QToolBar

SAMPLE = "sample_data/metal"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def metal():
    """One shared grid build - it is the slow part and nothing here mutates it."""
    import contextlib
    import io

    from vlsi_viewer.metal import build_metal

    with contextlib.redirect_stdout(io.StringIO()):
        return build_metal([f"{SAMPLE}/top.def", f"{SAMPLE}/sub.def"],
                           [f"{SAMPLE}/cells.lef"], [f"{SAMPLE}/tech.lef"], grid_size=10.0)


@pytest.fixture(scope="module")
def trimmed():
    """The same sample measured over M4..M9: a range in the middle, so both ends are cut."""
    import contextlib
    import io

    from vlsi_viewer.metal import build_metal

    with contextlib.redirect_stdout(io.StringIO()):
        return build_metal([f"{SAMPLE}/top.def", f"{SAMPLE}/sub.def"],
                           [f"{SAMPLE}/cells.lef"], [f"{SAMPLE}/tech.lef"], grid_size=10.0,
                           min_layer=4, max_layer=9)


@pytest.fixture
def window(app, metal):
    from vlsi_viewer.ui_main import MainWindow

    metal.set_scope("all")
    win = MainWindow(metal=metal)
    yield win
    win.close()


# -- the window shape ---------------------------------------------------------------

def test_metal_mode_has_no_hierarchy_toolbar(window):
    """The search box, match mode, Find, min-instances and macros toggle are all absent.

    A search box that filters a tree nobody can see is worse than no search box. Metal mode
    has a toolbar of its own, but it holds the map's value range and nothing else.
    """
    from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QLineEdit

    for attribute in ("search_edit", "mode_combo", "min_spin", "macro_check"):
        assert not hasattr(window, attribute), attribute
    toolbars = window.findChildren(QToolBar)
    assert len(toolbars) == 1
    assert toolbars[0].objectName() == "metal_range_toolbar"
    # A spin box is built around its own QLineEdit, so the search box has to be looked for by
    # parent: a toolbar widget is parented to the toolbar, a spin box's editor to the spin box.
    assert [w for w in toolbars[0].findChildren(QLineEdit) if w.parent() is toolbars[0]] == []
    assert toolbars[0].findChildren(QComboBox) == []      # no match mode
    assert len(toolbars[0].findChildren(QDoubleSpinBox)) == 2   # the ramp's Min and Max


def test_metal_mode_shows_no_tree(window):
    from PyQt5.QtWidgets import QSplitter

    central = window.centralWidget()
    assert isinstance(central, QSplitter)
    widgets = [central.widget(i) for i in range(central.count())]
    assert window._tree not in widgets
    assert widgets == [window._detail, window._layout, window._panel]


def test_the_cell_readout_is_the_left_pane_and_the_selection_the_right(window):
    """The two tables were in one column and fought over the same height.

    Splitting them puts the map between them, so both are fully visible at once - which is
    the whole reason the readout moved.
    """
    central = window.centralWidget()
    assert central.widget(0) is window._detail
    assert central.widget(1) is window._layout
    assert central.widget(2) is window._panel


def test_the_map_pane_takes_the_slack(app, window):
    """Stretch factors are not readable back, so this checks what they are for.

    Every spare pixel goes to the map, which is what stops the blank strip this window used to
    have beside the sidebar. The panes' `maximumWidth` is deliberately not asserted: Qt lets a
    widget's *minimum* win over its maximum, and under a very wide font the layer buttons alone
    exceed the panel's ceiling - a font artifact, not a layout fault.
    """
    window.resize(1400, 800)
    window.show()
    app.processEvents()
    splitter = window.centralWidget()
    detail, layout, panel = splitter.sizes()
    assert layout > detail and layout > panel
    # sizes() covers the panes only: the handles between them are not in it.
    handles = (splitter.count() - 1) * splitter.handleWidth()
    assert detail + layout + panel == splitter.width() - handles

    # Narrower: the side panes hold their width and the map gives up its own first. Sized from
    # hints instead, the layer table would keep 519 px and leave the map a sliver.
    window.resize(1000, 800)
    app.processEvents()
    detail, layout, panel = splitter.sizes()
    assert layout > panel and layout > detail
    window.close()


def test_no_density_column_is_built(window):
    """`Density%` is an instance-area metric and has no meaning for a routing map."""
    assert window._density is None


def test_the_panel_lists_layers_bottom_to_top(window, metal):
    names = [layer.name for layer in metal.layers]
    listed = list(window._panel._boxes)
    assert listed == names
    assert listed[0] == "M1"          # the bottom layer is listed first


def test_status_bar_names_the_mode_and_grid(window, metal):
    message = window.statusBar().currentMessage()
    assert "Metal mode" in message
    assert f"{metal.rows}×{metal.cols}" in message


def test_status_bar_reports_the_die_size(window, metal):
    """Nothing else on screen says the grid is 620 um across, and density has a scale."""
    x0, y0, x1, y1 = metal.extent
    message = window.statusBar().currentMessage()
    assert f"die {x1 - x0:g}×{y1 - y0:g} um" in message


def test_a_trimmed_window_shows_only_the_range(app, trimmed):
    """Rows, map list and status bar all come from the measured stack, and say which it is.

    `6 layers` would read as a short stack rather than a range somebody asked for, so the
    status bar names both ends - the one place on screen where the numbers can be checked
    against the flags.
    """
    from vlsi_viewer.ui_main import MainWindow

    win = MainWindow(metal=trimmed)
    try:
        listed = list(win._panel._boxes)
        assert listed == ["M4", "M5", "M6", "M7", "M8", "M9"]
        assert [layer.name for layer in trimmed.layers] == listed
        assert win.statusBar().currentMessage().count("layers M4..M9 (6 of 12)") == 1
    finally:
        win.close()


def test_the_capacity_note_counts_the_fallback_from_the_whole_stack(app, trimmed):
    """The sample's macro that declares no OBS blocks the stack's bottom four, M1..M4 - and
    of those only M4 is being measured here, so the note has to say M4 rather than "4 layers".
    """
    from vlsi_viewer.ui_main import MainWindow

    assert trimmed.blockage["fallback_layer_names"] == ["M4"]
    win = MainWindow(metal=trimmed)
    try:
        win._detail.on_cell(0, 0)
        note = win._detail.detail_note.text()
        assert "which is M4 here" in note
        assert "bottom 4 layer(s)" not in note
    finally:
        win.close()


def test_both_side_panes_are_resizable_not_fixed(window):
    for pane in (window._panel, window._detail):
        assert pane.minimumWidth() < pane.maximumWidth()


def test_the_range_widgets_are_in_the_toolbar_not_the_panel(window):
    """The toolbar is the only place a 1e12-range spin box can be without costing pane width."""
    from PyQt5.QtWidgets import QDoubleSpinBox, QLabel, QPushButton

    toolbar = window.findChildren(QToolBar)[0]
    assert [w for w in toolbar.findChildren(QDoubleSpinBox)] == \
        [window._layout.min_spin, window._layout.max_spin]
    assert window._panel.auto_btn in toolbar.findChildren(QPushButton)
    assert window._layout.fit_btn in toolbar.findChildren(QPushButton)
    assert window._panel.peak_label in toolbar.findChildren(QLabel)
    # ... and the panel is free of them, which is what it was fighting for room with
    assert window._panel.findChildren(QDoubleSpinBox) == []


def test_the_spin_boxes_are_actually_visible(app, window):
    """The regression the old suite could not see: setting a value works at zero width.

    `QSizePolicy.Ignored` makes `QWidgetItem::sizeHint()` return 0, and the row ends in
    `addStretch(1)`, so both boxes were laid out 0 px wide and rendered as nothing. Only a
    shown window can tell the difference.
    """
    window.resize(1400, 800)
    window.show()
    app.processEvents()
    for box in (window._layout.min_spin, window._layout.max_spin):
        assert box.width() > 0
    window._layout.min_spin.setValue(0.25)
    assert window._layout._lo == 0.25          # still wired up, not merely present
    window.close()


def test_the_peak_readout_is_not_clipped(app, window):
    """The last item in a QToolBar absorbs the leftover width, so an unconstrained label sits
    in a few hundred pixels of blank - and a narrower toolbar would clip it instead."""
    window.show()
    app.processEvents()
    label = window._panel.peak_label
    assert label.width() >= label.sizeHint().width()
    window.close()


def test_the_controls_row_is_not_laid_out_twice(window):
    """The view builds the row for physical mode; metal mode must not also show it."""
    from PyQt5.QtWidgets import QDoubleSpinBox

    assert window._layout.findChildren(QDoubleSpinBox) == []


def test_a_long_readout_line_does_not_widen_the_pane(window, metal):
    """The readout's length changes with every hover, and the pane's minimum with it.

    A QLabel's minimum width is the width of the string it currently holds, so a live readout
    makes the divider refuse to be dragged narrower over a long line.
    """
    from PyQt5.QtWidgets import QSizePolicy

    before = window._detail.minimumSizeHint().width()
    window._detail.on_cell(*_busiest(window._panel, metal))
    assert window._detail.minimumSizeHint().width() == before
    assert window._detail.detail_head.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored


def test_the_readout_table_scrolls_rather_than_pushing_the_totals_out(window):
    """A twenty-layer stack must not be able to hide the arithmetic under it."""
    assert window._detail.detail_area.maximumHeight() < 16777215


def _layer_row(panel, row):
    """The four cells of one layer-table row; row 0 is the heading."""
    grid = panel.layers_area.widget().layout()
    return [grid.itemAtPosition(row, column).widget() for column in range(4)]


def test_each_layer_row_carries_its_own_rules(window, metal):
    """W/S/P is the tech LEF's own numbers - the ones the capacity was computed from.

    Capacity is `routable area x (W + S) / P`, so the three rules belong beside the
    utilisation, and the factor itself is reported by asking the metric for it. Re-deriving
    the formula in a widget is exactly how a tooltip drifts from the map.
    """
    assert [cell.text() for cell in _layer_row(window._panel, 0)] == \
        ["layer", "W/S/P", "dir", "U"]
    for row, layer in enumerate(metal.layers, start=1):
        check, rules, direction, _value = _layer_row(window._panel, row)
        assert check.text() == layer.name
        # The fields are space-padded for alignment, so compare them stripped.
        assert "/".join(part.strip() for part in rules.text().split("/")) == \
            f"{layer.width:g}/{layer.spacing:g}/{layer.pitch:g}"
        assert direction.text() == ("H" if layer.is_horizontal else "V")
        assert f"f = (W + S) / P = {metal.pitch_factor(layer):.3f}" in rules.toolTip()


def test_the_rule_fields_line_up_down_the_column(window, metal):
    """`0.07/0.07/0.14` against `0.8/0.8/1.6` will not line up unless each field is padded.

    Unpadded, the slashes wander from row to row and the column stops reading as a table.
    """
    rules = [_layer_row(window._panel, row)[1].text()
             for row in range(1, len(metal.layers) + 1)]
    assert len(set(map(len, rules))) == 1, rules
    assert [text.count("/") for text in rules] == [2] * len(rules)


def test_the_readout_table_is_as_tall_as_the_rows_it_shows(app, window, metal):
    """Reported from the running window: three rows visible, half the pane empty below.

    A QScrollArea's size hint is the size its widget had when the policy was last consulted,
    not what the widget now needs, so asking it to size itself gives a table a fraction of the
    height it requires. The readout states its height instead.
    """
    from vlsi_viewer.ui_metal import DETAIL_MAX_HEIGHT

    # Read the height it asks for, not the realised geometry: the latter needs a layout pass.
    area = window._detail.detail_area
    window._panel._pick(None)
    window._panel._boxes["M1"][0].setChecked(True)
    window._detail.on_cell(0, 0)
    one_layer = area.maximumHeight()

    window._panel._pick(lambda layer: layer.is_horizontal)
    window._detail.on_cell(0, 0)
    many = area.maximumHeight()
    assert many > one_layer
    assert many >= min(window._detail.detail_grid.sizeHint().height(), DETAIL_MAX_HEIGHT)

    window._detail.on_cell(-1, -1)
    assert area.maximumHeight() < one_layer             # nothing to show, so no table

    # And the pane really gives it that height, which is what stops the rows being cut off.
    window._panel._pick(lambda layer: layer.is_horizontal)
    window._detail.on_cell(0, 0)
    window.show()
    app.processEvents()
    assert area.height() >= min(window._detail.detail_grid.sizeHint().height(),
                                DETAIL_MAX_HEIGHT)
    window.close()


def test_a_three_decimal_rule_is_not_rounded_away():
    """0.065 um is a real Nangate45 width; three significant figures would print `0.06`."""
    from vlsi_viewer.metal import MetalData
    from vlsi_viewer.parsers.routing import RouteLayer
    from vlsi_viewer.ui_layout import LayoutView
    from vlsi_viewer.ui_metal import MetalPanel

    layer = RouteLayer("M1", 0, "HORIZONTAL", 0.13, 0.065, 0.065)
    data = MetalData("t", [], 10.0, (0.0, 0.0, 10.0, 10.0), 1, 1, [layer],
                     np.full((1, 1), 100.0), {}, 4, {}, [])
    panel = MetalPanel(data, LayoutView(data, external_controls=True))
    rules = _layer_row(panel, 1)[1].text()
    assert [part.strip() for part in rules.split("/")] == ["0.065", "0.065", "0.13"]


# -- selection drives the map -------------------------------------------------------

def test_unticking_a_layer_changes_the_map(window, metal):
    before = window._layout._physical.heat(window._panel.current_kind()).copy()
    window._panel._boxes["M2"][0].setChecked(False)
    after = window._layout._physical.heat(window._panel.current_kind())
    assert window._panel.current_kind() != "G:M1,M10,M11,M12,M2,M3,M4,M5,M6,M7,M8,M9"
    assert not np.allclose(before, after)


def test_all_horizontal_selects_exactly_the_horizontal_layers(window, metal):
    window._panel._pick(lambda layer: layer.is_horizontal)
    selected = [layer for layer in metal.layers
                if window._panel._boxes[layer.name][0].isChecked()]
    assert selected and all(layer.is_horizontal for layer in selected)
    assert len(selected) == len(metal.horizontal)


def test_all_vertical_selects_exactly_the_vertical_layers(window, metal):
    window._panel._pick(lambda layer: not layer.is_horizontal)
    selected = [layer for layer in metal.layers
                if window._panel._boxes[layer.name][0].isChecked()]
    assert selected and not any(layer.is_horizontal for layer in selected)


def test_none_leaves_nothing_selected_and_an_empty_map(window):
    window._panel._pick(None)
    assert window._panel.current_kind() == "G:"
    assert window._layout._physical.heat("G:").max() == 0.0


def test_ticking_one_layer_selects_that_layer(window):
    window._panel._pick(None)
    window._panel._boxes["M3"][0].setChecked(True)
    assert window._panel.current_kind() == "L:M3"


def test_unusable_layers_are_disabled_with_a_reason():
    """A layer with no width rule is shown disabled, not hidden, so the gap is explained."""
    from vlsi_viewer.metal import MetalData
    from vlsi_viewer.parsers.routing import RouteLayer, TechRouting
    from vlsi_viewer.ui_metal import MetalPanel
    from vlsi_viewer.ui_layout import LayoutView

    layers = [RouteLayer("M1", 0, "HORIZONTAL", 0.2, 0.1, 0.1),
              RouteLayer("GHOST", 1, "VERTICAL", 0.2, 0.0, 0.0)]
    data = MetalData("t", [], 10.0, (0.0, 0.0, 10.0, 10.0), 1, 1, layers,
                     np.full((1, 1), 100.0), {}, 4, {}, [])
    view = LayoutView(data, external_controls=True)
    panel = MetalPanel(data, view)
    check, _value = panel._boxes["GHOST"]
    assert not check.isEnabled() and not check.isChecked()
    assert "width" in check.toolTip()


# -- scope --------------------------------------------------------------------------

def test_scope_combo_changes_the_numbers(window, metal):
    window._panel._pick(lambda layer: layer.is_horizontal)
    window._panel.scope_combo.setCurrentIndex(1)          # Signal only
    assert metal.scope == "signal"
    signal = float(window._layout._physical.heat(window._panel.current_kind()).max())
    window._panel.scope_combo.setCurrentIndex(2)          # Power only
    assert metal.scope == "power"
    power = float(window._layout._physical.heat(window._panel.current_kind()).max())
    window._panel.scope_combo.setCurrentIndex(0)          # Both
    both = float(window._layout._physical.heat(window._panel.current_kind()).max())
    assert both >= max(signal, power)


# -- the readout --------------------------------------------------------------------

def _busiest(panel, data):
    """The grid cell with the most wire, so a readout test is not run on an empty one."""
    heat = data.heat(panel.current_kind())
    iy, ix = np.unravel_index(int(np.argmax(heat)), heat.shape)
    return int(ix), int(iy)


def _shown(panel):
    """The detail rows as `(name, numbers, util)` strings, header excluded.

    Empty rows are skipped: a QGridLayout never lowers its row count, so a readout that has
    just gone from six layers to five still reports the sixth row, with nothing in it.
    """
    rows = []
    for row in range(1, panel.detail_grid.rowCount()):
        items = [panel.detail_grid.itemAtPosition(row, column)
                 for column in range(panel.detail_grid.columnCount())]
        if any(item is None for item in items):
            continue
        rows.append([item.widget().text() for item in items])
    return rows

def test_cell_detail_reconciles_with_the_pixel(window, metal):
    """The readout exists so the colour can be checked; it must equal what was drawn."""
    window._panel._pick(lambda layer: layer.is_horizontal)
    kind = window._panel.current_kind()
    window._detail.on_cell(12, 9)
    shown = window._layout._physical.heat(kind)[9, 12]
    assert f"{shown:.4f}" in window._detail.detail_sum.text()


def test_cell_detail_lists_every_selected_layer(window):
    window._panel._pick(lambda layer: layer.is_horizontal)
    window._detail.on_cell(12, 9)
    layers = window._layout._physical.layers_of(window._panel.current_kind())
    assert window._detail.detail_grid.count() == 3 * (len(layers) + 1)   # + the heading row
    assert [row[0].rstrip(" *") for row in _shown(window._detail)] == \
        [layer.name for layer in layers]


def test_cell_detail_names_its_columns_once(window):
    """`D/C` in the heading, not `D` and `C` on all twelve rows; the panel is the scarce one."""
    window._detail.on_cell(12, 9)
    heading = [window._detail.detail_grid.itemAtPosition(0, column).widget().text()
               for column in range(3)]
    assert heading == ["layer", "D/C", "U"]
    assert all("D " not in numbers and "C " not in numbers
               for _name, numbers, _util in _shown(window._detail))


def test_the_bottleneck_layer_is_picked_out(window, metal):
    """Which layer is hot is the readout's whole point, and it is not the user's job to scan.

    Bold is the signal; the trailing `*` repeats it, so the reading does not depend on
    noticing a font weight.
    """
    window._panel._pick(lambda layer: layer.is_horizontal)
    ix, iy = _busiest(window._panel, metal)
    window._detail.on_cell(ix, iy)
    worst = max(metal.cell_detail(ix, iy, window._panel.current_kind())["layers"],
                key=lambda entry: entry["util"])
    rows = _shown(window._detail)
    assert worst["util"] > 0
    for name, _numbers, _util in rows:
        assert ("*" in name) == (name.rstrip(" *") == worst["name"])
    starred = [row for row in rows if "*" in row[0]][0]
    for index in (0, 1, 2):
        assert "bold" in window._detail.detail_grid.itemAtPosition(
            rows.index(starred) + 1, index).widget().styleSheet()


def test_the_readout_reports_the_direction_maxima(window, metal):
    """"Can I still escape?" is the mode's question, and it is a per-direction number.

    A cell whose horizontal layers are full and whose vertical ones are empty is still
    routable, so the two directions are reported apart rather than as one figure.
    """
    window._panel._pick(lambda layer: layer.is_horizontal)
    ix, iy = _busiest(window._panel, metal)
    window._detail.on_cell(ix, iy)
    entries = metal.cell_detail(ix, iy, window._panel.current_kind())["layers"]
    horizontal = max(entry["util"] for entry in entries if entry["direction"] == "H")
    vertical = max((entry["util"] for entry in entries if entry["direction"] == "V"),
                   default=0.0)
    text = window._detail.detail_split.text()
    assert f"H max {horizontal:.3f}" in text
    assert f"V max {vertical:.3f}" in text
    assert "escapable" in text                       # V is empty here, so escape is up


def test_the_group_total_is_the_capacity_weighted_mean(window, metal):
    """Summing the layers would double the number; the answer is sum(D)/sum(C)."""
    window._panel._pick(lambda layer: layer.is_horizontal)
    ix, iy = _busiest(window._panel, metal)
    window._detail.on_cell(ix, iy)
    from vlsi_viewer.ui_metal import _fmt

    detail = metal.cell_detail(ix, iy, window._panel.current_kind())
    text = window._detail.detail_sum.text()
    assert f"{detail['util']:.4f}" in text
    assert f"{_fmt(detail['consumed'])}/{_fmt(detail['capacity'])}" in text


def test_cell_detail_reports_the_capacity_policy(window, metal):
    """Which mechanism took capacity away, because the two are not equally trustworthy.

    The sample has one macro that declares OBS and one that does not, so the note has to name
    both: a reader comparing two cells needs to know whether they are looking at a macro's own
    obstruction geometry or at a layer count guessed for it.
    """
    window._detail.on_cell(12, 9)
    note = window._detail.detail_note.text()
    assert "OBS" in note
    assert "declare none" in note and str(metal.macro_block_layers) in note
    assert metal.blockage["obs_cells"] == 1 and metal.blockage["fallback_cells"] == 1


def test_the_note_says_when_nothing_is_blocked(tmp_path):
    """A design whose macros all declare OBS says so; one with no macros says that instead."""
    from PyQt5.QtWidgets import QApplication

    from vlsi_viewer.metal import MetalData
    from vlsi_viewer.ui_layout import LayoutView
    from vlsi_viewer.ui_metal import CellDetailPanel

    QApplication.instance() or QApplication([])

    class _Data(MetalData):
        def __init__(self, blockage, depth=4):
            super().__init__("t", [], 10.0, (0.0, 0.0, 10.0, 10.0), 1, 1, [], np.full((1, 1), 1.0),
                             {}, depth, {}, [], blockage)

    panel = CellDetailPanel(_Data({"obs_cells": 2, "fallback_cells": 0}), lambda: "L:")
    assert "OBS" in panel.detail_note.text()
    assert "no macro blocks" in CellDetailPanel(_Data({}), lambda: "L:").detail_note.text()
    # A macro that declares nothing while the flag is off blocks nothing either - the note
    # used to promise "the bottom 0 layer(s)".
    silenced = _Data({"obs_cells": 0, "fallback_cells": 1,
                      "fallback_layer_names": []}, depth=0)
    assert "no macro blocks" in CellDetailPanel(silenced, lambda: "L:").detail_note.text()


def test_leaving_the_grid_clears_the_readout(window):
    window._detail.on_cell(12, 9)
    window._detail.on_cell(-1, -1)
    assert "hover" in window._detail.detail_head.text()
    assert window._detail.detail_grid.count() == 0


def test_hover_signal_drives_the_readout(window, metal):
    """The readout is fed by the view's signal, not by a private path of its own."""
    window._layout.cell_hovered.emit(5, 5)
    assert "cell (5,5)" in window._detail.detail_head.text()


def test_the_map_drawn_at_startup_is_the_map_the_panel_selects(window, metal):
    """Reported from the running window: the first map was nearly empty, and only became the
    real one after the *scope* was changed.

    The view defaults to its own first kind - the bottom layer alone, which carries almost
    nothing - while the panel's tick boxes say every layer. Nothing pushed the selection into
    the view, so the two disagreed until some other control nudged it. The hover readout gives
    it away: it names the kind it is reading.
    """
    assert window._panel.current_kind() == metal.group_kind(
        [layer.name for layer in metal.layers])
    assert window._layout._kind == window._panel.current_kind()
    assert window._layout._physical.heat(window._layout._kind).max() == \
        pytest.approx(metal.max_util(window._panel.current_kind()))
    # ... and the peak in the toolbar describes the same map
    assert f"peak {metal.max_util(window._panel.current_kind()):.3f}" in \
        window._panel.peak_label.text()


def test_the_readout_is_correct_the_moment_it_is_built(window, metal):
    """The panel emits `selection_changed` during its own construction, before the window has
    connected anything to it - so the readout is right at start-up only because it refreshes
    itself once. Remove that and the two panes disagree until the first hover.
    """
    assert window._detail.detail_head.text() == f"{len(metal.layers)} layer(s) selected"


def test_the_selection_signal_fires_exactly_once_per_change(window):
    """Two connections, or two emissions, would double the readout's work and hide a wiring
    mistake rather than showing it. `_on_scope` used to repeat `_apply_kind`'s body instead of
    calling it, which is exactly how a second emission path appears without looking wrong.
    """
    seen = []
    window._panel.selection_changed.connect(lambda: seen.append(1))
    window._panel._pick(lambda layer: layer.is_horizontal)
    assert len(seen) == 1
    seen.clear()
    window._panel.scope_combo.setCurrentIndex(1)          # Signal only
    assert len(seen) == 1


def test_the_readout_works_standalone_without_a_window():
    """Its contract is `(data, kind_of)`: it asks which map to describe rather than caching one.

    Built the way a future view would embed it, with a `kind_of` that changes after
    construction - the readout has to follow the map that is on screen.
    """
    from vlsi_viewer.metal import MetalData
    from vlsi_viewer.parsers.routing import RouteLayer
    from vlsi_viewer.ui_metal import CellDetailPanel

    layers = [RouteLayer("M1", 0, "HORIZONTAL", 0.2, 0.1, 0.1),
              RouteLayer("M2", 1, "VERTICAL", 0.2, 0.1, 0.1)]
    data = MetalData("t", [], 10.0, (0.0, 0.0, 10.0, 10.0), 1, 1, layers,
                     np.full((1, 1), 100.0), {}, 4, {}, [])
    current = {"kind": "L:M1"}
    panel = CellDetailPanel(data, lambda: current["kind"])
    panel.on_cell(0, 0)
    assert [row[0] for row in _shown(panel)] == ["M1"]

    current["kind"] = data.group_kind(["M1", "M2"])
    panel.refresh()
    assert [row[0].rstrip(" *") for row in _shown(panel)] == ["M1", "M2"]


def test_changing_the_selection_re_renders_a_stationary_cursor(window, metal):
    """The readout must describe the map that is on screen, cursor or no cursor.

    The two are separate panes now, so this no longer happens by accident of shared state:
    without the panel's `selection_changed` the readout would keep showing the old kind's
    numbers until the mouse happened to move - the numbers and the picture disagreeing is the
    one thing this readout exists to prevent.
    """
    window._panel._pick(lambda layer: layer.is_horizontal)
    ix, iy = _busiest(window._panel, metal)
    window._detail.on_cell(ix, iy)
    assert len(_shown(window._detail)) == \
        len(metal.layers_of(window._panel.current_kind()))

    window._panel._boxes["M1"][0].setChecked(False)          # no second on_cell call

    assert window._detail.detail_head.text().startswith(f"cell ({ix},{iy})")
    names = [row[0].rstrip(" *") for row in _shown(window._detail)]
    assert "M1" not in names
    assert names == [layer.name for layer
                     in metal.layers_of(window._panel.current_kind())]


# -- the range is calibrated --------------------------------------------------------

def test_the_ramp_is_fixed_between_zero_and_one(window):
    """1.0 means every track consumed, so autoscaling to the data would lose the meaning."""
    assert (window._layout._lo, window._layout._hi) == (0.0, 1.0)
    window._panel._pick(lambda layer: layer.is_horizontal)
    assert (window._layout._lo, window._layout._hi) == (0.0, 1.0)


def test_the_legend_follows_the_fixed_range(window):
    assert window._layout._legend is not None


def test_auto_fits_the_ramp_to_the_map_without_moving_the_peak(window, metal):
    """The sample peaks at ~0.53 and sits near 0.03, so [0, 1] is a dark rectangle.

    Auto stretches the colours to the map's top half-percent; the peak is still reported, so
    the absolute scale is never in doubt while it is stretched.
    """
    window._panel._pick(lambda layer: layer.is_horizontal)
    kind = window._panel.current_kind()
    occupied = metal.heat(kind)[metal.heat(kind) > 0]
    window._panel.auto_btn.click()

    lo, hi = window._layout._lo, window._layout._hi
    assert lo == 0.0
    assert float(np.percentile(occupied, 99.5)) == pytest.approx(hi)
    assert hi < metal.max_util(kind) + 1e-6
    assert hi > float(np.median(occupied))          # the stretch is real, not a no-op
    assert f"{metal.max_util(kind):.3f}" in window._panel.peak_label.text()


def test_auto_reaches_the_view_through_the_public_range_setter(window, metal):
    """Auto repaints; a range set on the spin boxes alone would leave the picture stale."""
    window._panel._pick(lambda layer: layer.is_horizontal)
    window._panel.auto_btn.click()
    # The spin box shows three decimals, which is coarser than the percentile it is given.
    assert window._layout.max_spin.value() == pytest.approx(window._layout._hi, abs=5e-4)
    assert window._layout._legend._hi == pytest.approx(window._layout._hi)


def test_auto_on_an_empty_map_is_a_no_op(window):
    """Every layer unticked: there is no range to fit, and dividing by nothing must not run."""
    window._panel._pick(None)
    window._panel.auto_btn.click()
    assert (window._layout._lo, window._layout._hi) == (0.0, 1.0)


def test_the_peak_follows_the_selected_map(window, metal):
    window._panel._pick(lambda layer: layer.is_horizontal)
    horizontal = metal.max_util(window._panel.current_kind())
    window._panel._pick(lambda layer: not layer.is_horizontal)
    assert f"{metal.max_util(window._panel.current_kind()):.3f}" in \
        window._panel.peak_label.text()
    assert f"{horizontal:.3f}" != f"{metal.max_util(window._panel.current_kind()):.3f}"


def test_a_contour_toggle_is_a_no_op(window):
    """There is no tree to click, but the call must not explode if one arrives."""
    window._layout.toggle_contour("TOP")
    assert window._layout._contour_items == []
    assert window._layout._contour_path is None


def test_a_map_rebuilt_from_a_db_renders_the_same(app, metal, tmp_path):
    """The db path end to end in the window: the panel's numbers, the map and the status bar are
    the same ones a full parse produces, because the grids and the layer table are the same.

    Both flavours are here. The first db was written by this design's own run and answers
    directly; the second was written by a sub-block dumped on its own, so its grids belong to
    another design's die and everything drawn from it had to be re-rasterised first. The window
    cannot tell them apart, which is the point: it is the same map either way.
    """
    import contextlib
    import io

    from vlsi_viewer.metal import build_metal
    from vlsi_viewer.ui_main import MainWindow

    def build(defs, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return build_metal(list(defs), [f"{SAMPLE}/cells.lef"], [f"{SAMPLE}/tech.lef"],
                               grid_size=10.0, **kwargs)

    dbs = tmp_path / "dbs"
    build([f"{SAMPLE}/top.def", f"{SAMPLE}/sub.def"], dump_db=str(dbs))
    rebuilt = build([], db_paths=[str(dbs / "top.def.db"), str(dbs / "sub.def.db")])

    alone = tmp_path / "alone"
    build([f"{SAMPLE}/sub.def"], dump_db=str(alone))
    replayed = build([f"{SAMPLE}/top.def"], db_paths=[str(alone / "sub.def.db")])
    assert replayed.replayed == ["SUB"]

    parsed_win = MainWindow(metal=metal)
    db_win = MainWindow(metal=rebuilt)
    replayed_win = MainWindow(metal=replayed)
    try:
        metal.set_scope("all")
        for data, other in ((rebuilt, db_win), (replayed, replayed_win)):
            # The layer panel is what a db must reproduce: the stack, its order and its checkboxes.
            assert list(parsed_win._panel._boxes) == list(other._panel._boxes)
            for layer, boxes in parsed_win._panel._boxes.items():
                assert boxes[0].text() == other._panel._boxes[layer][0].text(), layer
            data.set_scope("all")
            kind = metal.kinds()[0][0]
            assert np.array_equal(np.asarray(metal.heat(kind)), np.asarray(data.heat(kind)))
            assert parsed_win._panel.peak_label.text() == other._panel.peak_label.text()
    finally:
        parsed_win.close()
        db_win.close()
        replayed_win.close()
