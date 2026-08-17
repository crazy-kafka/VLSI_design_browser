import json
import logging

from vlsi_viewer.metrics import build_design, load_blocks


def _block(tmp_path, name, instances):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps({"top_name": name, "instances": instances}))
    return str(p)


def test_single_block_relative_paths(tmp_path):
    df = load_blocks([_block(tmp_path, "TOP", {"a/leaf": {"cell_name": "C1"}})])
    assert df["leaf_instance_name"].tolist() == ["TOP/a/leaf"]


def test_subblock_nested_under_parent(tmp_path):
    parent = _block(tmp_path, "block_A", {
        "UNIT/leaf1": {"cell_name": "C1"},
        "block_B": {"cell_name": "block_B"},
    })
    child = _block(tmp_path, "block_B", {
        "SUB/leaf2": {"cell_name": "C1"},
    })
    df = load_blocks([parent, child])
    paths = sorted(df["leaf_instance_name"].tolist())
    assert paths == ["block_A/UNIT/leaf1", "block_A/block_B/SUB/leaf2"]


def test_top_level_auto_detection(tmp_path):
    # A references B (so B is nested); C references nothing (independent top).
    a = _block(tmp_path, "A", {"b": {"cell_name": "B"}})
    b = _block(tmp_path, "B", {"leaf": {"cell_name": "C1"}})
    c = _block(tmp_path, "C", {"leaf": {"cell_name": "C1"}})
    df = load_blocks([a, b, c])
    paths = sorted(df["leaf_instance_name"].tolist())
    assert "A/b/leaf" in paths      # B nested under A
    assert "C/leaf" in paths        # C is its own top-level
    assert "B/leaf" not in paths    # B is not a top-level


def test_unresolved_reference_stays_leaf(tmp_path):
    parent = _block(tmp_path, "A", {"block_C": {"cell_name": "block_C"}})
    df = load_blocks([parent])
    assert df["leaf_instance_name"].tolist() == ["A/block_C"]


def test_cyclic_reference_warns(tmp_path, caplog):
    a = _block(tmp_path, "A", {"b": {"cell_name": "B"}})
    b = _block(tmp_path, "B", {"a": {"cell_name": "A"}})
    with caplog.at_level(logging.WARNING):
        load_blocks([a, b])
    assert "cyclic" in caplog.text


def test_build_design_with_nested_block(tmp_path):
    cell = tmp_path / "cell.json"
    cell.write_text(json.dumps({"C1": {"area": 1.0}}))
    parent = _block(tmp_path, "TOP", {"block_B": {"cell_name": "block_B"}})
    child = _block(tmp_path, "block_B", {"SUB/leaf": {"cell_name": "C1"}})
    d = build_design([parent, child], str(cell))
    assert "TOP/block_B/SUB" in d.hier.index
    assert d.hier.loc["TOP/block_B/SUB", "count"] == 1
