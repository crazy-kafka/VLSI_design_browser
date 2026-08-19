"""Generate a realistic demo netlist (~100k instances, 6 levels) + a sub-block.

The standard-cell mix varies per block so the ratio metrics (ULVT%, MB%, D1D2%)
span a wide range and the quality gradient shows red->yellow->green variety.

Run:  python sample_data/generate_sample.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

CELLS = {
    "INV_X1_SVT": {"area": 0.6, "is_inverter": True, "drive_size": 1, "is_SVT": True},
    "INV_X2_LVT": {"area": 1.0, "is_inverter": True, "drive_size": 2, "is_LVT": True},
    "INV_X1_ULVT": {"area": 0.7, "is_inverter": True, "drive_size": 1, "is_ULVT": True},
    "INV_X4_ULVT": {"area": 1.8, "is_inverter": True, "drive_size": 4, "is_ULVT": True},
    "INV_X8_SVT": {"area": 3.2, "is_inverter": True, "drive_size": 8, "is_SVT": True},
    "BUF_X2_LVT": {"area": 1.2, "is_buffer": True, "drive_size": 2, "is_LVT": True},
    "BUF_X4_ULVT": {"area": 2.0, "is_buffer": True, "drive_size": 4, "is_ULVT": True},
    "BUF_X8_SVT": {"area": 3.6, "is_buffer": True, "drive_size": 8, "is_SVT": True},
    "AND2_X1": {"area": 1.5, "is_combinational_cell": True, "drive_size": 3, "is_SVT": True},
    "OR2_X1": {"area": 1.5, "is_combinational_cell": True, "drive_size": 3, "is_LVT": True},
    "NAND2_X2": {"area": 1.8, "is_combinational_cell": True, "drive_size": 4, "is_ULVT": True},
    "XOR2_X2": {"area": 2.4, "is_combinational_cell": True, "drive_size": 4, "is_LVT": True},
    "MUX2_X1": {"area": 2.0, "is_combinational_cell": True, "drive_size": 3, "is_SVT": True},
    "DFF_X1": {"area": 5.0, "is_register_cell": True, "register_bit_count": 1, "drive_size": 6, "is_SVT": True},
    "DFF_X2": {"area": 8.0, "is_register_cell": True, "register_bit_count": 2, "drive_size": 6, "is_LVT": True},
    "DFF_X4": {"area": 12.0, "is_register_cell": True, "register_bit_count": 4, "drive_size": 8, "is_ULVT": True},
    "CLKBUF_X2": {"area": 1.4, "is_clock_cell": True, "is_buffer": True, "drive_size": 2, "is_LVT": True},
    "CLKINV_X2": {"area": 1.3, "is_clock_cell": True, "is_inverter": True, "drive_size": 2, "is_LVT": True},
    "ICG_X1": {"area": 3.0, "is_integrated_clock_gating_cell": True, "is_clock_cell": True,
               "drive_size": 4, "is_LVT": True},
    "SRAM": {"area": 5000.0, "is_macro": True, "is_sram": True},
    "PLL": {"area": 8000.0, "is_macro": True},
    "ADC": {"area": 12000.0, "is_macro": True},
    "block_B": {"area": 5000.0, "is_macro": True},
}

# (name, is_ULVT, drive_size <= 2) for non-register cells.
_NONREG = [
    ("INV_X1_SVT", False, True), ("INV_X2_LVT", False, True), ("INV_X1_ULVT", True, True),
    ("INV_X4_ULVT", True, False), ("INV_X8_SVT", False, False),
    ("BUF_X2_LVT", False, True), ("BUF_X4_ULVT", True, False), ("BUF_X8_SVT", False, False),
    ("AND2_X1", False, False), ("OR2_X1", False, False), ("NAND2_X2", True, False),
    ("XOR2_X2", False, False), ("MUX2_X1", False, False),
    ("CLKBUF_X2", False, True), ("CLKINV_X2", False, True), ("ICG_X1", False, False),
]

MACROS = ["SRAM", "PLL", "ADC"]

N_BLOCKS = 10
N_SUB = 4
N_UNIT = 4
N_GRP = 4
N_CLS = 4
LEAVES_PER_CLS = 40


def _make_pool(ulvt, mb, d1d2):
    """Build a weighted cell pool (flat list) for recipe fractions in [0, 1]."""
    pool = []

    def add(name, frac):
        pool.extend([name] * max(1, int(frac * 120)))

    add("DFF_X1", (1 - mb) * 0.22)
    add("DFF_X2", mb * (1 - ulvt) * 0.22)
    add("DFF_X4", mb * ulvt * 0.22)
    for name, is_ulvt, is_d1d2 in _NONREG:
        p = 0.78 / len(_NONREG)
        p *= (ulvt * 3 + 0.15) if is_ulvt else ((1 - ulvt) * 3 + 0.15)
        p *= (d1d2 * 3 + 0.15) if is_d1d2 else ((1 - d1d2) * 3 + 0.15)
        add(name, p)
    return pool


def _write(path, data, indent=None):
    with open(os.path.join(HERE, path), "w") as f:
        json.dump(data, f, indent=indent)


def _pools(version):
    """Per-block (ulvt, mb, d1d2) recipes; v2 is a perturbed variant for compare."""
    pools = []
    for b in range(N_BLOCKS):
        t = b / (N_BLOCKS - 1)
        if version == "v1":
            ulvt, mb, d1d2 = t, ((b * 3) % N_BLOCKS) / (N_BLOCKS - 1), ((b * 7) % N_BLOCKS) / (N_BLOCKS - 1)
        else:  # v2: shift ratios so the diff gradient shows variety
            ulvt = min(1.0, t * 1.6 + 0.05)
            mb = min(1.0, (((b * 3 + 2) % N_BLOCKS) / (N_BLOCKS - 1)) * 0.85)
            d1d2 = min(1.0, (((b * 7 + 5) % N_BLOCKS) / (N_BLOCKS - 1)) * 1.25)
        pools.append(_make_pool(ulvt, mb, d1d2))
    return pools


def _build_top(pools, drop_every=None):
    instances = {}
    counter = 0
    for b in range(N_BLOCKS):
        block = f"BLK_{b}"
        pool = pools[b]
        for s in range(N_SUB):
            sub = f"{block}/SUB_{s}"
            instances[f"{sub}/macro"] = {"cell_name": MACROS[s % len(MACROS)]}
            for u in range(N_UNIT):
                unit = f"{sub}/UNIT_{u}"
                for g in range(N_GRP):
                    grp = f"{unit}/GRP_{g}"
                    for c in range(N_CLS):
                        cls = f"{grp}/CLS_{c}"
                        for i in range(LEAVES_PER_CLS):
                            if drop_every is not None and counter % drop_every == 0:
                                counter += 1
                                continue
                            instances[f"{cls}/leaf_{i}"] = {"cell_name": pool[counter % len(pool)]}
                            counter += 1

    instances["block_B"] = {"cell_name": "block_B"}
    instances["top_macro"] = {"cell_name": "PLL"}
    return instances


def _build_block_b(version):
    block_b = {}
    for u in range(2):
        for i in range(10):
            if version == "v1":
                cell = "INV_X1_SVT" if (i + u) % 3 == 0 else "DFF_X2"
            else:
                cell = "DFF_X2" if (i + u) % 3 == 0 else "AND2_X1"
            block_b[f"UNIT_{u}/leaf_{i}"] = {"cell_name": cell}
    return block_b


def main():
    _write("cell_info.json", CELLS, indent=2)

    v1 = _build_top(_pools("v1"))
    _write("instance_info.json", {"top_name": "TOP", "instances": v1})
    _write("block_B.instance_info.json",
           {"top_name": "block_B", "instances": _build_block_b("v1")}, indent=2)

    # compare (v2): perturbed ratios + ~4% fewer leaves
    v2 = _build_top(_pools("v2"), drop_every=25)
    _write("instance_info_v2.json", {"top_name": "TOP", "instances": v2})
    _write("block_B.instance_info_v2.json",
           {"top_name": "block_B", "instances": _build_block_b("v2")}, indent=2)

    print(f"wrote v1: {len(v1)} instances, v2: {len(v2)} instances "
          f"(same cell_info.json)")


if __name__ == "__main__":
    main()
