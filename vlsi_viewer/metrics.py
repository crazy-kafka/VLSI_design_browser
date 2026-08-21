"""Hierarchy construction, filtering, flatten aggregation, and persistence."""
import hashlib
import logging
import os
import pickle

import numpy as np
import pandas as pd

from . import config, schema
from .loader import load_block, load_cell_info

logger = logging.getLogger(__name__)

# Raw aggregate columns computed per hierarchy node (flattened over descendants).
RAW_COLS = [
    "count", "area", "ulvt_area", "reg_bits", "mb_bits",
    "d1d2_count", "bi_count", "bi_area", "pul_count", "ckb_count", "icg_count",
    "macro_count", "macro_area",
]
_COUNT_COLS = ["count", "d1d2_count", "bi_count", "pul_count", "ckb_count",
               "icg_count", "macro_count"]
_STD_COLS = ["count", "area", "ulvt_area", "reg_bits", "mb_bits",
             "d1d2_count", "bi_count", "bi_area", "pul_count", "ckb_count", "icg_count"]
_MACRO_COLS = ["macro_count", "macro_area"]
CACHE_VERSION = "2"  # bump to invalidate stale pickles when RAW_COLS / metrics change


def _parent_of(path: str) -> str:
    i = path.rfind("/")
    return path[:i] if i != -1 else ""


def _depth_of(path: str) -> int:
    return path.count("/") + 1


def _join(prefix: str, rel: str) -> str:
    return f"{prefix}/{rel}" if prefix else rel


def _merge_blocks(earlier: pd.DataFrame, later: pd.DataFrame) -> pd.DataFrame:
    """Merge two same-top_name blocks; the earlier file wins on duplicate leaves."""
    if len(earlier) == 0:
        return later
    if len(later) == 0:
        return earlier
    a = earlier.set_index("leaf_instance_name")
    b = later.set_index("leaf_instance_name")
    merged = a.combine_first(b)  # a (earlier) takes precedence
    return merged.reset_index()


def load_blocks(block_paths) -> pd.DataFrame:
    """Load every block and merge them into flat leaves with absolute paths.

    A leaf whose ``cell_name`` matches another block's ``top_name`` is a block
    instance: that block's leaves are nested at the leaf's absolute path.

    Files sharing a ``top_name`` are merged; the earlier file takes precedence
    on duplicate leaf paths (A.1 absorbs A.2, which absorbs A.3).
    """
    blocks = {}
    for p in block_paths:
        name, df, _boundary = load_block(p)
        if name in blocks:
            logger.warning("duplicate top_name '%s'; merging %s (earlier file wins)", name, p)
            df = _merge_blocks(blocks[name], df)
        blocks[name] = df

    names = set(blocks)
    referenced = set()
    for df in blocks.values():
        referenced.update(df["cell_name"].dropna().astype(str).unique())

    tops = [n for n in blocks if n not in referenced]
    if not tops:
        logger.warning("no top-level block found (every top_name is referenced); "
                       "treating all blocks as top-level")
        tops = list(blocks)

    logger.info("%d block(s) loaded; top-level: %s", len(blocks), ", ".join(tops))

    parts = []
    visiting = []

    def expand(name, prefix):
        if name in visiting:
            logger.warning("cyclic block reference skipped: %s",
                           " -> ".join(visiting + [name]))
            return
        visiting.append(name)
        df = blocks[name]
        is_ref = df["cell_name"].isin(names)
        leaf = df[~is_ref].copy()
        if prefix and len(leaf):
            leaf["leaf_instance_name"] = prefix + "/" + leaf["leaf_instance_name"]
        parts.append(leaf)
        for rel, cell in zip(df.loc[is_ref, "leaf_instance_name"], df.loc[is_ref, "cell_name"]):
            logger.info("expanding block '%s' under '%s'", cell, _join(prefix, rel))
            expand(cell, _join(prefix, rel))
        visiting.pop()

    for top in tops:
        expand(top, top)

    columns = ["leaf_instance_name"] + [s.name for s in schema.INSTANCE_ATTRS]
    merged = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
    logger.info("merged %d leaf instance(s)", len(merged))
    return merged


def _build_leaves(inst: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """Join cell attributes onto instances and derive per-leaf fields."""
    leaves = inst.merge(cells, on="cell_name", how="left")

    # A cell is missing when its cell_name is absent OR not found in cell_info.
    # area is never NaN for a known cell (loader fills 0.0), so NaN == missing.
    leaves["is_missing"] = leaves["area"].isna()

    # Fill NaN cell attributes for missing cells so downstream boolean math is
    # clean; missing cells are excluded later via the is_missing flag.
    for spec in schema.CELL_ATTRS:
        leaves[spec.name] = leaves[spec.name].fillna(spec.default)

    leaves["parent_path"] = leaves["leaf_instance_name"].str.rsplit("/", n=1).str[0]
    no_slash = ~leaves["leaf_instance_name"].str.contains("/", regex=False)
    leaves.loc[no_slash, "parent_path"] = ""

    return leaves


def _flatten(leaves: pd.DataFrame) -> pd.DataFrame:
    """Compute per-hierarchy flatten aggregates.

    Returns a DataFrame indexed by hierarchy path with ``RAW_COLS`` plus
    ``parent`` and ``depth`` columns.
    """
    # --- direct std-cell contributions (the "counted" set) ---
    counted = leaves[
        ~leaves["is_missing"] & ~leaves["is_macro"] & ~leaves["is_physical_only"]
    ]
    n = len(counted)
    area = counted["area"].to_numpy(dtype="float64")
    is_ulvt = counted["is_ULVT"].to_numpy(dtype="bool")
    is_reg = counted["is_register_cell"].to_numpy(dtype="bool")
    reg_bits = counted["register_bit_count"].to_numpy(dtype="float64")
    is_bi = (counted["is_buffer"] | counted["is_inverter"]).to_numpy(dtype="bool")
    is_d1d2 = (counted["drive_size"] <= 2).to_numpy(dtype="bool")
    is_mb = is_reg & (reg_bits > 1)
    is_pul = counted["is_pulse_latch"].to_numpy(dtype="bool")
    is_ckb = is_bi & counted["is_clock_cell"].to_numpy(dtype="bool")
    is_icg = counted["is_integrated_clock_gating_cell"].to_numpy(dtype="bool")

    std = pd.DataFrame({
        "parent_path": counted["parent_path"].to_numpy(dtype=str),
        "count": np.ones(n, dtype="int64"),
        "area": area,
        "ulvt_area": np.where(is_ulvt, area, 0.0),
        "reg_bits": np.where(is_reg, reg_bits, 0.0),
        "mb_bits": np.where(is_mb, reg_bits, 0.0),
        "d1d2_count": is_d1d2.astype("int64"),
        "bi_count": is_bi.astype("int64"),
        "bi_area": np.where(is_bi, area, 0.0),
        "pul_count": is_pul.astype("int64"),
        "ckb_count": is_ckb.astype("int64"),
        "icg_count": is_icg.astype("int64"),
    })
    std = std.groupby("parent_path", sort=False).sum()

    # --- direct macro contributions ---
    macros = leaves[leaves["is_macro"] & ~leaves["is_missing"]]
    macro = pd.DataFrame({
        "parent_path": macros["parent_path"].to_numpy(dtype=str),
        "macro_count": np.ones(len(macros), dtype="int64"),
        "macro_area": macros["area"].to_numpy(dtype="float64"),
    })
    macro = macro.groupby("parent_path", sort=False).sum()

    # --- full hierarchy node set: all prefixes of all parent paths ---
    nodes = set(std.index) | set(macro.index)
    frontier = set(nodes)
    while frontier:
        nxt = set()
        for p in frontier:
            par = _parent_of(p)
            if par and par not in nodes:
                nodes.add(par)
                nxt.add(par)
        frontier = nxt

    agg = pd.DataFrame(0.0, index=pd.Index(sorted(nodes)), columns=RAW_COLS)
    for src, cols in ((std, _STD_COLS), (macro, _MACRO_COLS)):
        if len(src):
            agg.loc[src.index, cols] = src[cols].values

    # --- flatten: accumulate deepest-first into parents ---
    parent = pd.Series([_parent_of(p) for p in agg.index], index=agg.index)
    depth = pd.Series([_depth_of(p) for p in agg.index], index=agg.index)

    for d in range(int(depth.max()), 1, -1):
        nodes_at_d = depth[depth == d].index
        if len(nodes_at_d) == 0:
            continue
        contrib = agg.loc[nodes_at_d, RAW_COLS].copy()
        contrib.index = parent[nodes_at_d].values
        contrib = contrib.groupby(level=0, sort=False).sum()
        valid = contrib.index.intersection(agg.index)
        agg.loc[valid, RAW_COLS] += contrib.loc[valid, RAW_COLS].values

    for col in _COUNT_COLS:
        agg[col] = agg[col].round().astype("int64")

    agg["parent"] = parent
    agg["depth"] = depth
    return agg


class DesignData:
    """Preprocessed design data for one version."""

    def __init__(self, hier, missing_cells, children, instance_paths, cell_path):
        self.hier = hier              # DataFrame indexed by path (RAW_COLS+parent+depth)
        self.missing_cells = missing_cells   # sorted list of unique cell_name str
        self.children = children      # dict: parent path -> sorted list of child paths
        self.instance_paths = instance_paths  # list of block file paths
        self.cell_path = cell_path

    @property
    def roots(self):
        return self.children.get("", [])

    def metric_values(self, include_macros: bool = False) -> pd.DataFrame:
        """Return a DataFrame (index=path) of metric columns via the registry."""
        metrics = schema.METRICS if include_macros else schema.STD_METRICS
        return pd.DataFrame({m.key: m.compute(self.hier) for m in metrics},
                            index=self.hier.index)


def _children_map(hier: pd.DataFrame):
    """Build {parent_path: [child_path, ...]} in lexicographic order."""
    return hier.index.to_series().groupby(hier["parent"]).apply(list).to_dict()


def build_design(block_paths, cell_path: str) -> DesignData:
    """Load all blocks, merge into one hierarchy, and build the preprocessed design."""
    inst = load_blocks(block_paths)
    cells = load_cell_info(cell_path)
    leaves = _build_leaves(inst, cells)
    hier = _flatten(leaves)

    missing = sorted(
        leaves.loc[leaves["is_missing"], "cell_name"].dropna().astype(str).unique().tolist()
    )
    if missing:
        logger.warning("Found %d instance(s) with missing cell_info (%d unique cell_name); "
                       "excluded from all metrics.", int(leaves["is_missing"].sum()), len(missing))

    depth = int(hier["depth"].max()) if len(hier) else 0
    logger.info("built hierarchy: %d node(s), max depth %d, %d leaf instance(s)",
                hier.shape[0], depth, len(leaves))

    return DesignData(hier, missing, _children_map(hier), list(block_paths), cell_path)


def _source_key(paths) -> str:
    """Fast change-detection key from cache version + path + mtime + size."""
    h = hashlib.sha256()
    h.update(CACHE_VERSION.encode("utf-8"))
    for p in paths:
        st = os.stat(p)
        h.update(os.path.abspath(p).encode("utf-8"))
        h.update(str(st.st_mtime_ns).encode("utf-8"))
        h.update(str(st.st_size).encode("utf-8"))
    return h.hexdigest()[:16]


def _cache_file(block_paths, cell_path: str, cache_dir: str) -> str:
    key = _source_key(list(block_paths) + [cell_path])
    return os.path.join(cache_dir, f"{key}.pkl")


def load_or_build(block_paths, cell_path: str,
                  cache_dir: str = None, force: bool = False) -> DesignData:
    """Load from pickle cache when fresh, else build and persist."""
    if cache_dir is None:
        cache_dir = os.path.join(
            os.path.dirname(os.path.abspath(block_paths[0])), config.CACHE_DIR_NAME)
    cache_file = _cache_file(block_paths, cell_path, cache_dir)

    if not force and os.path.exists(cache_file):
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            if not set(RAW_COLS).issubset(data.hier.columns):
                logger.warning("cached data schema is stale (missing columns); rebuilding")
            else:
                logger.info("pickle cache hit: %s", cache_file)
                return data
        except Exception as exc:  # corrupt/stale cache -> rebuild
            logger.warning("cache load failed (%s); rebuilding", exc)

    data = build_design(block_paths, cell_path)
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(data, f)
    logger.info("pickle cache written: %s", cache_file)
    return data


def diff_table(d1, d2, include_macros: bool = False) -> pd.DataFrame:
    """Return per-path diff columns ``{key}_abs`` and ``{key}_rel`` for two versions.

    Rows are the union of both hierarchies' paths. Values missing on either
    side become NaN (rendered as ``—``).
    """
    metrics = schema.METRICS if include_macros else schema.STD_METRICS
    a = d1.metric_values(include_macros)
    b = d2.metric_values(include_macros)
    paths = a.index.union(b.index)
    a = a.reindex(paths)
    b = b.reindex(paths)
    out = {}
    for m in metrics:
        av = a[m.key].to_numpy(dtype="float64")
        bv = b[m.key].to_numpy(dtype="float64")
        with np.errstate(invalid="ignore", divide="ignore"):
            d = bv - av
            abs_v = d * 100.0 if m.kind == "percent" else d
            rel_v = np.where(av == 0, np.nan, d / av)
        out[f"{m.key}_abs"] = abs_v
        out[f"{m.key}_rel"] = rel_v
    return pd.DataFrame(out, index=paths)
