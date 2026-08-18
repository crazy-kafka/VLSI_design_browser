"""Visual theme: "cleanroom silicon" refined light palette + application."""
from PyQt5.QtGui import QColor, QPalette

# Palette tokens
BG = "#F4F6F8"          # window background (cool off-white)
SURFACE = "#FFFFFF"     # tree / table surface
SURFACE_ALT = "#EDF1F4"  # subtle alternate row
SELECTION = "#D9EBEE"   # selection tint (light teal)
HAIRLINE = "#D9E0E6"    # rules / borders
TEXT = "#1B2431"        # primary text (blue-slate ink)
TEXT_MUTED = "#64748B"  # secondary text (cool slate)
ACCENT = "#0E7C86"      # deep silicon teal
MACRO = "#A8732B"       # amber (macro columns only)

BAR_ALPHA = 0x3C        # data-bar fill opacity


def _qc(hex_str, alpha=255):
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


# Precomputed QColor objects.
BG_C = _qc(BG)
SURFACE_C = _qc(SURFACE)
SURFACE_ALT_C = _qc(SURFACE_ALT)
SELECTION_C = _qc(SELECTION)
TEXT_C = _qc(TEXT)
BAR_COLOR = _qc(ACCENT, BAR_ALPHA)
MACRO_BAR_COLOR = _qc(MACRO, BAR_ALPHA)

QUALITY_ALPHA = 0x90


def quality_color(goodness):
    """Red (bad) -> yellow -> green (good) color for a 'quality' bar.

    ``goodness`` is 0..1 (0 = worst/red, 1 = best/green).
    """
    g = max(0.0, min(1.0, float(goodness)))
    c = QColor.fromHsv(int(g * 120), 255, 235)
    c.setAlpha(QUALITY_ALPHA)
    return c


def _stylesheet():
    return f"""
    QMainWindow, QDialog {{ background: {BG}; }}
    QToolBar {{
        background: {SURFACE};
        border-bottom: 1px solid {HAIRLINE};
        spacing: 6px;
        padding: 4px 8px;
    }}
    QTreeWidget, QTableWidget {{
        background: {SURFACE};
        alternate-background-color: {SURFACE_ALT};
        border: 1px solid {HAIRLINE};
        selection-background-color: {SELECTION};
        selection-color: {TEXT};
    }}
    QHeaderView::section {{
        background: {BG};
        color: {TEXT_MUTED};
        padding: 6px 8px;
        border: none;
        border-bottom: 2px solid {HAIRLINE};
        border-right: 1px solid {HAIRLINE};
        font-weight: 600;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        background: {SURFACE};
        border: 1px solid {HAIRLINE};
        border-radius: 3px;
        padding: 3px 6px;
        color: {TEXT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
    QTabBar::tab {{
        background: transparent;
        color: {TEXT_MUTED};
        padding: 6px 14px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
    QStatusBar {{
        background: {SURFACE};
        border-top: 1px solid {HAIRLINE};
        color: {TEXT_MUTED};
    }}
    QCheckBox {{ color: {TEXT}; }}
    """


def apply_theme(app):
    """Apply the palette + stylesheet to the application."""
    palette = QPalette()
    palette.setColor(QPalette.Window, BG_C)
    palette.setColor(QPalette.Base, SURFACE_C)
    palette.setColor(QPalette.AlternateBase, SURFACE_ALT_C)
    palette.setColor(QPalette.Text, TEXT_C)
    palette.setColor(QPalette.WindowText, TEXT_C)
    palette.setColor(QPalette.Button, SURFACE_C)
    palette.setColor(QPalette.ButtonText, TEXT_C)
    palette.setColor(QPalette.Highlight, SELECTION_C)
    palette.setColor(QPalette.HighlightedText, TEXT_C)
    palette.setColor(QPalette.ToolTipBase, SURFACE_C)
    palette.setColor(QPalette.ToolTipText, TEXT_C)
    app.setPalette(palette)
    app.setStyleSheet(_stylesheet())
