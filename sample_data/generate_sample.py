"""Generate a realistic demo netlist (~100k instances, 6 hierarchy levels).

Run:  python sample_data/generate_sample.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Realistic standard-cell library (varied VT, drive, function) + macros.
CELLS = {
    "INV_X1_SVT": {"area": 0.6, "is_inverter": True, "drive_size": 1, "is_SVT": True},
    "INV_X2_LVT": {"area": 1.0, "is_inverter": True, "drive_size": 2, "is_LVT": True},
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
}

STD_WEIGHTS = [
    ("INV_X1_SVT", 10), ("INV_X2_LVT", 8), ("INV_X4_ULVT", 6), ("INV_X8_SVT", 4),
    ("BUF_X2_LVT", 8), ("BUF_X4_ULVT", 6), ("BUF_X8_SVT", 4),
    ("AND2_X1", 6), ("OR2_X1", 6), ("NAND2_X2", 6), ("XOR2_X2", 4), ("MUX2_X1", 6),
    ("DFF_X1", 10), ("DFF_X2", 6), ("DFF_X4", 4),
    ("CLKBUF_X2", 4), ("CLKINV_X2", 4), ("ICG_X1", 2),
]
STD_POOL = [name for name, w in STD_WEIGHTS for _ in range(w)]

MACROS = ["SRAM", "PLL", "ADC"]

N_BLOCKS = 10
N_SUB = 4
N_UNIT = 4
N_GRP = 4
N_CLS = 4
LEAVES_PER_CLS = 40


def _pick_std(index):
    # deterministic multiplicative-hash so the distribution is spread, not cyclical
    return STD_POOL[(index * 2654435761) % len(STD_POOL)]


def main():
    instances = {}
    counter = 0
    for b in range(N_BLOCKS):
        block = f"TOP/BLK_{b}"
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
                            instances[f"{cls}/leaf_{i}"] = {"cell_name": _pick_std(counter)}
                            counter += 1

    instances["TOP/top_macro"] = {"cell_name": "PLL"}

    with open(os.path.join(HERE, "instance_info.json"), "w") as f:
        json.dump(instances, f)
    with open(os.path.join(HERE, "cell_info.json"), "w") as f:
        json.dump(CELLS, f, indent=2)

    print(f"wrote {len(instances)} instances")


if __name__ == "__main__":
    main()
