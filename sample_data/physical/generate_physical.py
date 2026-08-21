"""Generate a realistic physical-mode sample netlist (>100k instances).

Multi-level nested blocks with rect-polygon boundaries, varied orientations,
and per-instance power values. Run: python sample_data/physical/generate_physical.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

CELLS = {
    "INV": {"area": 0.6, "size_x": 1, "size_y": 1, "is_inverter": True, "is_SVT": True},
    "BUF": {"area": 1.2, "size_x": 1, "size_y": 2, "is_buffer": True, "is_LVT": True},
    "DFF": {"area": 5.0, "size_x": 2, "size_y": 1, "is_register_cell": True, "is_ULVT": True},
    "SRAM": {"area": 2000.0, "size_x": 50, "size_y": 40, "is_macro": True, "is_sram": True},
}

ORIENTS = ["N", "S", "W", "E", "FN", "FS", "FW", "FE"]


def _cell(name, i):
    """Deterministic per-instance attrs (orient + power vary)."""
    return {
        "cell_name": name,
        "orient": ORIENTS[(i * 3) % len(ORIENTS)],
        "leakage_power": round(0.05 * (i % 7 + 1), 4),
        "dynamic_power": round(0.3 * (i % 5 + 1), 4),
    }


def _grid_instances(name_base, nx, ny, pitch=1, offset=(0, 0),
                    cell_names=("INV", "BUF", "DFF")):
    """Place a dense grid of instances in a block's local frame."""
    insts = {}
    idx = 0
    ox, oy = offset
    for j in range(ny):
        for i in range(nx):
            insts[f"{name_base}_{j}_{i}"] = dict(
                _cell(cell_names[(i + j) % len(cell_names)], idx),
                location_x=ox + i * pitch, location_y=oy + j * pitch)
            idx += 1
    return insts


def _write(path, data, indent=None):
    with open(os.path.join(HERE, path), "w") as f:
        json.dump(data, f, indent=indent)


def main():
    _write("cell_info.json", CELLS, indent=2)

    # SUB_A: dense 210x210 grid (~44k) in a 220x220 rect boundary
    sub_a = {"top_name": "SUB_A", "boundary": [(0, 0), (220, 220)],
             "instances": _grid_instances("a", 210, 210)}
    # SUB_B: 180x220 (~40k) in a 190x230 rect boundary
    sub_b = {"top_name": "SUB_B", "boundary": [(0, 0), (190, 230)],
             "instances": _grid_instances("b", 180, 220)}
    # SUB_C: 140x180 (~25k)
    sub_c = {"top_name": "SUB_C", "boundary": [(0, 0), (150, 190)],
             "instances": _grid_instances("c", 140, 180)}

    top_instances = {
        # sub-block instances with varied placement + orient
        "sub_A": dict(_cell("SUB_A", 1), location_x=100, location_y=100, orient="N"),
        "sub_B": dict(_cell("SUB_B", 2), location_x=800, location_y=100, orient="W"),
        "sub_C": dict(_cell("SUB_C", 3), location_x=1500, location_y=500, orient="E"),
        # a macro
        "sram": dict(_cell("SRAM", 4), location_x=600, location_y=400, orient="N"),
    }
    # direct cells in the TOP (a 100x50 patch at x in [300,400], y in [600,700])
    top_instances.update(_grid_instances("t", 100, 50, pitch=1, offset=(300, 600)))

    _write("instance_info.json", {
        "top_name": "TOP",
        "boundary": [(0, 0), (2000, 0), (2000, 800), (1200, 800),
                     (1200, 1000), (0, 1000)],  # rect-polygon with a notch
        "instances": top_instances,
    })
    _write("SUB_A.json", sub_a, indent=2)
    _write("SUB_B.json", sub_b, indent=2)
    _write("SUB_C.json", sub_c, indent=2)

    n = sum(len(x["instances"]) for x in (sub_a, sub_b, sub_c)) + len(top_instances)
    print(f"wrote physical sample: {n} instances")


if __name__ == "__main__":
    main()
