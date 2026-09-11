"""Small helpers shared by the vendored EDA parsers.

These lived in a repo-root ``utils.py`` in the project the parsers came from. Only
``Print`` was carried over when this repo's ``utils.py`` was created, which left
``readFile`` undefined and ``CoordinateProcess`` unreachable, so none of the parsers
were importable. They now import from here instead, and the one ``CoordinateProcess``
use was inlined, so nothing under ``vlsi_viewer/`` depends on the repo root being on
``sys.path``.
"""


def Print(*args, **kwargs):
    """Print a message to stdout (stand-in for a richer logging/print helper)."""
    print(*args, **kwargs)


def readFile(path):
    """Return the full text of ``path``.

    The DEF parser handles ``.gz`` itself, so this stays a plain text read.
    """
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()
