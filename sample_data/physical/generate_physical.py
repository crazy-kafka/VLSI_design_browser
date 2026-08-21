"""Generate a realistic CPU-cluster physical sample (~100k instances).

The top-level ``CPU_CLUSTER`` holds 4 cores in the 4 corners with 4 different
orientations (N / W / S / E). Each core contains IFU, IEX and LSU sub-blocks,
and each sub-block has thousands of standard cells plus a small SRAM bank. An
"uncore" region (interconnect logic in the central cross + 8 L2 SRAM macros in
the horizontal band) sits between the cores.

Placement is non-overlapping by construction: standard cells are laid into
rows with a monotonically advancing cursor, and macros sit in dedicated
strips/bands. Overlap is the only way the density heat map can exceed 1.0, so
max density stays <= 1.0. The die side is solved so the average density (total
cell area / die area) lands at ~60%, and the generator self-verifies the result
through ``vlsi_viewer.physical.build_physical``.

Run:  python sample_data/physical/generate_physical.py
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# allow `python sample_data/physical/generate_physical.py` to import vlsi_viewer
_REPO = os.path.dirname(os.path.dirname(HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# ---------------------------------------------------------------------------
# Cell library
# ---------------------------------------------------------------------------
CELLS = {
    "INV_X1": {"area": 0.4, "size_x": 0.4, "size_y": 1.0,
               "is_inverter": True, "is_SVT": True},
    "INV_X2": {"area": 0.6, "size_x": 0.6, "size_y": 1.0,
               "is_inverter": True, "is_LVT": True},
    "BUF_X2": {"area": 0.8, "size_x": 0.8, "size_y": 1.0,
               "is_buffer": True, "is_LVT": True},
    "NAND2_X1": {"area": 0.8, "size_x": 0.8, "size_y": 1.0,
                 "is_combinational_cell": True, "is_SVT": True},
    "NOR2_X1": {"area": 0.8, "size_x": 0.8, "size_y": 1.0,
                "is_combinational_cell": True, "is_LVT": True},
    "AND2_X1": {"area": 1.0, "size_x": 1.0, "size_y": 1.0,
                "is_combinational_cell": True, "is_SVT": True},
    "OR2_X1": {"area": 1.0, "size_x": 1.0, "size_y": 1.0,
               "is_combinational_cell": True, "is_LVT": True},
    "XOR2_X1": {"area": 1.4, "size_x": 1.4, "size_y": 1.0,
                "is_combinational_cell": True, "is_ULVT": True},
    "MUX2_X1": {"area": 1.2, "size_x": 1.2, "size_y": 1.0,
                "is_combinational_cell": True, "is_LVT": True},
    "DFF_X1": {"area": 1.6, "size_x": 1.6, "size_y": 1.0,
               "is_register_cell": True, "register_bit_count": 1, "is_SVT": True},
    "DFF_X2": {"area": 2.0, "size_x": 2.0, "size_y": 1.0,
               "is_register_cell": True, "register_bit_count": 2, "is_LVT": True},
    "CLKBUF_X2": {"area": 0.8, "size_x": 0.8, "size_y": 1.0,
                  "is_clock_cell": True, "is_buffer": True, "is_LVT": True},
    "ICG_X1": {"area": 1.0, "size_x": 1.0, "size_y": 1.0,
               "is_integrated_clock_gating_cell": True, "is_clock_cell": True,
               "is_LVT": True},
    "SRAM": {"area": 1280.0, "size_x": 40.0, "size_y": 32.0,
             "is_macro": True, "is_sram": True},
}

SRAM = "SRAM"
SRAM_W = CELLS[SRAM]["size_x"]
SRAM_H = CELLS[SRAM]["size_y"]

# Weighted standard-cell pool (realistic logic mix).
_POOL = [
    ("INV_X1", 4), ("INV_X2", 3), ("BUF_X2", 4),
    ("NAND2_X1", 6), ("NOR2_X1", 6), ("AND2_X1", 5), ("OR2_X1", 5),
    ("XOR2_X1", 3), ("MUX2_X1", 4),
    ("DFF_X1", 6), ("DFF_X2", 3), ("CLKBUF_X2", 2), ("ICG_X1", 2),
]
STD_POOL = [name for name, w in _POOL for _ in range(w)]
MEAN_STD_W = sum(CELLS[n]["size_x"] for n in STD_POOL) / len(STD_POOL)

# ---------------------------------------------------------------------------
# Floorplan constants
# ---------------------------------------------------------------------------
CORE_SIZE = 210.0      # square core -> 4 orientations keep the same footprint
MARGIN = 15.0          # die margin around the 2x2 core array

# Per-core sub-block standard-cell counts (fit inside the core, see layout()).
SUB_STD = {"IFU": 8000, "IEX": 7400, "LSU": 7200}
SUB_SRAM = {"IFU": 2, "IEX": 3, "LSU": 2}   # macros per sub-block

UNCORE_STRIP = 15000   # std cells in the vertical cross strip (bottom + top halves)
UNCORE_ARMS = 1500     # std cells in each horizontal-band arm
N_L2 = 8               # L2 SRAM macros in the horizontal band (4 per arm)

ROW_UTIL = 0.85        # fraction of each region's width filled per row

# ---------------------------------------------------------------------------
# Placement helpers (non-overlapping by construction)
# ---------------------------------------------------------------------------

def _attrs(name, rng):
    return {
        "cell_name": name,
        "orient": "N",
        "leakage_power": round(0.02 * rng.uniform(0.5, 3.0), 4),
        "dynamic_power": round(0.05 * rng.uniform(0.5, 3.0), 4),
    }


def place_std_rows(cells, x0, y0, w, h, util=ROW_UTIL):
    """Place std cells into rows over (x0,y0,w,h); returns (name,x,y,orient)
    tuples. Cells advance a cursor left-to-right, rows stack bottom-up, so no
    two cells overlap. Cells that do not fit are dropped."""
    placed = []
    row_right = x0 + w * util
    x, y = x0, y0
    top = y0 + h
    idx = 0
    for name in cells:
        sx = CELLS[name]["size_x"]
        if x + sx > row_right:
            x = x0
            y += 1.0
            if y + 1.0 > top:
                break
        placed.append((name, x, y, ("N", "FN")[idx % 2]))
        x += sx
        idx += 1
    return placed


def place_std_rows_blocked(cells, x0, y0, w, h, blocked, util=ROW_UTIL):
    """Like place_std_rows but skips x-ranges covered by ``blocked`` rects
    (list of (bx0, by0, bx1, by1)) on the rows they intersect."""
    placed = []
    y = y0
    ci = 0
    while y + 1.0 <= y0 + h and ci < len(cells):
        segs = [(x0, x0 + w * util)]
        for bx0, by0, bx1, by1 in blocked:
            if by1 <= y or by0 >= y + 1.0:
                continue
            nb = (bx0, bx1)
            new = []
            for s0, s1 in segs:
                if nb[0] >= s1 or nb[1] <= s0:
                    new.append((s0, s1))
                else:
                    if nb[0] > s0:
                        new.append((s0, nb[0]))
                    if nb[1] < s1:
                        new.append((nb[1], s1))
            segs = new
        for s0, s1 in segs:
            x = s0
            while ci < len(cells):
                name = cells[ci]
                sx = CELLS[name]["size_x"]
                if x + sx > s1:
                    break
                placed.append((name, x, y, "N"))
                x += sx
                ci += 1
        y += 1.0
    return placed


def place_sram_stack(n, x0, y0, orient="N"):
    """Place n SRAM macros stacked vertically from (x0,y0)."""
    return [("SRAM", x0, y0 + k * (SRAM_H + 2.0), orient) for k in range(n)]


def place_sram_row(n, x0, y0, orient="N"):
    """Place n SRAM macros side-by-side from (x0,y0)."""
    return [("SRAM", x0 + k * (SRAM_W + 4.0), y0, orient) for k in range(n)]


def _insts(prefix, placed, rng):
    """Turn placed (name,x,y,orient) tuples into an instances dict."""
    out = {}
    for k, (name, x, y, orient) in enumerate(placed):
        attrs = _attrs(name, rng)
        attrs["orient"] = orient
        attrs["location_x"] = round(x, 3)
        attrs["location_y"] = round(y, 3)
        out[f"{prefix}_{k}"] = attrs
    return out


def _write(path, data, indent=None):
    with open(os.path.join(HERE, path), "w") as f:
        json.dump(data, f, indent=indent)


def _rect_poly(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------

def build_subblock(name, rng):
    """One IFU / IEX / LSU block: std cells in rows + a vertical SRAM strip.

    Cell coordinates are in the sub-block's OWN local frame (origin 0,0); the
    core block places each sub-block at its core-local offset.
    """
    n_std = SUB_STD[name]
    n_sram = SUB_SRAM[name]
    C = CORE_SIZE
    if name == "IFU":
        # top strip of the core (placed by CORE at core-local (0, 0))
        region = (0.0, 0.0, C, 0.32 * C)
        std_rect = (0.0, 0.0, C - SRAM_W, 0.32 * C)
        sram_x, sram_y = C - SRAM_W, 0.0
    else:
        # IEX / LSU bottom half, 0.5*C wide each (placed by CORE at x-offset)
        region = (0.0, 0.0, 0.5 * C, 0.68 * C)
        std_rect = (0.0, 0.0, 0.5 * C - SRAM_W, 0.68 * C)
        sram_x, sram_y = 0.5 * C - SRAM_W, 0.0

    cells = [rng.choice(STD_POOL) for _ in range(n_std)]
    std = place_std_rows(cells, *std_rect)
    sram = place_sram_stack(n_sram, sram_x, sram_y)

    insts = _insts("std", std, rng)
    insts.update(_insts("sram", sram, rng))
    rx0, ry0 = region[0], region[1]
    return {
        "top_name": name,
        "boundary": _rect_poly(rx0, ry0, rx0 + region[2], ry0 + region[3]),
        "instances": insts,
    }


def build_core(rng):
    """CORE block: references IFU / IEX / LSU placed in the core's frame."""
    C = CORE_SIZE
    insts = {
        "ifu": dict(_attrs("IFU", rng), location_x=0.0, location_y=0.0, orient="N"),
        "iex": dict(_attrs("IEX", rng), location_x=0.0, location_y=0.32 * C, orient="N"),
        "lsu": dict(_attrs("LSU", rng), location_x=0.5 * C, location_y=0.32 * C, orient="N"),
    }
    return {"top_name": "CORE",
            "boundary": _rect_poly(0.0, 0.0, C, C),
            "instances": insts}


def build_top(die, rng):
    """TOP (CPU_CLUSTER): 4 rotated cores at the corners + uncore cross."""
    C = CORE_SIZE
    m = MARGIN
    gap = die - 2 * m - 2 * C
    # gap == width of the central cross
    insts = {}
    # A rotated core keeps a different corner fixed at its placement origin:
    # N -> lower-left, W -> lower-right, S -> upper-right, E -> upper-left.
    ll = m
    rr = m + 2 * C + gap
    refs = [
        ("core_0", ll, ll, "N"),
        ("core_1", rr, ll, "W"),
        ("core_2", rr, rr, "S"),
        ("core_3", ll, rr, "E"),
    ]
    for name, x, y, orient in refs:
        attrs = _attrs("CORE", rng)
        attrs["orient"] = orient
        attrs["location_x"] = round(x, 3)
        attrs["location_y"] = round(y, 3)
        insts[name] = attrs

    # --- uncore logic cells in the vertical strip of the cross, split into a
    # --- bottom half and a top half so the strip reads evenly (the horizontal
    # --- band between the halves holds the L2 macros and arm logic).
    strip_b = (m + C, m, gap, C)            # bottom half
    strip_t = (m + C, m + C + gap, gap, C)  # top half
    strip_rects = [strip_b, strip_t]
    cells = [rng.choice(STD_POOL) for _ in range(UNCORE_STRIP)]
    half = (len(cells) + 1) // 2
    for i, (prefix, rect) in enumerate(zip(("uncore/b", "uncore/t"), strip_rects)):
        part = cells[i * half:(i + 1) * half]
        insts.update(_insts(prefix, place_std_rows(part, *rect), rng))

    # --- 8 L2 SRAM macros in the horizontal band arms ---
    band_y0 = m + C + (gap - SRAM_H) / 2.0
    left_x = m + 6.0
    right_x = m + C + gap + 6.0
    l2 = place_sram_row(4, left_x, band_y0) + place_sram_row(4, right_x, band_y0)
    insts.update(_insts("l2/sram", l2, rng))

    # --- uncore logic cells in the arms, around the L2 macros ---
    # the horizontal band spans the full die width; skip the vertical strip so
    # the cross arms don't overlap the strip's cells.
    band = (m, m + C, 2 * C + gap, gap)
    blocked = [(x, y, x + SRAM_W, y + SRAM_H) for _, x, y, _ in l2]
    blocked.append((m + C, m, m + C + gap, m + 2 * C + gap))  # vertical strip
    arm_cells = [rng.choice(STD_POOL) for _ in range(UNCORE_ARMS * 2)]
    insts.update(_insts("uncore/arm", place_std_rows_blocked(arm_cells, *band, blocked), rng))

    return {"top_name": "CPU_CLUSTER",
            "boundary": _rect_poly(0.0, 0.0, die, die),
            "instances": insts}


def _expand_count(insts, cell_name_to_blocks):
    """Count leaf instances when block references are expanded (for reporting)."""
    total = 0
    for attrs in insts.values():
        if attrs["cell_name"] in cell_name_to_blocks:
            total += _expand_count(cell_name_to_blocks[attrs["cell_name"]],
                                   cell_name_to_blocks)
        else:
            total += 1
    return total


def main():
    rng = random.Random(0)
    _write("cell_info.json", CELLS, indent=2)

    # Solve the die side so the average density lands at ~60%: the cell area is
    # fixed by the placement counts, so pick L = sqrt(area / 0.60).
    n_std = (4 * sum(SUB_STD.values()) + UNCORE_STRIP + 2 * UNCORE_ARMS)
    n_sram = (4 * sum(SUB_SRAM.values()) + N_L2)
    area = n_std * MEAN_STD_W + n_sram * SRAM_W * SRAM_H
    die = int(round(math.sqrt(area / 0.60) / 10.0) * 10)
    die = max(die, int(2 * MARGIN + 2 * CORE_SIZE + 40))  # leave a ~40-wide cross

    ifu = build_subblock("IFU", rng)
    iex = build_subblock("IEX", rng)
    lsu = build_subblock("LSU", rng)
    core = build_core(rng)
    top = build_top(die, rng)

    _write("IFU.json", ifu, indent=2)
    _write("IEX.json", iex, indent=2)
    _write("LSU.json", lsu, indent=2)
    _write("CORE.json", core, indent=2)
    _write("instance_info.json", top, indent=None)

    blocks = {"IFU": ifu["instances"], "IEX": iex["instances"],
              "LSU": lsu["instances"], "CORE": core["instances"]}
    expanded = _expand_count(top["instances"], blocks)
    density = area / (die * die)

    unique = (len(top["instances"]) + len(core["instances"]) + len(ifu["instances"])
              + len(iex["instances"]) + len(lsu["instances"]))
    print("wrote physical sample:")
    print("  files: IFU.json IEX.json LSU.json CORE.json instance_info.json")
    print(f"  unique JSON records : {unique}")
    print(f"  expanded instances  : {expanded} (std {n_std} + SRAM {n_sram})")
    print(f"  die                 : {die} x {die}")
    print(f"  avg density (est.)  : {density:.3f} (target ~0.60)")
    verify()


def verify():
    """Self-check through the real parser + rasterizer (no GUI needed)."""
    try:
        from vlsi_viewer.physical import build_physical
    except ImportError:
        print("  verify: vlsi_viewer not importable; skipped")
        return
    files = ["instance_info.json", "CORE.json", "IFU.json", "IEX.json", "LSU.json"]
    paths = [os.path.join(HERE, f) for f in files]
    pd_ = build_physical(paths, os.path.join(HERE, "cell_info.json"))

    n = len(pd_.boxes)
    total_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in pd_.boxes)
    x0, y0, x1, y1 = pd_.extent
    die_area = (x1 - x0) * (y1 - y0)
    avg = total_area / die_area
    dmax = float(pd_.density.max())

    print(f"  verify: {n} leaf boxes, avg density {avg:.3f}, "
          f"max density bin {dmax:.3f}")

    assert 90_000 <= n <= 110_000, f"instance count {n} out of range"
    assert 0.55 <= avg <= 0.65, f"avg density {avg:.3f} not ~60%"
    assert dmax <= 1.0 + 1e-9, f"max density {dmax} exceeds 1.0"
    assert dmax > 0.85, f"no dense bins (max {dmax})"
    assert float(pd_.density.min()) < 0.05, "no empty bins (no density variety)"
    print("  verify: OK (count ~100k, density ~60%, max <= 1.0, varied)")


if __name__ == "__main__":
    main()
