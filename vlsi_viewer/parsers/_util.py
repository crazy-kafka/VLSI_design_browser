"""Small helpers shared by the vendored EDA parsers.

These lived in a repo-root ``utils.py`` in the project the parsers came from. Only
``Print`` was carried over when this repo's ``utils.py`` was created, which left
``readFile`` undefined and ``CoordinateProcess`` unreachable, so none of the parsers
were importable. They now import from here instead, and the one ``CoordinateProcess``
use was inlined, so nothing under ``vlsi_viewer/`` depends on the repo root being on
``sys.path``.
"""
import gzip


def Print(*args, **kwargs):
    """Print a message to stdout (stand-in for a richer logging/print helper)."""
    print(*args, **kwargs)


def readFile(path):
    """Return the full text of ``path``, transparently handling a ``.gz`` suffix.

    Compressed inputs are the norm for large netlists, so a ``.gz`` name is read
    through gzip. ``BadGzipFile`` falls back to a plain read, which keeps a file that
    is merely *named* ``.gz`` usable - the same behaviour as the companion project's
    ``utils/readFile.py``.
    """
    if str(path).endswith(".gz"):
        try:
            with gzip.open(path, "rb") as fh:
                return fh.read().decode("utf-8")
        except gzip.BadGzipFile:
            pass
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()
