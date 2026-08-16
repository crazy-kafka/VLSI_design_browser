import json
import os

import pytest

from vlsi_viewer.metrics import build_design

# Small hand-verifiable netlist used by the unit tests.
INSTANCE_INFO = {
    "TOP/MACROA/UNIT1/inv_a": {"cell_name": "INV_X1"},
    "TOP/MACROA/UNIT1/buf_a": {"cell_name": "BUF_X1"},
    "TOP/MACROA/UNIT1/dff_a": {"cell_name": "DFF_X2"},
    "TOP/MACROA/UNIT1/dff_b": {"cell_name": "DFF_X1"},
    "TOP/UNIT2/and_a": {"cell_name": "AND_X1"},
    "TOP/UNIT2/sram_a": {"cell_name": "SRAM"},
    "TOP/tap_a": {"cell_name": "TAP", "is_physical_only": True},
    "TOP/MACROA/UNIT1/missing_a": {"cell_name": "UNKNOWN"},
}

CELL_INFO = {
    "INV_X1": {"area": 1.0, "is_inverter": True, "drive_size": 1, "is_SVT": True},
    "BUF_X1": {"area": 2.0, "is_buffer": True, "drive_size": 2, "is_LVT": True},
    "DFF_X2": {"area": 3.0, "is_register_cell": True, "register_bit_count": 2, "drive_size": 4, "is_ULVT": True},
    "DFF_X1": {"area": 4.0, "is_register_cell": True, "register_bit_count": 1, "drive_size": 4, "is_ULVT": True},
    "AND_X1": {"area": 1.5, "is_combinational_cell": True, "drive_size": 3, "is_SVT": True},
    "SRAM": {"area": 100.0, "is_macro": True, "is_sram": True},
    "TAP": {"area": 0.5},
}


@pytest.fixture
def sample_dir(tmp_path):
    (tmp_path / "instance_info.json").write_text(json.dumps(INSTANCE_INFO))
    (tmp_path / "cell_info.json").write_text(json.dumps(CELL_INFO))
    return str(tmp_path)


@pytest.fixture
def design(sample_dir):
    return build_design(
        os.path.join(sample_dir, "instance_info.json"),
        os.path.join(sample_dir, "cell_info.json"),
    )
