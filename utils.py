"""Small shared helpers (Print) used by vlsi_viewer.coordinateProcess."""


def Print(*args, **kwargs):
    """Print a message to stdout (stand-in for a richer logging/print helper)."""
    print(*args, **kwargs)
