"""Convert LEF / DEF / Verilog into the viewer's JSON structures.

The outputs are plain ``dict``s that :func:`vlsi_viewer.loader.load_block` and
:func:`vlsi_viewer.loader.load_cell_info` already accept - there is no second format,
so everything downstream (metrics, physical mode, the GUI) works unchanged.

Units: LEF ``SIZE`` is in microns and DEF coordinates are integers in DEF database
units, so every DEF coordinate is divided by ``DefParser.dbUnit()`` to match.
"""
import gzip
import json
import logging
import re
from dataclasses import dataclass
from typing import AnyStr, Dict, List, Sequence

from .. import schema
# The loader's own coercion, so a value this accepts is a value the loader accepts: one
# definition of what a JSON attribute may look like ("1" for a bool, "2.5" for a float).
from ..loader import _coerce

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




# ------------------------------------------------------------------ incremental fill
#
# DEF and a netlist describe structure and placement and carry no power, so the leakage and
# dynamic heat maps come out flat for those flows. `--json` closes that gap: instance data from
# files the `json` subcommand already reads is filled into the converted blocks *here*, before
# anything loads them.
#
# Here rather than after loading, because absence is only expressible in a dict like this: the
# loader turns a missing attribute into its default (0.0 for power), and a default cannot be told
# from a value somebody meant. And it happens before the hierarchy is expanded, so one record for
# a sub-block's leaf fills *every* placement of that block - `metrics.load_blocks` and
# `physical.walk` both expand these same dicts later, each of them reading power off the entry.


@dataclass
class FillSummary:
    """What one fill did, for the summary `cli` prints and for the tests.

    ``instances`` and ``total`` are counted over *design* instances, not over records: a record
    for a sub-block's leaf that the design places four times fills four. They are walk counts
    rather than a tally kept while filling, because two files may fill one instance's different
    attributes and a per-file tally would call that two instances.
    """

    files: int = 0
    records: int = 0                 # records offering at least one fillable value
    matched: int = 0                 # records that resolved to a leaf of the design
    instances: int = 0               # design instances that carry a filled attribute
    total: int = 0                   # design instances in all, for the partial-fill denominator
    conflicts: int = 0               # the input already had the attribute: the file's is dropped
    unusable: int = 0                # a record or value that could not be used
    mismatched_cells: int = 0        # a record whose cell_name is not the design's


def _names(names, limit: int = 5) -> str:
    """``a, b, c`` for a warning: enough to recognise the design, not a listing of it."""
    ordered = sorted(str(name) for name in names)
    shown = ", ".join(ordered[:limit])
    return shown + (f", +{len(ordered) - limit}" if len(ordered) > limit else "")


def _read_instance_json(path) -> dict:
    """One ``--json`` file as written - no defaults, because absence is what the fill reads."""
    try:
        with open(str(path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        # A missing or malformed file is a wrong argument rather than a partial fill, so this
        # reaches `cli.main`, which prints `error: ...` and exits 1 - the same as a bad --def.
        raise ValueError(f"instance json {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"instance json {path}: expected an object with 'instances'")
    return data


def _index_blocks(blocks) -> Dict[str, List[dict]]:
    """``top_name -> the blocks with that name``, in input order.

    Several blocks can share a name (``metrics._merge_blocks`` unions them, earlier file winning a
    duplicate leaf), so every lookup goes through `_instances` and takes the earlier entry.
    """
    index: Dict[str, List[dict]] = {}
    for block in blocks:
        index.setdefault(str(block.get("top_name") or ""), []).append(block)
    return index


def _instances(index: Dict[str, List[dict]], name: str) -> dict:
    """The instances of the block called ``name``, with the group's duplicates merged."""
    merged: dict = {}
    for block in index.get(name, ()):
        for leaf, entry in block["instances"].items():
            merged.setdefault(leaf, entry)           # earlier file wins, as `_merge_blocks` does
    return merged


def _resolve(index: Dict[str, List[dict]], name: str, key: str, seen=frozenset()):
    """The instance entry ``key`` names, relative to the block called ``name``, or ``None``.

    The key is tried whole first: a DEF that flattens its hierarchy into the component names
    (``sample_data/eda`` writes ``- u0/b0/tap_1_0 TAP_1 ...``) holds ``u0/b0/tap_1_0`` as one
    instance, while one that really instantiates a sub-block holds ``u0`` and the key descends
    through it. Descending is by ``cell_name`` naming another block - the same rule
    `metrics.load_blocks` and `physical.walk` use to expand the hierarchy - so an entry this
    accepts is one both of them will place and read power off.
    """
    if name not in index or name in seen:
        return None
    instances = _instances(index, name)
    if key in instances:
        return instances[key]
    head, sep, tail = key.partition("/")
    if not sep or not head:
        return None
    entry = instances.get(head) or {}
    child = str(entry.get("cell_name") or "")
    if child in index:
        return _resolve(index, child, tail, seen | {name})
    return None


def _target(index: Dict[str, List[dict]], top: str, raw_key):
    """`_resolve` for one record, tolerating the absolute path a user may have exported.

    The hierarchy paths the viewer shows and ``--out`` writes start with the top name
    (``core/u0/b0/x``), so a leading ``<top>/`` is stripped and the key retried.
    """
    key = str(raw_key).replace("\\", "/").strip("/")
    found = _resolve(index, top, key)
    if found is None and key.startswith(top + "/"):
        found = _resolve(index, top, key[len(top) + 1:])
    return found


def _shape(index: Dict[str, List[dict]], wanted) -> List[int]:
    """``[design instances, the ones carrying a filled attribute]``.

    The same walk the hierarchy does, counting rather than placing: a block nothing instantiates
    is a top (all of them are, if every block is referenced), and a block placed K times counts
    its leaves K times - which is what makes "N of M instance(s)" mean instances on screen.
    """
    referenced = {str(entry.get("cell_name") or "")
                  for group in index.values() for block in group
                  for entry in block["instances"].values()}
    tops = [name for name in index if name not in referenced] or list(index)
    leaves, filled = {}, {}
    for name in index:
        entries = _instances(index, name)
        keep = [entry for entry in entries.values()
                if str(entry.get("cell_name") or "") not in index]
        leaves[name] = len(keep)
        filled[name] = sum(1 for entry in keep if any(spec in entry for spec in wanted))
    counts = [0, 0]
    visiting = set()

    def walk(name: str) -> None:
        if name in visiting:            # a cycle: the walks warn and stop, and so does the count
            return
        visiting.add(name)
        counts[0] += leaves[name]
        counts[1] += filled[name]
        for entry in _instances(index, name).values():
            child = str(entry.get("cell_name") or "")
            if child in index:
                walk(child)
        visiting.discard(name)

    for name in tops:
        walk(name)
    return counts


def fill_instances(blocks, json_paths) -> FillSummary:
    """Fill instance attributes from ``--json`` files into converted blocks, **in place**.

    The file's ``top_name`` names the block its record keys are relative to, which is the whole
    of "a flattened top file or a per-block file": keys are resolved against that block, and a
    key whose first path segment names an instance of another block descends into it. Either
    form, in any order, so a ``TOP.json`` covering the design and a ``sub_A.json`` covering one
    sub-block both apply - and a sub-block's record fills every placement of it.

    An attribute the converted input already has is never overwritten: its cell name and placement
    are facts about the design, not gaps, so the file's value for one is dropped and counted. A
    record naming an instance the design does not have is ignored and counted. Nothing here is
    fatal, because a partial fill is the normal case - one file per sub-block is exactly that.
    """
    index = _index_blocks(blocks)
    summary = FillSummary(files=len(json_paths))
    wanted = set()
    for path in json_paths:
        data = _read_instance_json(path)
        top = str(data.get("top_name") or "")
        records = data.get("instances")
        if top not in index:
            logger.warning(
                "power: %s names '%s', which is no block of this design (%s); its %d record(s) "
                "are unused", path, top or "<no top_name>", _names(index),
                len(records) if isinstance(records, dict) else 0)
            continue
        if not isinstance(records, dict):
            raise ValueError(f"instance json {path}: 'instances' must be an object")

        unmatched: List[str] = []
        containers: List[str] = []
        mismatched: List[tuple] = []
        unusable = applied = 0
        offered = filled_records = 0
        for raw_key, record in records.items():
            if not isinstance(record, dict):
                unusable += 1
                continue
            entry = _target(index, top, raw_key)
            if entry is None:
                unmatched.append(str(raw_key))
                continue
            if str(entry.get("cell_name") or "") in index:
                containers.append(str(raw_key))      # a sub-block's own instance, not a leaf
                continue
            summary.matched += 1
            values = {}
            for spec in schema.INSTANCE_ATTRS:
                if spec.name not in record or record[spec.name] is None:
                    continue
                try:
                    values[spec.name] = _coerce(record[spec.name], spec.type)
                except (TypeError, ValueError):
                    unusable += 1
            if not values:
                continue                             # not a record this feature can use
            summary.records += 1
            offered += 1
            wrote = 0
            for name, value in values.items():
                if name in entry:
                    # The input's own value stands. Only a real disagreement is a conflict - a
                    # file restating a placement it agrees with has ignored nothing - and a
                    # disagreeing cell name is the strongest sign the file belongs to another
                    # version of the design, so that one is said out loud.
                    if entry[name] != value:
                        summary.conflicts += 1
                        if name == "cell_name":
                            summary.mismatched_cells += 1
                            mismatched.append((str(raw_key), value, entry[name]))
                    continue
                entry[name] = value
                wanted.add(name)               # what the design ends up *carrying* from the file
                applied += 1
                wrote += 1
            if wrote:
                filled_records += 1
        summary.unusable += unusable
        logger.info("power: %s -> %d of %d record(s) filled", path, filled_records, offered)
        if unmatched or containers:
            logger.warning(
                "power: %s: %d of %d record(s) filled no instance of '%s'%s (e.g. %s)", path,
                len(unmatched) + len(containers), len(records), top,
                f", {len(containers)} of them naming a sub-block rather than a leaf"
                if containers else "", _names(unmatched or containers, 3))
        if mismatched:
            key, value, own = mismatched[0]
            logger.warning("power: %s: %d record(s) name a different cell than the design "
                           "(e.g. %s: %s, where the design places %s); the design keeps its own",
                           path, len(mismatched), key, value, own)
        if unusable:
            logger.warning("power: %s: %d record(s) or value(s) could not be used",
                           path, unusable)
        if not applied:
            logger.warning("power: %s: nothing was filled under '%s'; its data is unused",
                           path, top)

    # Counted even when nothing was filled, so "0 of N instance(s)" is a real denominator: the
    # number to read next to the warning that says no record matched.
    summary.total, summary.instances = _shape(index, wanted)
    return summary
