"""Runtime configuration defaults."""

# Default value for hier_min_inst_count_threshold (tree display filter only).
DEFAULT_MIN_INST_COUNT = 100

# Directory name for the pickle cache, created beside the input JSONs.
CACHE_DIR_NAME = ".vlsi_cache"

# Physical-mode heat-map grid cell size.
DEFAULT_GRID_SIZE = 3.0

# Hierarchy contour: merge instances closer than this many grid cells.
DEFAULT_CONTOUR_GAP_FACTOR = 2.0
