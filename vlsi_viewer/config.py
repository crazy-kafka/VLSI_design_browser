"""Runtime configuration defaults."""

# Default value for hier_min_inst_count_threshold (tree display filter only).
DEFAULT_MIN_INST_COUNT = 100

# Directory name for the pickle cache, created beside the input JSONs.
CACHE_DIR_NAME = ".vlsi_cache"

# Physical-mode heat-map grid cell size.
DEFAULT_GRID_SIZE = 3.0

# Hierarchy contour: merge instances closer than this many grid cells.
DEFAULT_CONTOUR_GAP_FACTOR = 2.0

# Metal-density-mode grid cell size. Finer than the physical-mode default on purpose: a
# router's own gcell is 1-5 um, and at 3 um the quantisation noise of counting individual
# wires per cell swamps the pattern. At 10 um a cell holds ~50-100 tracks on a 0.1-0.2 um
# pitch, which is the noise/resolution balance the metric wants.
DEFAULT_METAL_GRID_SIZE = 10.0

# How many of the bottom routing layers a hard macro removes capacity from when its LEF
# declares no OBS - a fallback, not the rule. A macro's obstructions say which layers it
# blocks and where, and that is what the metric uses; this is for the libraries that stay
# silent, where the alternative is assuming nothing blocks at all. The bottom layers are the
# guess because macros are built from the lower metals and the upper ones route over them.
# Counted from the bottom of the *whole* stack the tech LEF declares, before any
# --min-layer/--max-layer: a range the caller asked for must not move the guess onto a layer
# they asked to keep.
DEFAULT_MACRO_BLOCK_LAYERS = 4

# Guard on the number of bins in a metal grid. A 20 mm die at a 10 um grid is 4M bins per
# layer; the grids are float32, so this is roughly 16 MB each. Above it the run is warned
# about rather than refused - a user may well have the memory.
DEFAULT_METAL_MAX_BINS = 4_000_000
