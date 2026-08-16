import json
import os

import pandas as pd
import pytest

from vlsi_viewer.loader import load_cell_info, load_instance_info


def test_instance_defaults_and_presence(sample_dir):
    df = load_instance_info(os.path.join(sample_dir, "instance_info.json"))
    df = df.set_index("leaf_instance_name")

    # is_physical_only defaults to False when omitted, True when provided.
    assert df.loc["TOP/MACROA/UNIT1/inv_a", "is_physical_only"] == False
    assert df.loc["TOP/tap_a", "is_physical_only"] == True

    # reserved str attribute defaults to "".
    assert df.loc["TOP/MACROA/UNIT1/inv_a", "orient"] == ""

    # cell_name retained verbatim (including the unknown one).
    assert df.loc["TOP/MACROA/UNIT1/missing_a", "cell_name"] == "UNKNOWN"


def test_cell_defaults_and_types(sample_dir):
    df = load_cell_info(os.path.join(sample_dir, "cell_info.json"))
    df = df.set_index("cell_name")

    assert df.loc["INV_X1", "area"] == 1.0
    assert df.loc["INV_X1", "is_inverter"] == True
    # omitted flags default to False / 0.
    assert df.loc["INV_X1", "is_register_cell"] == False
    assert df.loc["INV_X1", "register_bit_count"] == 0
    # dtypes are coerced per the schema.
    assert df["is_inverter"].dtype == bool
    assert df["register_bit_count"].dtype.kind == "i"
    assert df["area"].dtype.kind == "f"


def test_string_bool_coercion(tmp_path):
    inst = tmp_path / "inst.json"
    inst.write_text(json.dumps({
        "TOP/a": {"cell_name": "C1", "is_physical_only": "true"},
    }))
    df = load_instance_info(str(inst))
    assert df.loc[0, "is_physical_only"] == True

    cell = tmp_path / "cell.json"
    cell.write_text(json.dumps({
        "C1": {"area": "2.5", "is_macro": 1, "register_bit_count": "3"},
    }))
    cdf = load_cell_info(str(cell))
    assert cdf.loc[0, "area"] == 2.5
    assert cdf.loc[0, "is_macro"] == True
    assert cdf.loc[0, "register_bit_count"] == 3
