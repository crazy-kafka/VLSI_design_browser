"""Regenerate the README's screenshots from the bundled samples.

    python docs/capture.py            # writes docs/compare.png, physical.png, metal.png

The images in the README are captures of the running application, and this is the script that
produces them - so they can be checked rather than trusted. It drives the same code path each CLI
subcommand drives and saves the window with `QWidget.grab()`, offscreen, with no display attached.

**The fonts have to be loaded by hand.** Offscreen Qt starts with an *empty* font database - text
comes out as boxes - and `ui_tree` picks its monospace family from that database when it is first
imported. So this file loads system fonts first and imports the application modules afterwards;
that ordering is the reason the imports are not at the top.

The commands captured are the README's own three - `python quickstart.py json | physical | metal`,
taken from `quickstart.argv_for` rather than restated here, so an image cannot show a command line
the README does not. Each is left on its first screen at the window size the README uses: no
clicking, no picking a nicer map.
"""
import contextlib
import glob
import io
import os
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtGui import QFont, QFontDatabase  # noqa: E402  - after the offscreen setting
from PyQt5.QtWidgets import QApplication, QSplitter  # noqa: E402

SIZE = (1600, 900)
# Which shortcut each image is: compare = the two-version diff, physical = the heat map, metal =
# the per-layer routing map.
CAPTURES = [("compare", "json"), ("physical", "physical"), ("metal", "metal")]
# A pane is sized from its *hint* unless someone says otherwise, so the physical window gave the
# tree only the sum of its columns and they came out 3-22 px wide, every value clipped to "1.60",
# "68%". Metal mode sets its own pane widths (ui_main.py); this is the one the physical window
# needs to stay legible next to the map at this size.
PANE_SIZES = {"physical": [700, 900]}
# The density column and the first heat map are computed on a background thread, and the tree's
# columns are laid out on the first resize: the window is shown and the loop spun before it is
# grabbed, or the capture is a half-drawn window.
SETTLE = 60

# One UI family and one monospace, by file - the names the application asks for on a real desktop.
FONT_FILES = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/consola.ttf",
              "/usr/share/fonts/**/DejaVuSans.ttf", "/usr/share/fonts/**/DejaVuSansMono.ttf",
              "/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Menlo.ttc"]
UI_FAMILIES = ("Segoe UI", "DejaVu Sans", "Arial", "Sans Serif")


def _load_fonts(app):
    """Give offscreen Qt a font database, then a default family that exists."""
    loaded = [path for pattern in FONT_FILES
              for path in glob.glob(pattern, recursive=True)
              if QFontDatabase.addApplicationFont(path) >= 0]
    families = set(QFontDatabase().families())
    for family in UI_FAMILIES:
        if family in families:
            app.setFont(QFont(family, 9))
            break
    print(f"fonts: {len(loaded)} file(s) loaded, {len(families)} famil(ies), "
          f"UI font {app.font().family()!r}, fixed font "
          f"{QFontDatabase.systemFont(QFontDatabase.FixedFont).family()!r}")


def _load_ui():
    """Import the window modules - after `_load_fonts`, which `ui_tree` reads at import time."""
    from vlsi_viewer import theme
    from vlsi_viewer.cli import parse_args, resolve_inputs
    from vlsi_viewer.metrics import build_design
    from vlsi_viewer.physical import build_physical
    from vlsi_viewer.ui_main import MainWindow
    return SimpleNamespace(theme=theme, parse_args=parse_args, resolve_inputs=resolve_inputs,
                           build_design=build_design, build_physical=build_physical,
                           MainWindow=MainWindow)


def _window(mod, argv):
    """The window for one demo, built the way its CLI subcommand builds it."""
    args = mod.parse_args(argv)
    if args.cmd == "metal":
        from vlsi_viewer.metal import build_metal
        return mod.MainWindow(metal=build_metal(args.def_files, args.lef, args.tech_lef))
    cells, blocks, compare, pins = mod.resolve_inputs(args)
    design1 = mod.build_design(blocks, cells)
    design2 = mod.build_design(compare, cells) if compare else None
    physical = (mod.build_physical(blocks, cells, grid_size=args.grid_size, pins=pins)
                if getattr(args, "physical_mode", False) else None)
    return mod.MainWindow(design1, design2, physical=physical)


def capture(app, mod, name, argv):
    with contextlib.redirect_stdout(io.StringIO()):
        window = _window(mod, argv)
    window.resize(*SIZE)
    window.show()
    central = window.centralWidget()
    if isinstance(central, QSplitter) and name in PANE_SIZES:
        central.setSizes(PANE_SIZES[name])     # after show(): the splitter lays out on resize
    for _ in range(SETTLE):
        app.processEvents()
        time.sleep(0.02)
    path = os.path.join(HERE, f"{name}.png")
    window.grab().save(path)
    window.close()
    print(f"wrote {os.path.relpath(path, ROOT)}")


def main():
    import quickstart                       # the shortcuts themselves, not a copy of them
    app = QApplication.instance() or QApplication([])
    _load_fonts(app)
    mod = _load_ui()
    mod.theme.apply_theme(app)
    for name, shortcut in CAPTURES:
        capture(app, mod, name, quickstart.argv_for(shortcut))


if __name__ == "__main__":
    main()
