"""The vendored LEF / DEF / Verilog parsers and their conversion to viewer JSON.

The parsers were written for another project and imported three names from a root
``utils`` module this repo never had, so none of them were importable. The first test
guards the relocation and those imports; the rest cover the converters, using the
committed ``sample_data/eda`` sample for the happy path and inline files for the
parser quirks that the converters have to defend against.
"""
import json
import logging

import pytest

from vlsi_viewer import schema
from vlsi_viewer.parsers.convert import (cell_info_from_lef, instance_info_from_def,
                                         instance_info_from_verilog)

SAMPLE = "sample_data/eda"

# Minimal DEF: one placed component. The parser's coordinate regex needs whitespace
# *inside* the parens - "( 100 200 )", not "(100 200)".
DEF_HEAD = f"""DESIGN tiny ;
UNITS DISTANCE MICRONS {{dbu}} ;
DIEAREA ( 0 0 ) ( 4000 4000 ) ;
COMPONENTS {{n}} ;
{{body}}END COMPONENTS
END DESIGN
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


# -- Phase 2: the parsers must import at all --------------------------------------

def test_parsers_are_importable():
    from vlsi_viewer.parsers import (DefParser, InstExtractor, LefParser,
                                     TlefParser, VerilogParser)
    for cls in (DefParser, LefParser, TlefParser, VerilogParser, InstExtractor):
        assert isinstance(cls, type), cls


# -- LEF -> cell_info.json --------------------------------------------------------

def test_lef_cell_info_shape_and_sizes():
    cells = cell_info_from_lef([f"{SAMPLE}/cells.lef"])
    assert cells
    for name, attrs in cells.items():
        assert set(attrs) == {spec.name for spec in schema.CELL_ATTRS}, name
    assert cells["INV_X1_SVT"]["size_x"] == pytest.approx(0.4)
    assert cells["INV_X1_SVT"]["size_y"] == pytest.approx(1.0)
    assert cells["INV_X1_SVT"]["area"] == pytest.approx(0.4)
    assert cells["SRAM_512"]["size_x"] == pytest.approx(16.0)
    assert cells["SRAM_512"]["area"] == pytest.approx(128.0)


def test_lef_cell_info_flags():
    """is_macro comes from LEF CLASS, and filler/tap/DCAP are flagged area-only."""
    cells = cell_info_from_lef([f"{SAMPLE}/cells.lef"])
    # LEF CLASS BLOCK -> macro (not extractCellInfo.py's `drive_size != 0` rule)
    assert cells["SRAM_512"]["is_macro"] is True
    assert cells["SRAM_512"]["is_sram"] is True
    assert cells["INV_X1_SVT"]["is_macro"] is False

    for name in ("FILL_8", "FILL_16", "TAP_1", "DCAP_4"):
        assert cells[name]["is_physical_only"] is True, name
        assert cells[name]["is_macro"] is False, name
    assert cells["INV_X1_SVT"]["is_physical_only"] is False

    # Vt suffixes, checked ULVT-first so "..._ULVT" is not read as LVT
    assert cells["XOR2_X1_ULVT"]["is_ULVT"] is True
    assert cells["NOR2_X1_LVT"]["is_LVT"] is True
    assert cells["INV_X1_SVT"]["is_SVT"] is True
    assert cells["XOR2_X1_ULVT"]["is_LVT"] is False

    # registers: SDF marks a flop, MB<n> carries the multi-bit count
    assert cells["SDF_X1_SVT"]["is_register_cell"] is True
    assert cells["SDF_X2_LVT"]["register_bit_count"] == 1
    assert cells["MB4_SDF_ULVT"]["register_bit_count"] == 4
    assert cells["MB4_SDF_ULVT"]["is_combinational_cell"] is False
    # drive strength from the _X<n> suffix
    assert cells["INV_X2_LVT"]["drive_size"] == 2
    assert cells["SDF_X2_LVT"]["drive_size"] == 2


def test_lef_unterminated_macro_raises(tmp_path):
    """A MACRO without END runs the parser's cursor off the end (IndexError).

    Documented rather than fixed: the parser is vendored as-is, and this at least fails
    loudly instead of silently dropping the library.
    """
    lef = _write(tmp_path, "bad.lef", "MACRO C1\n  SIZE 1.0 BY 1.0 ;\n")
    with pytest.raises(IndexError):
        cell_info_from_lef([lef])


# -- Verilog -> instance_info.json ------------------------------------------------

def test_verilog_instance_info():
    block = instance_info_from_verilog(f"{SAMPLE}/core.v", "core")
    assert block["top_name"] == "core"
    assert "boundary" not in block, "a netlist carries no placement"
    inst = block["instances"]
    assert inst, "no instances extracted"
    # hierarchy is flattened to instance-name paths
    assert any(p.startswith("u0/b0/") for p in inst), sorted(inst)[:5]
    assert any(p.startswith("u1/b2/") for p in inst)
    # macros are leaves at the top level
    assert inst["smem_0"] == {"cell_name": "SRAM_512"}
    # a gate-level netlist has no filler/tap/decap cells
    assert not {i["cell_name"] for i in inst.values()} & {"FILL_8", "FILL_16", "TAP_1",
                                                          "DCAP_4"}


def test_verilog_unknown_top_raises():
    with pytest.raises(KeyError):
        instance_info_from_verilog(f"{SAMPLE}/core.v", "not_a_module")


# -- DEF -> instance_info.json ----------------------------------------------------

def test_def_instance_info():
    block = instance_info_from_def(f"{SAMPLE}/core.def")
    assert block["top_name"] == "core"           # from the DEF DESIGN name
    assert len(block["boundary"]) == 4
    # DIEAREA is 4000x4000 DB units at 1000 per micron
    xs = [p[0] for p in block["boundary"]]
    assert max(xs) == pytest.approx(122.0)

    inst = block["instances"]
    assert inst
    assert not {i["cell_name"] for i in inst.values() if i["cell_name"].startswith("FILL")}, \
        "filler must be dropped: it tiles every row gap and would peg density at 100%"
    # physical-only cells that are NOT filler are kept, and carry no power data
    assert "TAP_1" in {i["cell_name"] for i in inst.values()}
    for entry in inst.values():
        assert "leakage_power" not in entry and "dynamic_power" not in entry
        assert entry["orient"] in ("N", "S", "W", "E", "FN", "FS", "FW", "FE")
        assert entry["location_x"] >= 0.0 and entry["location_y"] >= 0.0


def test_def_coordinates_are_divided_by_db_unit(tmp_path):
    """A DEF at 2000 DB units per micron must not be scaled as if it were 1000."""
    body = "- u1 C1 + PLACED ( 1000 2000 ) N ;\n"
    path = _write(tmp_path, "u2000.def",
                  DEF_HEAD.format(dbu=2000, n=1, body=body))
    block = instance_info_from_def(path)
    assert block["instances"]["u1"]["location_x"] == pytest.approx(0.5)
    assert block["instances"]["u1"]["location_y"] == pytest.approx(1.0)


def test_def_without_units_warns(tmp_path, caplog):
    """A missing UNITS statement leaves the parser's 2000 default silent."""
    text = DEF_HEAD.format(dbu=1000, n=1, body="- u1 C1 + PLACED ( 1000 0 ) N ;\n")
    text = "\n".join(line for line in text.splitlines() if not line.startswith("UNITS"))
    path = _write(tmp_path, "nounits.def", text + "\n")
    with caplog.at_level(logging.WARNING, logger="vlsi_viewer.parsers.convert"):
        instance_info_from_def(path)
    assert any("UNITS DISTANCE MICRONS" in r.message for r in caplog.records)
    # and the scale really is the 2000 default, which is why the warning matters
    assert instance_info_from_def(path)["instances"]["u1"]["location_x"] == pytest.approx(0.5)


def test_def_wrapped_component_warns(tmp_path, caplog):
    """The parser reads one line at a time, so a continued statement is dropped."""
    body = ("- u1 C1 + PLACED ( 100 0 ) N ;\n"
            "- u2 C1\n  + PLACED ( 200 0 ) N ;\n")
    path = _write(tmp_path, "wrapped.def", DEF_HEAD.format(dbu=1000, n=2, body=body))
    with caplog.at_level(logging.WARNING, logger="vlsi_viewer.parsers.convert"):
        block = instance_info_from_def(path)
    assert list(block["instances"]) == ["u1"], "the wrapped component was parsed"
    assert any("component" in r.message and "parsed" in r.message for r in caplog.records)


def test_def_unplaced_is_skipped(tmp_path):
    """UNPLACED components sit at (0, 0) in the parser; shipping them would pile
    every one of them on the die origin."""
    body = ("- u1 C1 + PLACED ( 100 0 ) N ;\n"
            "- u2 C1 + UNPLACED ;\n")
    path = _write(tmp_path, "unplaced.def", DEF_HEAD.format(dbu=1000, n=2, body=body))
    block = instance_info_from_def(path)
    assert list(block["instances"]) == ["u1"]


def test_def_without_design_name_needs_top(tmp_path):
    text = DEF_HEAD.format(dbu=1000, n=1, body="- u1 C1 + PLACED ( 0 0 ) N ;\n")
    text = "\n".join(line for line in text.splitlines() if not line.startswith("DESIGN"))
    path = _write(tmp_path, "noname.def", text + "\n")
    with pytest.raises(ValueError, match="--top"):
        instance_info_from_def(path)
    assert instance_info_from_def(path, top="picked")["top_name"] == "picked"


# -- the generated JSON is ordinary input for the viewer --------------------------

def test_generated_json_round_trips_through_the_loaders(tmp_path):
    """cell_info + instance_info from the sample must load and drive physical mode."""
    from vlsi_viewer.loader import load_block, load_cell_info
    from vlsi_viewer.physical import build_physical

    cells = cell_info_from_lef([f"{SAMPLE}/cells.lef"])
    block = instance_info_from_def(f"{SAMPLE}/core.def")
    cpath = tmp_path / "cell_info.json"
    bpath = tmp_path / "instance_info.json"
    cpath.write_text(json.dumps(cells))
    bpath.write_text(json.dumps(block))

    name, df, boundary = load_block(str(bpath))
    assert name == "core" and boundary is not None
    assert len(df) == len(block["instances"])
    load_cell_info(str(cpath))

    pd_ = build_physical([str(bpath)], str(cpath), grid_size=2.0)
    dens = pd_.heat("density")
    occupied = dens[dens > 0]
    mid = ((occupied >= 0.2) & (occupied <= 0.95)).mean()
    assert mid > 0.4, f"density is not a utilisation field ({mid:.0%} mid-range)"
    # TAP/DCAP are physical-only: in density, out of the hierarchy surfaces
    assert dens.max() <= 1.0 + 1e-9
    assert len(pd_.boxes) == len(block["instances"])
    assert len(pd_.boxes_for("core/u0/b0")) < len(pd_.boxes)
