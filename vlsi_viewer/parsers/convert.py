"""Convert LEF / DEF / Verilog into the viewer's JSON structures.

The outputs are plain ``dict``s that :func:`vlsi_viewer.loader.load_block` and
:func:`vlsi_viewer.loader.load_cell_info` already accept - there is no second format,
so everything downstream (metrics, physical mode, the GUI) works unchanged.

Units: LEF ``SIZE`` is in microns and DEF coordinates are integers in DEF database
units, so every DEF coordinate is divided by ``DefParser.dbUnit()`` to match.
"""
import gzip
import logging
import re

from .. import schema

logger = logging.getLogger(__name__)

# Filler cells tiled across every row gap. These are dropped rather than flagged
# physical-only: they cover the whole core, so counting them would drive the density
# heat map to 100% and hide the real utilisation. DCAP/GDCAP are *not* dropped - they
# are sparse, and they are legitimately physical-only area.
FILL_PREFIX = "FILL"

# Cell-name heuristics. These are library conventions, not LEF syntax: nothing in a
# LEF file says which cell is a buffer or how many bits a flop holds. The rules follow
# dev_plan/code_sample/extractCellInfo.py (the LinxCore library these samples target),
# with two changes noted at their use sites. Edit this block for another library.
PHYSICAL_ONLY_PATTERNS = ("FILL", "BOUNDARY", "BHD", "ANTENNA", "DCAP", "TIE", "TAP",
                          "GDCAP", "HDDI")

# (regex, schema field) pairs applied to CORE cells only.
_NAME_FLAGS = (
    (r"^BUF|CKBD", "is_buffer"),
    (r"^INV|CKND", "is_inverter"),
    (r"^CK|^DCCK", "is_clock_cell"),
    (r"^CKLN", "is_integrated_clock_gating_cell"),
)
# Mutually exclusive, and the order matters: "..._ULVT" also ends with "LVT".
_VT_SUFFIXES = (("ULVT", "is_ULVT"), ("LVT", "is_LVT"), ("SVT", "is_SVT"))
_DRIVE_COT = re.compile(r"D(\d+)(?:PUL)?COT.*VT")   # LinxCore: D4PULCOT...VT
_DRIVE_X = re.compile(r"_X(\d+)")                   # common: INV_X1, BUF_X2_LVT
_MB_BITS = re.compile(r"MB(\d+)")


def _is_physical_only_name(name: str) -> bool:
    """Whether a cell is area-only (filler, tap, decap, antenna, boundary...)."""
    upper = name.upper()
    return any(p in upper for p in PHYSICAL_ONLY_PATTERNS)


def _drive_size(name: str) -> int:
    """Drive strength: LinxCore's ``D<n>...COT...VT`` form, else an ``_X<n>`` infix.

    The ``_X<n>`` search is deliberately not anchored: names carry a Vt suffix after it
    (``INV_X2_LVT``), so anchoring on the end would miss most of the library.
    """
    match = _DRIVE_COT.search(name)
    if match:
        return int(match.group(1))
    match = _DRIVE_X.search(name.upper())
    return int(match.group(1)) if match else 0


def is_macro_class(macro_class: str) -> bool:
    """Whether a LEF ``CLASS`` value names a hard macro rather than a standard cell.

    Only the *first* word names the class. The reference grammar is
    ``CLASS {COVER [BUMP] | RING | BLOCK [BLACKBOX|SOFT] | PAD [INPUT|...|SPACER|AREAIO]
    | CORE [FEEDTHRU|TIEHIGH|TIELOW|SPACER|ANTENNACELL|WELLTAP] | ENDCAP {...}}``, so
    ``CLASS CORE SPACER ;`` is a CORE cell. Comparing the whole string against "CORE" made
    every filler, antenna and welltap cell a hard macro, and a macro removes capacity from
    the layers it blocks: on the real Nangate45 library that is 8 cells, worth 1 % of a
    32.7 um block's bottom-layer capacity.

    Public because the metal-density blockage model asks the same question of the same LEF
    values, and two copies of this rule would drift.
    """
    classes = (macro_class or "").upper().split()
    return (classes[0] if classes else "") != "CORE"


def _cell_attrs(name: str, macro) -> dict:
    """One ``cell_info.json`` entry, shaped exactly like ``schema.CELL_ATTRS``."""
    attrs = {spec.name: spec.default for spec in schema.CELL_ATTRS}
    size_x, size_y = macro.size()
    attrs["area"] = size_x * size_y
    attrs["size_x"] = size_x
    attrs["size_y"] = size_y
    # Divergence from extractCellInfo.py, which used ``drive_size != 0``: the viewer's
    # is_macro drives the macro columns and the Density% metric, so it has to mean
    # "LEF hard macro", which is what a non-CORE CLASS encodes. The rule itself lives in
    # `is_macro_class`, shared with the metal-density blockage model.
    attrs["is_macro"] = is_macro_class(macro.macroClass())
    attrs["is_physical_only"] = _is_physical_only_name(name)
    if attrs["is_macro"]:
        attrs["is_sram"] = "SRAM" in name.upper()
        return attrs
    if attrs["is_physical_only"]:
        return attrs        # filler/tap carry no logic flags

    upper = name.upper()
    for pattern, field in _NAME_FLAGS:
        attrs[field] = re.search(pattern, name) is not None
    attrs["is_pulse_latch"] = "PUL" in upper
    is_ff = "SDF" in upper
    attrs["is_register_cell"] = is_ff
    # Divergence from extractCellInfo.py's ``r'^MB(d)'``: that is a literal "d", so
    # int('d') raises for any MBd... cell. Multi-bit flops carry the bit count here.
    mb = _MB_BITS.search(upper)
    attrs["register_bit_count"] = int(mb.group(1)) if mb else (1 if is_ff else 0)
    attrs["is_combinational_cell"] = not (is_ff or "LN" in upper or "LH" in upper)
    attrs["drive_size"] = _drive_size(name)
    for suffix, field in _VT_SUFFIXES:
        if upper.endswith(suffix):
            attrs[field] = True
            break
    return attrs


def cell_info_from_lef(lef_paths, with_obstructions: bool = False, with_pins: bool = False):
    """``cell_info.json`` data from one or more macro LEF files.

    Every macro is emitted, including filler and tap cells: the viewer needs their
    ``size_x``/``size_y`` to draw their area, and their absence would silently drop
    them from the density map (``physical.py`` skips cells missing from cell_info) and
    show them as zero-area leaves in the tree.

    ``with_obstructions`` returns the macros' own ``OBS`` geometry alongside, keyed by cell and
    then by layer, for the metal-density blockage model. ``with_pins`` returns each macro's
    signal-pin centres instead, keyed by cell, for the pin-density map - one ``(x, y)`` per pin,
    in the macro's own microns, with power and ground pins already dropped. Both cost nothing to
    ask for: the ``LefParser`` walk already reads this geometry while building each macro, so the
    choice is between carrying it out of that parse and parsing the whole library a second time -
    which is what the blockage stage used to do, and what a caller with both needs avoids. They
    are separate tables, so ask for one at a time.
    """
    from .LEF import LefParser

    if with_obstructions and with_pins:
        raise ValueError("cell_info_from_lef returns one extra table, not two")

    macros = LefParser(list(lef_paths)).getMacros()
    logger.info("lef: %d macro(s) from %d file(s)", len(macros), len(lef_paths))
    info = {name: _cell_attrs(name, macro) for name, macro in macros.items()}
    if with_obstructions:
        obstructions = {}
        for name, macro in macros.items():
            if not is_macro_class(macro.macroClass()):
                continue                 # a standard cell's OBS is pin access, not a keep-out
            declared = macro.obstructions()
            if declared:
                obstructions[name] = declared
        return info, obstructions
    if with_pins:
        pins = {}
        for name, macro in macros.items():
            declared = [pin.centre for pin in macro.pins() if _counts_as_pin(pin)]
            if declared:
                pins[name] = declared
        return info, pins
    return info


# Power and ground pins, which the pin-density map excludes: a rail pin sits on every
# instance of a cell in a row, so it measures the row, not the design. The LEF's ``USE``
# is the authority and is not always spelled in upper case; the name is the fallback for
# the libraries that write ``USE SIGNAL`` on a VDD pin.
_POWER_PIN_NAME = re.compile(r"^(VDD|VSS|VCC|GND|VPP|VBB|VPW|VNW)", re.IGNORECASE)


def _counts_as_pin(pin) -> bool:
    if pin.centre is None:
        return False                     # no geometry, so no point to count
    if (pin.use or "").upper() in ("POWER", "GROUND"):
        return False
    return _POWER_PIN_NAME.match(pin.pin_name or "") is None


def instance_info_from_verilog(verilog_paths, top) -> dict:
    """``instance_info.json`` data from one gate-level netlist.

    ``verilog_paths`` is one file or several; a netlist split across files is one
    design, so they are merged before the walk and produce a single result.
    ``InstExtractor`` already flattens the hierarchy to ``{rel/path: cell_name}``, which
    is exactly the ``instances`` mapping. There is no placement in a netlist, so the
    result carries no ``boundary`` - which is why this path cannot drive physical mode.
    """
    from .verilog import InstExtractor

    found = InstExtractor(verilog_paths, top).insts
    logger.info("verilog: %s -> %d instance(s) under %s",
                verilog_paths, len(found), top)
    return {"top_name": top,
            "instances": {rel: {"cell_name": cell} for rel, cell in found.items()}}


def _read_head(path, limit: int = 65536) -> str:
    """The first ``limit`` characters of a DEF, transparently handling ``.gz``."""
    try:
        if str(path).endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as fh:
                return fh.read(limit)
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def instance_info_from_def(def_path, top=None) -> dict:
    """``instance_info.json`` data from one DEF (placement).

    ``top`` overrides the DEF ``DESIGN`` name. Coordinates are converted from DEF
    database units to microns; ``orient`` is passed through because DEF's
    ``N/S/W/E/FN/FS/FW/FE`` already match ``Orient.orient_map``.

    DEF carries no power data, so ``leakage_power``/``dynamic_power`` are left out and
    the loader defaults them to 0.0 - the leakage and dynamic heat maps come out empty.
    """
    from .DEF import DefParser

    parser = DefParser(def_path)
    db_unit = parser.dbUnit()
    head = _read_head(def_path)
    if not re.search(r"UNITS\s+DISTANCE\s+MICRONS", head):
        logger.warning("%s declares no 'UNITS DISTANCE MICRONS'; assuming %d database "
                       "units per micron, which may scale the design incorrectly",
                       def_path, db_unit)

    components = parser.getAllComponents()
    declared = re.search(r"COMPONENTS\s+(\d+)\s*;", head)
    if declared and int(declared.group(1)) != len(components):
        # DefParser reads one line at a time, so a component statement wrapped over
        # several lines is dropped silently.
        logger.warning("%s declares %s components but %d were parsed; wrapped "
                       "component statements may have been skipped",
                       def_path, declared.group(1), len(components))

    name = top or parser.designName or ""
    if not name:
        raise ValueError(f"DEF {def_path} has no DESIGN name; pass --top")

    instances = {}
    dropped_fill = unplaced = 0
    for comp in components:
        model = str(comp.model_name)
        if model.upper().startswith(FILL_PREFIX):
            dropped_fill += 1
            continue
        if str(comp.pstatus).upper() == "UNPLACED":
            # Kept at (0, 0) by the parser, which would pile every unplaced instance
            # onto the die origin in physical mode.
            unplaced += 1
            continue
        instances[comp.comp_name] = {
            "cell_name": model,
            "location_x": comp.pos_x / db_unit,
            "location_y": comp.pos_y / db_unit,
            "orient": comp.orient,
        }

    boundary = [[x / db_unit, y / db_unit] for x, y in parser.shape()]
    logger.info("def: %s -> %d instance(s) (dropped %d filler, skipped %d unplaced), "
                "%d boundary point(s)", def_path, len(instances), dropped_fill,
                unplaced, len(boundary))
    return {"top_name": name, "boundary": boundary, "instances": instances}
