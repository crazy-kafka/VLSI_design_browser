"""Generate a small browsable EDA sample: macro LEF + DEF + gate-level Verilog.

Unlike ``sample_data/physical`` (108k instances, JSON only), this sample is sized to a
few thousand instances so the DEF stays small enough to parse on every test run, while
still having real hierarchy, hard macros, filler and tap cells - enough for the tree,
the contours and the density heat map to be worth browsing:

    CPU ``core``
      u0, u1                     (two identical units)
        b0, b1, b2               (three identical sub-blocks per unit)
          <std, filler and tap cells>   placed in rows
      smem_0 .. smem_3           (SRAM hard macros in a band below the blocks)

All three files describe the same floorplan, so the ``def`` and ``verilog`` subcommands
can be compared. They do NOT list the same instances, and that is correct: a gate-level
netlist has no filler, tap or decap cells, while a DEF does - and the DEF converter
drops filler on top of that (it tiles every row gap, so counting it would peg the
density map at 100%).

Run:  python sample_data/eda/generate_eda_sample.py
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# ---------------------------------------------------------------------------
# Cell library: (name, width, height, LEF class, pool weight, physical_only)
# ---------------------------------------------------------------------------
# The Vt suffixes and the MB<n>/SDF naming follow the conventions the cell_info
# heuristics in vlsi_viewer/parsers/convert.py key on (ULVT%/MB%/D1D2% columns).
# The last flag is this file's own statement of which cells are area-only, and
# verify() checks it against what the name heuristics actually derive.
CELLS = [
    ("INV_X1_SVT",    0.4, 1.0, "CORE", 8, False),
    ("INV_X2_LVT",    0.6, 1.0, "CORE", 6, False),
    ("BUF_X2_SVT",    0.8, 1.0, "CORE", 6, False),
    ("BUF_X4_LVT",    1.2, 1.0, "CORE", 4, False),
    ("NAND2_X1_SVT",  0.8, 1.0, "CORE", 10, False),
    ("NOR2_X1_LVT",   0.8, 1.0, "CORE", 10, False),
    ("AND2_X1_SVT",   1.0, 1.0, "CORE", 8, False),
    ("OR2_X1_LVT",    1.0, 1.0, "CORE", 8, False),
    ("XOR2_X1_ULVT",  1.4, 1.0, "CORE", 5, False),
    ("MUX2_X1_LVT",   1.2, 1.0, "CORE", 6, False),
    ("SDF_X1_SVT",    1.6, 1.0, "CORE", 7, False),
    ("SDF_X2_LVT",    2.0, 1.0, "CORE", 4, False),
    ("MB4_SDF_ULVT",  4.0, 1.0, "CORE", 3, False),
    ("CLKBUF_X2_LVT", 0.8, 1.0, "CORE", 3, False),
    ("ICG_X1_SVT",    1.0, 1.0, "CORE", 2, False),
    ("FILL_8",        0.8, 1.0, "CORE", 0, True),
    ("FILL_16",       1.6, 1.0, "CORE", 0, True),
    ("TAP_1",         0.4, 1.0, "CORE", 0, True),
    ("DCAP_4",        0.8, 1.0, "CORE", 0, True),
    ("SRAM_512",     16.0, 8.0, "BLOCK", 0, False),
]
SIZE = {name: (w, h) for name, w, h, _c, _wt, _p in CELLS}
KLASS = {name: c for name, _w, _h, c, _wt, _p in CELLS}
AREA_ONLY = {name for name, _w, _h, _c, _wt, p in CELLS if p}
STD_POOL = [name for name, _w, _h, _c, weight, _p in CELLS for _ in range(weight)]

# ---------------------------------------------------------------------------
# Floorplan
# ---------------------------------------------------------------------------
MARGIN = 6.0            # die margin
CHANNEL = 4.0           # routing channel between blocks
BLOCK_W = 34.0          # sub-block width
ROW_UTIL = 0.80         # std-cell fill per row; filler takes up the rest
SITE = 0.2              # standard-cell site grid
N_UNITS = 2
N_SUB = 3
STD_PER_BLOCK = 620
SRAM = "SRAM_512"
SRAM_W, SRAM_H = SIZE[SRAM]
UNITS_PER_MICRON = 1000  # DEF UNITS DISTANCE MICRONS


def _activity(x, y):
    """Smooth 2-D activity field in [0, 1] - dense datapath vs sparse control.

    The same idea as sample_data/physical: a constant row fill would make every bin
    read exactly 1.0 and the heat map would be solid rectangles.
    """
    value = (0.72
             + 0.14 * math.sin(x / 9.0 + 0.4)
             + 0.12 * math.sin(y / 7.0 + 1.1)
             + 0.08 * math.sin((x + y) / 5.0 + 2.3))
    return min(1.0, max(0.0, value))


def _util(x, y):
    """Target std-cell fill at (x, y): ~0.42 where the field is sparsest, ~0.95 densest."""
    return min(0.95, max(0.42, 0.25 + 0.72 * _activity(x, y)))


def _layout_block(cells, rng):
    """Rows of ``(name, x)`` for one sub-block, in build order.

    Std cells advance left-to-right and each cell pays off its share of whitespace as
    site-sized holes, so the holes stay spread out rather than piling into one stripe.
    Filler then completes each row out to ``BLOCK_W``, as a filler step would. The
    cursor only ever moves forward, so nothing overlaps.
    """
    limit = BLOCK_W * ROW_UTIL

    def start_row(index):
        """A fresh row's cells and cursor: alternate rows begin with a tap cell."""
        if index % 2 == 0:
            return [("TAP_1", 0.0)], SIZE["TAP_1"][0]
        return [], 0.0

    rows, row, x, owed, y = [], [], 0.0, 0.0, 0
    row, x = start_row(y)
    for name in cells:
        width = SIZE[name][0]
        if x + width > limit:
            rows.append(row)
            y += 1
            row, x, owed = *start_row(y), 0.0
        row.append((name, round(x, 3)))
        x += width
        owed += (1.0 - _util(x, y)) * width
        sites = int(owed / SITE)
        if sites > 0:
            sites = max(1, sites + rng.choice((-1, 0, 0, 1)))
            x += sites * SITE
            owed -= sites * SITE
    rows.append(row)

    for row in rows:
        x = row[-1][1] + SIZE[row[-1][0]][0]
        if BLOCK_W - x >= SIZE["DCAP_4"][0]:
            row.append(("DCAP_4", round(x, 3)))     # decaps sit among the filler
            x += SIZE["DCAP_4"][0]
        while True:
            remaining = BLOCK_W - x
            if remaining >= SIZE["FILL_16"][0]:
                name = "FILL_16"
            elif remaining >= SIZE["FILL_8"][0]:
                name = "FILL_8"
            else:
                break
            row.append((name, round(x, 3)))
            x += SIZE[name][0]
    return rows


def build():
    """Return (placements, rows, die) - all coordinates in microns."""
    rng = random.Random(0)
    cells = [rng.choice(STD_POOL) for _ in range(STD_PER_BLOCK)]
    rows = _layout_block(cells, rng)
    block_h = float(len(rows))

    blocks_w = N_SUB * BLOCK_W + (N_SUB - 1) * CHANNEL
    blocks_h = N_UNITS * block_h + (N_UNITS - 1) * CHANNEL
    die_w = blocks_w + 2 * MARGIN
    die_h = MARGIN + blocks_h + CHANNEL + SRAM_H + MARGIN

    placements = []
    for unit in range(N_UNITS):
        for sub in range(N_SUB):
            bx = MARGIN + sub * (BLOCK_W + CHANNEL)
            by = MARGIN + (N_UNITS - 1 - unit) * (block_h + CHANNEL)
            for r, row in enumerate(rows):
                # Alternating N / FN per row is the usual row-mirroring convention.
                orient = "N" if r % 2 == 0 else "FN"
                for c, (name, x) in enumerate(row):
                    # Leaf names depend only on row/column, so all six blocks share
                    # one set of names - which lets one verilog module describe them.
                    placements.append((f"u{unit}/b{sub}/{name.lower()}_{r * 1000 + c}",
                                       name, bx + x, by + r, orient))

    smem_y = MARGIN + blocks_h + CHANNEL
    for k in range(4):
        placements.append((f"smem_{k}", SRAM, MARGIN + k * (SRAM_W + CHANNEL),
                           smem_y, "N"))
    return placements, rows, (die_w, die_h)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_lef(path):
    lines = ["# Sample macro LEF generated by generate_eda_sample.py",
             "VERSION 5.8 ;", 'BUSBITCHARS "[]" ;', 'DIVIDERCHAR "/" ;', ""]
    for name, width, height, klass, _weight, _physical in CELLS:
        lines += [f"MACRO {name}",
                  f"  CLASS {klass} ;",
                  "  ORIGIN 0 0 ;",
                  f"  SIZE {width} BY {height} ;",
                  "  SYMMETRY X Y ;",
                  f"END {name}", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(CELLS)


def write_def(path, placements, die):
    dbu = UNITS_PER_MICRON
    # round(), not int(): a micron value like 64.6 is 64.59999999999999 in binary, so
    # truncating would emit 64599 instead of 64600 and leave a 0.001 micron overlap
    # between neighbours that touch exactly.
    def dbu_of(microns):
        return int(round(microns * dbu))

    header = [
        "# Sample DEF generated by generate_eda_sample.py",
        "VERSION 5.8 ;",
        'DIVIDERCHAR "/" ;',
        'BUSBITCHARS "[]" ;',
        "DESIGN core ;",
        f"UNITS DISTANCE MICRONS {dbu} ;",
        f"DIEAREA ( 0 0 ) ( {dbu_of(die[0])} {dbu_of(die[1])} ) ;",
        f"COMPONENTS {len(placements)} ;",
    ]
    body = [f"- {name} {cell} + SOURCE DIST + PLACED ( {dbu_of(x)} {dbu_of(y)} ) "
            f"{orient} ;" for name, cell, x, y, orient in placements]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header + body + ["END COMPONENTS", "", "END DESIGN"]) + "\n")


def write_verilog(path, rows):
    """Gate-level netlist: same hierarchy and instance names as the DEF, but no
    placement, and none of the physical-only cells (a netlist has no filler/tap)."""
    out = ["// Sample gate-level netlist generated by generate_eda_sample.py",
           "module sub_blk (a, y);", "  input a;", "  output y;"]
    for r, row in enumerate(rows):
        for c, (name, _x) in enumerate(row):
            if name in AREA_ONLY:
                continue
            out.append(f"  {name} {name.lower()}_{r * 1000 + c} (.A(a), .Y(y));")
    out += ["endmodule", "",
            "module unit_blk (a, y);", "  input a;", "  output y;"]
    for sub in range(N_SUB):
        out.append(f"  sub_blk b{sub} (.a(a), .y(y));")
    out += ["endmodule", "",
            "module core (a, y);", "  input a;", "  output y;"]
    for unit in range(N_UNITS):
        out.append(f"  unit_blk u{unit} (.a(a), .y(y));")
    for k in range(4):
        out.append(f"  SRAM_512 smem_{k} (.A(a), .Y(y));")
    out += ["endmodule"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def verify():
    """Re-parse the generated files through the converters, then the real loaders."""
    import json
    import tempfile

    from vlsi_viewer import schema
    from vlsi_viewer.loader import load_block, load_cell_info
    from vlsi_viewer.parsers.convert import (cell_info_from_lef, instance_info_from_def,
                                             instance_info_from_verilog)
    from vlsi_viewer.physical import build_physical

    lef = os.path.join(HERE, "cells.lef")
    def_file = os.path.join(HERE, "core.def")
    v_file = os.path.join(HERE, "core.v")

    cells = cell_info_from_lef([lef])
    assert all(set(a) == {s.name for s in schema.CELL_ATTRS} for a in cells.values())
    # The name heuristics must agree with this file's own statement of which cells are
    # area-only, and CLASS BLOCK must be what makes a cell a macro.
    for name, attrs in cells.items():
        assert attrs["is_physical_only"] == (name in AREA_ONLY), name
        assert attrs["is_macro"] == (KLASS[name] != "CORE"), name
    print(f"  verify: {len(cells)} LEF macro(s); physical-only "
          f"{', '.join(sorted(AREA_ONLY))}")

    block = instance_info_from_def(def_file)
    assert block["boundary"], "DEF produced no boundary"
    kept = {i["cell_name"] for i in block["instances"].values()}
    assert not (kept & {"FILL_8", "FILL_16"}), "filler should have been dropped"
    orients = sorted({i["orient"] for i in block["instances"].values()})
    print(f"  verify: DEF -> {len(block['instances'])} instances "
          f"({len(build()[0])} components less filler), orients {orients}")

    netlist = instance_info_from_verilog(v_file, "core")
    assert "boundary" not in netlist, "a netlist has no placement"
    assert not ({i["cell_name"] for i in netlist["instances"].values()} & AREA_ONLY), \
        "a netlist should not contain physical-only cells"
    print(f"  verify: verilog -> {len(netlist['instances'])} instances (logic only)")

    with tempfile.TemporaryDirectory() as tmp:
        cpath = os.path.join(tmp, "cell_info.json")
        bpath = os.path.join(tmp, "instance_info.json")
        with open(cpath, "w", encoding="utf-8") as fh:
            json.dump(cells, fh)
        with open(bpath, "w", encoding="utf-8") as fh:
            json.dump(block, fh)
        name, df, boundary = load_block(bpath)
        load_cell_info(cpath)
        pd_ = build_physical([bpath], cpath, grid_size=2.0)
        dens = pd_.heat("density")
        occupied = dens[dens > 0]
        mid = 100 * ((occupied >= 0.2) & (occupied <= 0.95)).mean()
        print(f"  verify: load_block -> {name!r}, {len(df)} loaded instance(s), "
              f"boundary {boundary is not None}")
        print(f"  verify: physical grid {pd_.rows}x{pd_.cols}, density max "
              f"{dens.max():.3f}, {mid:.0f}% of occupied bins mid-range")
        assert mid > 40, f"density map is not a utilisation field ({mid:.0f}% mid-range)"
    print("  verify: OK")


def main():
    placements, rows, die = build()
    write_lef(os.path.join(HERE, "cells.lef"))
    write_def(os.path.join(HERE, "core.def"), placements, die)
    write_verilog(os.path.join(HERE, "core.v"), rows)

    filler = sum(1 for _n, cell, _x, _y, _o in placements if cell.startswith("FILL"))
    print("wrote EDA sample:")
    print("  files: cells.lef core.def core.v")
    print(f"  components     : {len(placements)} "
          f"({len(placements) - filler} kept + {filler} filler)")
    print(f"  blocks         : {N_UNITS} units x {N_SUB} sub-blocks, {len(rows)} rows each")
    print(f"  die            : {die[0]:.0f} x {die[1]:.0f} microns")
    verify()


if __name__ == "__main__":
    main()
