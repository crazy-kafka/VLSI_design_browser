"""Metal-density widgets: what to show, and the arithmetic behind a pixel.

Two panels, deliberately separate, because the window shows them in different places:

**`MetalPanel`** (right) selects what the map shows. The layer checkboxes, bottom to top, each
with the layer's own width / spacing / pitch beside its mean utilisation - the metric's capacity
is `area x (W + S) / P`, so those three numbers are the ones that explain the fourth. Below
them, the net class: a power stripe is fixed and deliberate, so merging it with signal metal
makes a region under a stripe read as a routing hotspot. Ticking several layers shows them
grouped, and a group is read as a capacity-weighted mean, so ticking the horizontal layers is
the horizontal-routing map, which is the read the mode exists for.

**`CellDetailPanel`** (left) is the readout for the cell under the cursor: `D`, `C` and `U` for
every selected layer, the group's `sum(D)/sum(C)`, which layer is the bottleneck, and whether
either direction still has room. That readout is the reason the metric is worth having in a GUI
at all - it makes the colour checkable rather than something to take on trust.

The map's value range is built here too but placed in the window's toolbar, along with the
window itself: `MetalPanel` creates the range widgets and never lays them out, exactly as
`LayoutView(external_controls=True)` does with its controls row.
"""
import numpy as np
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .metal import SCOPE_ALL, SCOPE_POWER, SCOPE_SIGNAL

SCOPE_LABELS = [(SCOPE_ALL, "Signal + power"), (SCOPE_SIGNAL, "Signal only"),
                (SCOPE_POWER, "Power only")]

# How much of a map's occupied range the Auto button fits to. Not the maximum: one saturated
# cell - a power ring crossing a corner - would otherwise flatten everything else.
AUTO_PERCENTILE = 99.5

# How tall the detail table may grow before it scrolls. Sized to show a full 12-layer stack
# without a scrollbar; deeper stacks scroll, which is what the scroll area is for, and the cap
# keeps the pane's minimum height (and so the window's) from growing with the stack.
DETAIL_MAX_HEIGHT = 340


def _fmt(value: float) -> str:
    """Three significant figures, without a trailing zero-fest.

    The panel is narrow and the numbers are small; `17.0`, `73.7` and `100` read at a glance
    where `17.004`, `73.684` and `100.000` get clipped.
    """
    if value == 0:
        return "0"
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _microns(value: float) -> str:
    """A tech-LEF dimension, short but exact.

    Not `_fmt`: three significant figures would turn a real 0.065 um width into `0.06`, and
    the point of showing the rules is that they are the ones the capacity was computed from.
    """
    return f"{value:g}"


def _flexible(label: QLabel) -> QLabel:
    """Stop a label's text from setting its pane's minimum width.

    A QLabel's minimum width is the full width of whatever string it is holding, so a live
    readout makes the pane's minimum grow and shrink as the cursor moves - and a QSplitter
    will not size a pane below its minimum, so the divider refuses to be dragged narrower over
    a long line. Only safe in a vertical layout, where every row gets the full width anyway:
    in a horizontal one an `Ignored` label is given zero width, which is how the range spin
    boxes came to be invisible.
    """
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    return label


class MetalPanel(QWidget):
    """What the map shows: net class and routing layers.

    The value-range widgets are built here and placed in the toolbar by the window; see the
    module docstring. ``selection_changed`` is how the cell readout learns that the map it is
    describing has changed without the user moving the cursor.
    """

    selection_changed = pyqtSignal()

    def __init__(self, data, view, parent=None):
        super().__init__(parent)
        self.data = data
        self.view = view
        self._boxes = {}
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addWidget(self._scope_box())
        root.addWidget(self._layers_box(), 1)
        self._build_range_widgets()
        # Resizable rather than fixed: the splitter gives the pane its own hint and hands the
        # map everything else, and dragging the divider is the user's own fix for a number
        # that does not fit.
        self.setMinimumWidth(250)
        self.setMaximumWidth(460)

        self._sync_from_view()
        # Tell the view what the tick boxes select *now*. Without this the map is drawn for the
        # view's own default - the bottom layer alone - while the panel says every layer is
        # ticked, so the first thing a user sees is the M1 map (nearly empty) and it only
        # becomes the map they asked for once something else nudges the selection.
        self._apply_kind()

    # -- construction ----------------------------------------------------------------

    def _scope_box(self):
        box = QGroupBox("Net class")
        layout = QVBoxLayout(box)
        self.scope_combo = QComboBox()
        for key, label in SCOPE_LABELS:
            self.scope_combo.addItem(label, key)
        self.scope_combo.currentIndexChanged.connect(self._on_scope)
        layout.addWidget(self.scope_combo)
        return box

    def _layers_box(self):
        box = QGroupBox("Routing layers")
        outer = QVBoxLayout(box)

        buttons = QHBoxLayout()
        for label, pick in (("All H", lambda layer: layer.is_horizontal),
                            ("All V", lambda layer: not layer.is_horizontal),
                            ("None", None)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked, pick=pick: self._pick(pick))
            buttons.addWidget(button)
        outer.addLayout(buttons)

        # Unbounded height and given the layout's stretch: the layer selection is the primary
        # control and must never be the thing that gets squeezed.
        self.layers_area = area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        # The numbers columns are right-aligned, headings included, so a heading sits over the
        # digits it names rather than at the left edge of a stretched column.
        right = Qt.AlignRight | Qt.AlignVCenter
        for column, (heading, alignment) in enumerate(
                (("layer", Qt.AlignLeft | Qt.AlignVCenter), ("W/S/P", right),
                 ("dir", Qt.AlignLeft | Qt.AlignVCenter), ("U", right))):
            label = QLabel(heading)
            label.setAlignment(alignment)
            label.setStyleSheet("color: #999;")
            grid.addWidget(label, 0, column)
        # Every rule padded to the widest in the table, so the slashes line up down the column
        # instead of the digits shuffling row by row - `0.07/0.07/0.14` against `0.8/0.8/1.6`.
        pad = max((len(_microns(value)) for layer in self.data.layers
                   for value in (layer.width, layer.spacing, layer.pitch)), default=1)
        # Bottom to top, which is the stack order and the order the tech LEF lists them in.
        for row, layer in enumerate(self.data.layers, start=1):
            check = QCheckBox(layer.name)
            check.setChecked(True)
            check.stateChanged.connect(self._on_layers)
            if not layer.usable:
                check.setChecked(False)
                check.setEnabled(False)
            rules = QLabel("/".join(f"{_microns(value):>{pad}}"
                                    for value in (layer.width, layer.spacing, layer.pitch)))
            rules.setAlignment(right)
            rules.setStyleSheet("color: #666; font-family: Consolas, monospace;")
            direction = QLabel("H" if layer.is_horizontal else "V")
            direction.setStyleSheet("color: #888;")
            value = QLabel("")
            value.setAlignment(right)
            value.setStyleSheet("color: #666; font-family: Consolas, monospace;")
            for column, cell in enumerate((check, rules, direction, value)):
                cell.setToolTip(self._layer_tooltip(layer))
                grid.addWidget(cell, row, column)
            self._boxes[layer.name] = (check, value)
        grid.setRowStretch(len(self.data.layers) + 1, 1)
        # Leftover width goes to an empty column rather than to the last data column, so the
        # headings stay directly over the numbers they name.
        grid.setColumnStretch(4, 1)
        area.setWidget(inner)
        outer.addWidget(area, 1)
        return box

    def _layer_tooltip(self, layer) -> str:
        """The rules in full, plus the factor the capacity is normalised by.

        The factor lives here rather than as a fourth column because it is 1.000 on most
        layers - when the pitch is exactly width plus spacing - so it would cost a column of
        width on every row to say "nothing to see". On a layer where it is *not* 1.0, it is
        the answer to "why is this layer's capacity not its area?".
        """
        if not layer.usable:
            return (f"{layer.name}: no usable width in the tech LEF, so its wires cannot be "
                    f"measured and it is left unticked")
        factor = self.data.pitch_factor(layer)
        return (f"{layer.name}  {'horizontal' if layer.is_horizontal else 'vertical'}\n"
                f"width {_microns(layer.width)} um   spacing {_microns(layer.spacing)} um   "
                f"pitch {_microns(layer.pitch)} um\n"
                f"f = (W + S) / P = {factor:.3f}\n"
                f"capacity = routable area x {factor:.3f}")

    def _build_range_widgets(self):
        """The map's value range, built but not placed - the window's toolbar adopts them."""
        self.auto_btn = QPushButton("Auto")
        self.auto_btn.setToolTip(
            "fit the ramp to this map's own range.\n1.0 always means every track consumed, "
            "so this stretches the colours rather than changing what they measure")
        self.auto_btn.clicked.connect(self.auto_range)
        self.peak_label = QLabel("")
        # Exactly its text width: the last item in a QToolBar absorbs all the leftover space,
        # so a Preferred label would sit in a few hundred invisible pixels of it.
        self.peak_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

    # -- selection -------------------------------------------------------------------

    def current_kind(self):
        """The map kind for the current tick boxes: one layer, or a group of them."""
        picked = [layer.name for layer in self.data.layers
                  if self._boxes[layer.name][0].isChecked()]
        if not picked:
            # Nothing ticked: an empty map rather than silently showing everything, so what
            # is on screen always matches what the panel says is selected.
            return "G:"
        if len(picked) == 1:
            return f"L:{picked[0]}"
        return self.data.group_kind(picked)

    def _pick(self, predicate) -> None:
        self._syncing = True
        for layer in self.data.layers:
            check, _value = self._boxes[layer.name]
            if check.isEnabled():
                check.setChecked(bool(predicate(layer)) if predicate else False)
        self._syncing = False
        self._apply_kind()

    def _on_layers(self, _state) -> None:
        if not self._syncing:
            self._apply_kind()

    def _apply_kind(self) -> None:
        self.view.set_kind(self.current_kind())
        self._update_details()
        self.selection_changed.emit()

    def _on_scope(self, _index) -> None:
        # Changing the scope redraws the same kind from different grids; the range cache is per
        # map, not per scope, so the ramp the user set is left alone.
        self.data.set_scope(self.scope_combo.currentData())
        self._apply_kind()

    def auto_range(self) -> None:
        """Fit the ramp to this map's own range.

        The fixed ``[0, 1]`` default is what makes "1.0 = every track consumed" true, and the
        INNOVUS ramp's first third spans 0…0.33, so a design peaking at 0.46 - a healthy one -
        renders as a nearly uniform dark rectangle. This stretches the colours without
        changing what they measure, and the peak stays on show beside it.
        """
        kind = self.current_kind()
        grid = self.data.heat(kind)
        occupied = grid[grid > 0]
        if occupied.size == 0:
            return
        self.view.set_range(0.0, max(float(np.percentile(occupied, AUTO_PERCENTILE)), 1e-3))

    def _sync_from_view(self) -> None:
        """Adopt the data's current scope, so the two cannot disagree at start-up."""
        index = self.scope_combo.findData(self.data.scope)
        if index >= 0:
            self.scope_combo.setCurrentIndex(index)

    # -- readouts --------------------------------------------------------------------

    def _update_details(self) -> None:
        """Refresh the per-layer means and the map's peak."""
        for layer in self.data.layers:
            value = self._boxes[layer.name][1]
            value.setText("—" if not layer.usable
                          else f"{self.data.layer_util(layer):.3f}")
        self.peak_label.setText(
            f"peak {self.data.max_util(self.current_kind()):.3f}   full = 1.000")


class CellDetailPanel(QWidget):
    """The readout for the hovered cell: the arithmetic behind the colour on screen.

    Fed from two directions, both wired by the window: the view's ``cell_hovered`` signal and
    the selection panel's ``selection_changed``. ``kind_of`` is how it asks what map to
    describe, so it never reaches into the other panel's state.
    """

    def __init__(self, data, kind_of, parent=None):
        super().__init__(parent)
        self.data = data
        self.kind_of = kind_of
        self._last_cell = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        box = QGroupBox("Cell detail")
        layout = QVBoxLayout(box)

        self.detail_head = _flexible(QLabel("hover a cell"))
        # Wraps rather than clips: the coordinates are the longest line in the pane and the one
        # thing here that must never be cut in half.
        self.detail_head.setWordWrap(True)
        self.detail_head.setStyleSheet("color: #444; font-family: Consolas, monospace;")
        layout.addWidget(self.detail_head)

        # Scrollable and capped, so a twenty-layer stack cannot push the summary lines out of
        # the window. The table and the height it needs are built by `_new_grid`/`_install_grid`,
        # which `refresh` below calls; see `_new_grid` for why the order matters.
        self.detail_area = area = QScrollArea()
        area.setWidgetResizable(True)
        layout.addWidget(area)
        self.detail_grid = None

        self.detail_sum = QLabel("")
        self.detail_split = QLabel("")
        self.detail_note = QLabel("")
        for label in (self.detail_sum, self.detail_split):
            label.setWordWrap(True)
            label.setStyleSheet("color: #222; font-family: Consolas, monospace;")
            layout.addWidget(label)
        self.detail_note.setWordWrap(True)
        self.detail_note.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.detail_note)

        root.addWidget(box)
        root.addStretch(1)
        self.setMinimumWidth(250)
        self.setMaximumWidth(460)

        self.refresh()

    # -- inputs ----------------------------------------------------------------------

    def on_cell(self, ix: int, iy: int) -> None:
        """Show the cell under the cursor, or blank the readout when there is none."""
        self._last_cell = (ix, iy) if ix >= 0 else None
        if ix < 0 or iy < 0:
            self._blank("hover a cell")
            return
        try:
            detail = self.data.cell_detail(ix, iy, self.kind_of())
        except (IndexError, ValueError):
            self._blank("hover a cell")
            return

        self.detail_head.setText(f"cell ({ix},{iy}) x={detail['x']:.0f} y={detail['y']:.0f}")
        self._fill_grid(detail)
        self.detail_sum.setText(
            f"sum(D)/sum(C) = {detail['util']:.4f}\n"
            f"  {_fmt(detail['consumed'])}/{_fmt(detail['capacity'])}")
        self.detail_split.setText(self._split_words(detail))

    def refresh(self) -> None:
        """Re-render for the current selection, or say what the selection is if idle.

        Called when the map changes under a stationary cursor - the numbers on screen must
        describe the map that is on screen.
        """
        kind = self.kind_of()
        self.detail_note.setText(self._capacity_note())
        if self._last_cell is not None:
            self.on_cell(*self._last_cell)
        else:
            self.detail_head.setText(f"{len(self.data.layers_of(kind))} layer(s) selected")
            self._new_grid()
            self._install_grid()

    def _capacity_note(self) -> str:
        """What took capacity away, said in terms of the two mechanisms.

        They are not equally trustworthy: one is the macro's own ``OBS`` geometry, the other is
        a layer count guessed for a macro whose LEF declares nothing. A reader comparing two
        cells needs to know which they are looking at, so the fallback is named rather than
        folded into a single sentence about "macros".
        """
        blockage = self.data.blockage
        observed = blockage.get("obs_cells", 0)
        guessed = blockage.get("fallback_cells", 0)
        depth = self.data.macro_block_layers
        # The fallback counts from the bottom of the *whole* stack, so the count is not always
        # the answer once a range is being measured: the layers it did reach are named when it
        # is not, so a reader does not go looking for capacity that was never taken. Empty
        # when the flag is off, which blocks nothing whatever the macros declare.
        names = blockage.get("fallback_layer_names") or []
        if depth <= 0:
            falls_back = ""
        elif len(names) == depth:
            falls_back = f"the bottom {depth} layer(s) of the stack"
        elif names:
            falls_back = (f"{depth} layer(s) of the whole stack, which is "
                          f"{', '.join(names)} here")
        else:
            falls_back = "no layer inside the measured range"
        if observed and guessed:
            return (f"capacity: less each macro's OBS; {guessed} declare none"
                    + (f" and block {falls_back}" if falls_back else ""))
        if observed:
            return f"capacity: less each macro's own OBS"
        if guessed and falls_back:
            return (f"capacity: less macro area on {falls_back} - no OBS in the LEF to say "
                    f"which")
        return "capacity: no macro blocks anything"

    # -- rendering -------------------------------------------------------------------

    def _fill_grid(self, detail) -> None:
        """One header row and one row per selected layer, with the bottleneck picked out.

        The column headings earn their line: spelling out `D`, `C` and `U` on every row costs
        three characters twelve times over, and the pane is the scarce dimension here.
        """
        rows = detail["layers"]
        worst = max(range(len(rows)), key=lambda index: rows[index]["util"]) if rows else -1
        grid = self._new_grid()
        for column, heading in enumerate(("layer", "D/C", "U")):
            label = QLabel(heading)
            label.setStyleSheet("color: #999; font-family: Consolas, monospace;")
            grid.addWidget(label, 0, column)
        for row, entry in enumerate(rows, start=1):
            bottleneck = (row - 1) == worst and entry["util"] > 0
            cells = [
                QLabel(entry["name"] + (" *" if bottleneck else "")),
                QLabel(f"{_fmt(entry['consumed']):>5}/{_fmt(entry['capacity']):<5}"),
                QLabel(f"{entry['util']:.3f}"),
            ]
            for column, cell in enumerate(cells):
                cell.setStyleSheet(
                    "font-family: Consolas, monospace; "
                    + ("color: #111; font-weight: bold;" if bottleneck else "color: #444;"))
                grid.addWidget(cell, row, column)
        self._install_grid()

    def _new_grid(self) -> QGridLayout:
        """Start a fresh table on a widget that is **not yet** in the scroll area.

        Three Qt behaviours have to be worked around to size this table, and a user reported
        the symptom of getting them wrong: a twelve-row readout three rows tall, with a
        scrollbar and the rest of the pane empty beneath it.

        A `QScrollArea` resizes its widget to the viewport, and a `QGridLayout` computes its
        hint from the geometry it finds itself in - so a table installed while the area is a
        few pixels tall reports *no* height, the area stays that tall, and the two keep each
        other small. Filling a detached widget first and measuring it there breaks the loop.
        A `QGridLayout` also keeps a row structure for every row it has ever held, so the
        table is replaced rather than re-filled; installing a fresh widget also disposes of the
        old labels, which `takeAt` alone does not.
        """
        inner = QWidget()
        self.detail_grid = grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        self._inner = inner
        return grid

    def _install_grid(self) -> None:
        """Size the scroll area to the table it is about to hold, then hand it over."""
        needed = self.detail_grid.sizeHint().height() + 2 * self.detail_area.frameWidth()
        self.detail_area.setFixedHeight(min(max(0, needed), DETAIL_MAX_HEIGHT))
        self.detail_area.setWidget(self._inner)     # deletes the widget it had before

    @staticmethod
    def _split_words(detail) -> str:
        """Whether either direction still has room - the reason the H/V split exists.

        A cell with its horizontal layers full and its vertical layers empty is still
        routable: the router escapes upward. Both busy is the case worth looking at, so it is
        said in words rather than left as two numbers to compare.
        """
        def peak(direction):
            return max((entry["util"] for entry in detail["layers"]
                        if entry["direction"] == direction), default=0.0)

        horizontal, vertical = peak("H"), peak("V")
        verdict = ("no room either way" if min(horizontal, vertical) > 0.5
                   else "escapable" if max(horizontal, vertical) > 0 else "")
        return (f"  H max {horizontal:.3f}   V max {vertical:.3f}"
                + (f"\n  {verdict}" if verdict else ""))

    def _blank(self, message: str) -> None:
        self.detail_head.setText(message)
        self.detail_sum.setText("")
        self.detail_split.setText("")
        self._new_grid()
        self._install_grid()
