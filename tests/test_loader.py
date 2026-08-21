import json
import os

import pytest

from vlsi_viewer.loader import load_block, load_cell_info


def test_load_block_top_and_relative_paths(sample_dir):
    top_name, df, boundary = load_block(os.path.join(sample_dir, "instance_info.json"))
    assert boundary is None
    assert top_name == "TOP"
    df = df.set_index("leaf_instance_name")

    # relative paths (no TOP prefix) + attribute defaulting
    assert df.loc["MACROA/UNIT1/inv_a", "is_physical_only"] == False
    assert df.loc["tap_a", "is_physical_only"] == True
    assert df.loc["MACROA/UNIT1/inv_a", "orient"] == ""
    assert df.loc["MACROA/UNIT1/missing_a", "cell_name"] == "UNKNOWN"


def test_cell_defaults_and_types(sample_dir):
    df = load_cell_info(os.path.join(sample_dir, "cell_info.json"))
    df = df.set_index("cell_name")

    assert df.loc["INV_X1", "area"] == 1.0
    assert df.loc["INV_X1", "is_inverter"] == True
    assert df.loc["INV_X1", "is_register_cell"] == False
    assert df.loc["INV_X1", "register_bit_count"] == 0
    assert df["is_inverter"].dtype == bool
    assert df["register_bit_count"].dtype.kind == "i"
    assert df["area"].dtype.kind == "f"


def test_string_bool_coercion(tmp_path):
    inst = tmp_path / "inst.json"
    inst.write_text(json.dumps({
        "top_name": "TOP",
        "instances": {"a": {"cell_name": "C1", "is_physical_only": "true"}},
    }))
    top_name, df, _ = load_block(str(inst))
    assert top_name == "TOP"
    assert df.loc[0, "is_physical_only"] == True

    cell = tmp_path / "cell.json"
    cell.write_text(json.dumps({
        "C1": {"area": "2.5", "is_macro": 1, "register_bit_count": "3"},
    }))
    cdf = load_cell_info(str(cell))
    assert cdf.loc[0, "area"] == 2.5
    assert cdf.loc[0, "is_macro"] == True
    assert cdf.loc[0, "register_bit_count"] == 3


def test_load_block_boundary_two_points(tmp_path):
    inst = tmp_path / "b.json"
    inst.write_text(json.dumps({
        "top_name": "T", "instances": {},
        "boundary": [(0, 0), (10, 20)],
    }))
    _, _, boundary = load_block(str(inst))
    assert boundary == [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0)]


def test_load_block_boundary_rectilinear_polygon(tmp_path):
    inst = tmp_path / "b.json"
    inst.write_text(json.dumps({
        "top_name": "T", "instances": {},
        "boundary": [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)],
    }))
    _, _, boundary = load_block(str(inst))
    assert boundary == [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (5.0, 5.0), (5.0, 10.0), (0.0, 10.0)]


def test_load_block_boundary_invalid(tmp_path):
    inst = tmp_path / "b.json"
    # non-axis-aligned edge -> must raise
    inst.write_text(json.dumps({
        "top_name": "T", "instances": {},
        "boundary": [(0, 0), (10, 0), (10, 10), (2, 3)],
    }))
    with pytest.raises(ValueError):
        load_block(str(inst))
