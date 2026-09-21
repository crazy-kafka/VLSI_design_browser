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
from vlsi_viewer.parsers.convert import (cell_info_from_lef, fill_instances,
                                         instance_info_from_def, instance_info_from_verilog)

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


def test_class_modifiers_are_not_class_names(tmp_path):
    """`CLASS CORE SPACER ;` is a CORE cell - the modifier is not the class.

    Invisible against the sample, which writes plain `CLASS CORE ;`. A real library writes the
    modifiers: Nangate45 has 6 `CORE SPACER`, 1 `CORE ANTENNACELL` and 1 `CORE WELLTAP`, and
    reading those as class names made all 8 into hard macros. A macro takes capacity away from
    the layers it blocks, so the bottom-layer capacity of a 32.7 um block came out 1 % low.

    The grammar is `CORE [FEEDTHRU|TIEHIGH|TIELOW|SPACER|ANTENNACELL|WELLTAP]`, and the same
    applies to `PAD [INPUT|OUTPUT|INOUT|POWER|SPACER|AREAIO]`.
    """
    lef = tmp_path / "mod.lef"
    lef.write_text("""\
MACRO FILL_1
  CLASS CORE SPACER ;
  SIZE 1 BY 2 ;
END FILL_1
MACRO ANT_1
  CLASS CORE ANTENNACELL ;
  SIZE 1 BY 2 ;
END ANT_1
MACRO TAP_1
  CLASS CORE WELLTAP ;
  SIZE 1 BY 2 ;
END TAP_1
MACRO RAM
  CLASS BLOCK ;
  SIZE 8 BY 16 ;
END RAM
MACRO IOPAD_1
  CLASS PAD POWER ;
  SIZE 10 BY 20 ;
END IOPAD_1
""")
    cells = cell_info_from_lef([str(lef)])
    for name in ("FILL_1", "ANT_1", "TAP_1"):
        assert cells[name]["is_macro"] is False, name
    assert cells["RAM"]["is_macro"] is True
    assert cells["IOPAD_1"]["is_macro"] is True     # a pad spacer is still a pad


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


def test_lef_obstructions_are_read_by_layer(tmp_path):
    """``OBS`` geometry, in the macro's own coordinates.

    A hard macro's obstructions are what the metal-density mode uses to decide which layers
    the macro blocks and where, so this is the parse that decides capacity.
    """
    from vlsi_viewer.parsers.LEF import LefParser

    lef = _write(tmp_path, "obs.lef", """\
MACRO RAM
  CLASS BLOCK ;
  SIZE 10 BY 20 ;
  OBS
    LAYER metal1 ;
      RECT 0 0 10 20 ;
      RECT 1.5 -0.5 2.5 3.25 ;
    LAYER metal3 ;
      RECT 0 0 5 5 ;
  END
END RAM
MACRO PLAIN
  CLASS CORE ;
  SIZE 1 BY 1 ;
END PLAIN
""")
    macros = LefParser([lef]).getMacros()
    assert macros["RAM"].obstructions() == {
        "metal1": [(0.0, 0.0, 10.0, 20.0), (1.5, -0.5, 2.5, 3.25)],
        "metal3": [(0.0, 0.0, 5.0, 5.0)],
    }
    # A macro with no OBS reports an empty mapping, not None and not a missing key: the
    # caller has to tell "declares nothing" from "declares geometry".
    assert macros["PLAIN"].obstructions() == {}
    assert macros["RAM"].size() == (10.0, 20.0)


def test_lef_pin_centres_drop_power_and_ground(tmp_path):
    """Pin centres for the pin-density map: one point per pin, rails excluded.

    A rail pin is on every instance of a cell in a row, so counting it would measure the
    row rather than the design. ``USE`` is the authority; the name is the fallback, because
    a library that writes ``USE SIGNAL`` on a VSS pin is not rare.
    """
    from vlsi_viewer.parsers.LEF import LefParser

    lef = _write(tmp_path, "pins.lef", """\
MACRO C1
  SIZE 4 BY 8 ;
  PIN A
    DIRECTION INPUT ;
    USE SIGNAL ;
    PORT
      LAYER metal1 ;
        RECT 0 0 1 1 ;
        RECT 1 3 3 5 ;
    END
  END A
  PIN NC
    DIRECTION INPUT ;
  END NC
  PIN VDD
    DIRECTION INOUT ;
    USE POWER ;
    PORT
      LAYER metal1 ;
        RECT 0 0 4 0.5 ;
    END
  END VDD
  PIN VSS_1
    DIRECTION INOUT ;
    USE SIGNAL ;
    PORT
      LAYER metal1 ;
        RECT 0 7.5 4 8 ;
    END
  END VSS_1
END C1
""")
    cells, pins = cell_info_from_lef([lef], with_pins=True)
    assert set(cells) == {"C1"}
    # A's two rects union to (0,0)-(3,5), so its centre is (1.5, 2.5) - one point for the
    # pin, not one per rectangle. NC declares nothing and the two rails are dropped.
    assert pins == {"C1": [(1.5, 2.5)]}
    # ``shape`` still means the last RECT the pin declared, which other readers rely on.
    assert LefParser([lef]).getMacros()["C1"].pin("A").shape == [(1.0, 3.0), (3.0, 5.0)]


def test_pin_and_obstruction_tables_are_asked_for_one_at_a_time(tmp_path):
    lef = _write(tmp_path, "one.lef", "MACRO C1\n  SIZE 1 BY 1 ;\nEND C1\n")
    with pytest.raises(ValueError):
        cell_info_from_lef([lef], with_obstructions=True, with_pins=True)


def test_a_rect_before_any_layer_belongs_to_no_layer(tmp_path):
    """Nothing in the grammar allows it, and guessing a layer would be worse than dropping it."""
    from vlsi_viewer.parsers.LEF import LefParser

    lef = _write(tmp_path, "early.lef", """\
MACRO RAM
  CLASS BLOCK ;
  SIZE 4 BY 4 ;
  OBS
    RECT 0 0 1 1 ;
    LAYER metal2 ;
      RECT 0 0 4 4 ;
  END
END RAM
""")
    assert LefParser([lef]).getMacros()["RAM"].obstructions() == {"metal2": [(0.0, 0.0, 4.0, 4.0)]}


def test_obstruction_geometry_that_cannot_be_read_is_counted(tmp_path):
    """POLYGON and PATH inside OBS are not modelled. Counted, so a caller can say so rather
    than silently reporting a layer as less obstructed than its LEF declares."""
    from vlsi_viewer.parsers.LEF import LefParser

    lef = _write(tmp_path, "poly.lef", """\
MACRO RAM
  CLASS BLOCK ;
  SIZE 4 BY 4 ;
  OBS
    LAYER metal2 ;
      POLYGON 0 0 4 0 4 4 ;
      RECT 0 0 4 4 ;
  END
END RAM
""")
    parser = LefParser([lef])
    assert parser.getMacros()["RAM"].obstructions() == {"metal2": [(0.0, 0.0, 4.0, 4.0)]}
    assert parser.n_obs_unmodelled == 1


def test_obstructions_are_copied_on_the_way_out(tmp_path):
    """The caller filters this geometry; handing out the parser's own lists would let one
    consumer's edit change what every other consumer sees."""
    from vlsi_viewer.parsers.LEF import LefParser

    lef = _write(tmp_path, "copy.lef", """\
MACRO RAM
  CLASS BLOCK ;
  SIZE 4 BY 4 ;
  OBS
    LAYER metal2 ;
      RECT 0 0 4 4 ;
  END
END RAM
""")
    macro = LefParser([lef]).getMacros()["RAM"]
    handed_out = macro.obstructions()
    handed_out["metal2"].clear()
    handed_out["metal9"] = []
    assert macro.obstructions() == {"metal2": [(0.0, 0.0, 4.0, 4.0)]}


def test_lef_unterminated_macro_is_read_as_far_as_it_goes(tmp_path):
    """A MACRO without END used to run the parser's cursor off the end and raise IndexError.

    The macro walk had no length guard - `while macro_end not in lef_lines[cursor]` - so a
    truncated library crashed rather than being read as far as it went. That guard arrived with
    the `OBS` reader, which has to terminate on a *bare* `END` and therefore has one more way
    to be wrong; the behaviour is now "read what is there", and the macro that was cut short
    keeps the fields it managed to declare.
    """
    lef = _write(tmp_path, "bad.lef", "MACRO C1\n  SIZE 1.0 BY 1.0 ;\n")
    cells = cell_info_from_lef([lef])
    assert cells["C1"]["size_x"] == pytest.approx(1.0)
    assert cells["C1"]["size_y"] == pytest.approx(1.0)


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


# -- compressed inputs, and a netlist split across files ---------------------------

def _gzipped(src, dst):
    """Gzip ``src`` into ``dst`` - compressed EDA inputs are the norm in real flows."""
    import gzip
    with open(src, "rb") as fh_in, gzip.open(dst, "wb") as fh_out:
        fh_out.write(fh_in.read())
    return str(dst)


def test_verilog_gz_matches_plain_text(tmp_path):
    gz = _gzipped(f"{SAMPLE}/core.v", tmp_path / "core.v.gz")
    assert instance_info_from_verilog(gz, "core") == \
        instance_info_from_verilog(f"{SAMPLE}/core.v", "core")


def test_lef_gz_matches_plain_text(tmp_path):
    """getAllLefLines used to open each LEF directly, bypassing the gz-aware readFile."""
    gz = _gzipped(f"{SAMPLE}/cells.lef", tmp_path / "cells.lef.gz")
    assert cell_info_from_lef([gz]) == cell_info_from_lef([f"{SAMPLE}/cells.lef"])


def test_a_plain_file_named_gz_still_reads(tmp_path):
    """BadGzipFile falls back to a plain read, so a mislabelled file stays usable."""
    import shutil
    mislabelled = tmp_path / "core.v.gz"
    shutil.copyfile(f"{SAMPLE}/core.v", mislabelled)
    assert instance_info_from_verilog(str(mislabelled), "core") == \
        instance_info_from_verilog(f"{SAMPLE}/core.v", "core")


def test_netlist_split_across_files_is_one_design(tmp_path):
    """A netlist is usually one file per module; together they are a single design."""
    import re
    with open(f"{SAMPLE}/core.v", encoding="utf-8") as fh:
        text = fh.read()
    modules = re.findall(r"(module\s+(\w+)\b.*?endmodule)", text, re.S)
    assert len(modules) > 1, "the sample should define more than one module"

    paths = []
    for body, name in modules:
        path = tmp_path / f"{name}.v"
        path.write_text(body)
        paths.append(str(path))

    assert instance_info_from_verilog(paths, "core") == \
        instance_info_from_verilog(f"{SAMPLE}/core.v", "core")


def test_a_duplicate_module_warns(tmp_path, capsys):
    """Defining a module twice is a broken netlist, not a silent order dependence."""
    with open(f"{SAMPLE}/core.v", encoding="utf-8") as fh:
        text = fh.read()
    (tmp_path / "a.v").write_text(text)
    (tmp_path / "b.v").write_text(text)
    instance_info_from_verilog([str(tmp_path / "a.v"), str(tmp_path / "b.v")], "core")
    assert "more than one file" in capsys.readouterr().out


# -- the --json fill --------------------------------------------------------------

METAL = "sample_data/metal"


def _fill_file(tmp_path, name, top, instances):
    path = tmp_path / name
    path.write_text(json.dumps({"top_name": top, "instances": instances}))
    return str(path)


def _metal_design():
    """The committed two-level sample: TOP places SUB four times, at four orientations."""
    return [instance_info_from_def(f"{METAL}/top.def"),
            instance_info_from_def(f"{METAL}/sub.def")]


def test_fill_power_from_a_flattened_file(tmp_path):
    """A file whose top_name is the design itself, keyed by the names the DEF writes.

    That is this sample's own shape - its DEF flattens the hierarchy into the component names -
    so every key is an instance key and nothing has to be descended.
    """
    block = instance_info_from_def(f"{SAMPLE}/core.def")
    keys = sorted(block["instances"])[:2]
    path = _fill_file(tmp_path, "core.power.json", "core", {
        key: {"cell_name": block["instances"][key]["cell_name"],
              "leakage_power": 0.1, "dynamic_power": 0.3} for key in keys})

    summary = fill_instances([block], [path])

    assert (summary.files, summary.records, summary.matched) == (1, 2, 2)
    assert (summary.instances, summary.total) == (2, len(block["instances"]))
    assert summary.conflicts == 0 and summary.unusable == 0
    for key in keys:
        assert block["instances"][key]["leakage_power"] == 0.1
        assert block["instances"][key]["dynamic_power"] == 0.3


@pytest.mark.parametrize("top, key", [
    ("SUB", "r0_0"),                 # a sub-block's own file, keyed by its leaf names
    ("TOP", "u0/r0_0"),              # one file for the whole design, flattened
    ("TOP", "TOP/u0/r0_0"),          # ... with the absolute path the viewer shows
])
def test_the_same_record_is_found_however_it_is_addressed(tmp_path, top, key):
    """The two accepted forms, and the path a user copies out of the tree.

    All three name the same instance, and one record for a sub-block's leaf has to fill *every*
    placement of that block - four here - because the fill happens before the hierarchy is
    expanded, which is where the placements are made.
    """
    blocks = _metal_design()
    assert len(blocks[0]["instances"]) == 4          # the four placements of SUB
    leaf = sorted(blocks[1]["instances"])[0]
    path = _fill_file(tmp_path, "power.json", top, {key.replace("r0_0", leaf):
                                                    {"leakage_power": 0.5}})

    summary = fill_instances(blocks, [path])

    assert (summary.records, summary.matched) == (1, 1)
    assert summary.instances == 4                    # one record, four design instances
    assert summary.total == 4 * len(blocks[1]["instances"])
    assert blocks[1]["instances"][leaf]["leakage_power"] == 0.5


def test_the_input_wins_a_conflict_and_agreement_is_not_one(tmp_path, caplog):
    """The input's own attributes are facts about the design, not gaps to fill.

    A record restating them is counted only where it *disagrees*: a power file that repeats the
    cell name it was written from is not a conflict, while one naming a different cell is the
    strongest sign the file belongs to another version - and the run says so by name.
    """
    block = instance_info_from_def(f"{SAMPLE}/core.def")
    keys = sorted(block["instances"])[:2]
    same, other = block["instances"][keys[0]], block["instances"][keys[1]]
    path = _fill_file(tmp_path, "power.json", "core", {
        keys[0]: {"cell_name": same["cell_name"],          # agrees: nothing to report
                  "location_x": same["location_x"], "leakage_power": 0.2},
        keys[1]: {"cell_name": "NOT_" + other["cell_name"], "leakage_power": 0.2}})

    with caplog.at_level(logging.WARNING, logger="vlsi_viewer.parsers.convert"):
        summary = fill_instances([block], [path])

    assert summary.conflicts == 1 and summary.mismatched_cells == 1
    assert other["cell_name"] != "NOT_" + other["cell_name"]        # the design keeps its own
    assert other["leakage_power"] == 0.2                            # ... and gains the power
    assert "keeps its own" in caplog.text


def test_records_that_match_nothing_are_reported(tmp_path, caplog):
    """A wrong file, or a wrong block, has to be visible - and cheap to diagnose.

    Three shapes at once: a file naming a block this design does not have, a record under a real
    block that names no instance, and a record naming the sub-block itself rather than a leaf of
    it. Nothing is fatal; the counts say what was used.
    """
    blocks = _metal_design()
    unknown = _fill_file(tmp_path, "unknown.json", "NOPE", {"r0_0": {"leakage_power": 1.0}})
    mixed = _fill_file(tmp_path, "mixed.json", "TOP", {"u0": {"leakage_power": 1.0},
                                                       "nope": {"leakage_power": 1.0}})

    with caplog.at_level(logging.WARNING, logger="vlsi_viewer.parsers.convert"):
        summary = fill_instances(blocks, [unknown, mixed])

    assert (summary.files, summary.matched, summary.instances) == (2, 0, 0)
    assert summary.total == 4 * len(blocks[1]["instances"])          # the denominator is real
    assert "which is no block of this design" in caplog.text
    assert "filled no instance" in caplog.text
    assert "sub-block rather than a leaf" in caplog.text


def test_a_value_that_is_not_a_number_is_counted_not_crashed(tmp_path, caplog):
    """One bad value must not cost the run the other one in the same record."""
    block = instance_info_from_def(f"{SAMPLE}/core.def")
    key = sorted(block["instances"])[0]
    path = _fill_file(tmp_path, "power.json", "core",
                      {key: {"leakage_power": "not a number", "dynamic_power": 0.4}})

    with caplog.at_level(logging.WARNING, logger="vlsi_viewer.parsers.convert"):
        summary = fill_instances([block], [path])

    assert summary.unusable == 1 and summary.instances == 1
    assert block["instances"][key]["dynamic_power"] == 0.4
    assert "leakage_power" not in block["instances"][key]
    assert "could not be used" in caplog.text


def test_the_filled_data_survives_the_loader(tmp_path):
    """Why the fill is a dict operation: after `load_block` an absent attribute is 0.0.

    The loader fills every schema default, so a power of zero and a power nobody supplied are the
    same value - which is precisely what a later merge could not act on.
    """
    from vlsi_viewer.loader import load_block

    block = instance_info_from_def(f"{SAMPLE}/core.def")
    key = sorted(block["instances"])[0]
    power = _fill_file(tmp_path, "power.json", "core", {key: {"leakage_power": 0.25}})

    fill_instances([block], [power])
    _name, df, _boundary = load_block(block)

    row = df[df["leaf_instance_name"] == key].iloc[0]
    assert row["leakage_power"] == 0.25
    assert row["dynamic_power"] == 0.0               # absent, so defaulted - not a value


def test_the_committed_power_sample_still_matches_the_def():
    """A stale sample would fill nothing and say so only in a warning, so it is pinned here."""
    block = instance_info_from_def(f"{SAMPLE}/core.def")
    with open(f"{SAMPLE}/core.power.json", encoding="utf-8") as fh:
        power = json.load(fh)
    assert power["top_name"] == block["top_name"]
    assert set(power["instances"]) == set(block["instances"])
    for key, record in power["instances"].items():
        assert record["cell_name"] == block["instances"][key]["cell_name"], key
        assert record["leakage_power"] > 0 and record["dynamic_power"] > 0, key


def test_the_instance_table_is_built_once_not_per_record():
    """The regression for a fill that took days: one table per block, and no copy when there is
    nothing to merge.

    Resolving a record used to rebuild the block's whole dict, so a flat 3.35M-instance design
    copied 3.35M entries for each of its 3.35M records (measured 74.8 us per call at 1k entries,
    growing linearly, i.e. days in total). The table for a single-block design is now the block's
    own dict, so a lookup is one hash probe.
    """
    from vlsi_viewer.parsers.convert import _block_instances

    block = {"top_name": "TOP", "instances": {"a": {"cell_name": "C1"}}}
    tables = _block_instances([block])
    assert tables["TOP"] is block["instances"]          # no copy: the entries are the objects

    # Two blocks sharing a top_name are still merged, earlier file winning a duplicate leaf -
    # the rule `metrics._merge_blocks` applies to the same case.
    first = {"top_name": "TOP", "instances": {"a": {"cell_name": "C1"}, "b": {"cell_name": "C1"}}}
    second = {"top_name": "TOP", "instances": {"a": {"cell_name": "OTHER"}, "c": {"cell_name": "C1"}}}
    tables = _block_instances([first, second])
    assert set(tables["TOP"]) == {"a", "b", "c"}
    assert tables["TOP"]["a"] is first["instances"]["a"]


def test_a_flat_fill_scales_linearly(tmp_path):
    """8k instances with 8k records: ~40 ms now, ~5 s while the lookup rebuilt the block's dict.

    The bound is loose on purpose - it is a shape check, not a benchmark - and it is set an order
    of magnitude above the measured cost and an order below the quadratic one.
    """
    import time

    n = 8_000
    block = {"top_name": "TOP",
             "instances": {f"u0/b0/i{k}": {"cell_name": "INV_X1_SVT"} for k in range(n)}}
    path = tmp_path / "power.json"
    path.write_text(json.dumps({"top_name": "TOP", "instances": {
        key: {"leakage_power": 0.01} for key in block["instances"]}}))

    started = time.perf_counter()
    summary = fill_instances([block], [str(path)])
    elapsed = time.perf_counter() - started

    assert summary.instances == n and summary.conflicts == 0
    assert elapsed < 1.0, f"{elapsed:.1f}s for {n} records - the lookup is quadratic again"


def test_the_fill_reports_progress(tmp_path, caplog, monkeypatch):
    """A record loop that can run for minutes says where it is, and the summary says how long.

    Silence is half of why a slow fill was reported as a hang: the file is read without a word and
    the first line came after the whole loop.
    """
    import logging

    from vlsi_viewer.parsers import convert

    monkeypatch.setattr(convert, "FILL_PROGRESS_RECORDS", 2)
    block = instance_info_from_def(f"{SAMPLE}/core.def")
    keys = sorted(block["instances"])[:5]
    path = _fill_file(tmp_path, "power.json", "core",
                      {key: {"leakage_power": 0.1} for key in keys})

    with caplog.at_level(logging.INFO, logger="vlsi_viewer.parsers.convert"):
        summary = fill_instances([block], [path])

    said = [record.getMessage() for record in caplog.records]
    assert any(text.startswith("power: reading ") for text in said)
    progress = [text for text in said if "record(s) read" in text]
    assert [text.split(": ")[2].split(" of ")[0] for text in progress] == ["2", "4"]
    summary_line = next(text for text in said if "record(s) filled" in text)
    assert summary_line.endswith(")") and "s)" in summary_line
    assert summary.matched == len(keys)
