# Using this project's DEF / LEF / Verilog parsers from another project

Three layers sit on top of each other. Take the lowest one that answers your question — each one
needs less of this repository than the one above it.

| layer | module | what you get | needs |
|---|---|---|---|
| 1 | `vlsi_viewer.parsers.{DEF,LEF,verilog}` | the vendored parsers: DEF placement and wiring, LEF macros and tech layers, a netlist flattened | **stdlib only** |
| 2 | `vlsi_viewer.parsers.convert` | the same inputs as plain dicts in this project's JSON schema — cells, instances with placement in microns, pins | layer 1, `pandas` |
| 3 | `vlsi_viewer.parsers.routing` | routing layers with pitch/width/spacing, and a DEF's wires streamed as micron-space shapes | layers 1–2, `numpy` (`shapely` too, imported only where a `+ POLYGON` is expanded) |

Everything here is Python 3.9+ and reads files as-is; nothing in the parser layer imports Qt.

## Copying it, and importing it

- **Layer 1 alone** is self-contained: copy `vlsi_viewer/parsers/` (the `DEF/`, `LEF/` and
  `verilog/` subpackages plus `_util.py`) into your tree and fix the one relative import worth
  knowing about — the subpackages import `.._util` for `readFile`/`Print`/`Cancelled`. They use
  nothing else from this repository, and nothing outside the standard library.
- **Layers 2–3** need this repository: `convert.py` imports `..schema` and `..loader`,
  `routing.py` imports `..assembly`. `import vlsi_viewer.parsers` runs
  `vlsi_viewer/__init__.py`, which pulls in `pandas` (through `metrics`) — but **not** PyQt5, so a
  headless tool can import the parsers without a Qt install. Add the repository root to
  `sys.path`, or install the project, and:

```python
from vlsi_viewer.parsers import DefParser, LefParser, TlefParser, VerilogParser, InstExtractor
from vlsi_viewer.parsers.convert import (cell_info_from_lef, instance_info_from_def,
                                         instance_info_from_verilog)
from vlsi_viewer.parsers.routing import TechRouting, ShapeStream, parse_def, SIGNAL, POWER
```

The examples below were all run against the committed samples under `sample_data/eda` (a small CPU
cluster: `core.def`, `core.v`, `cells.lef`, `core.power.json`) and `sample_data/metal`
(`top.def` + `sub.def` + `tech.lef`), with the printed results copied from that run.

---

## Layer 1 — the vendored parsers

These came from another project; the directory names (`DEF`, not `def` — a Python keyword), the
method names (`camelCase`) and the internals are kept so the code stays traceable to its source.
Two of them shadow a method with an attribute: read the accessor table before writing calls.

### `DefParser` — placement, pins, obstructions, nets

**It parses the whole file in the constructor.** There is no `parse()` to call and no lazily-read
accessor; when the call returns, everything the flags asked for is in memory (or has been handed to
your `sink`).

```python
DefParser(def_file, skip_comp=False, parse_pin=False, batch_mode=False, parse_net=False,
          parse_blockage=False, parse_specialnet=False, parse_ndr=True, sink=None,
          cancel=None, lines=None, puts=None)
```

| argument | meaning |
|---|---|
| `def_file` | path; `.gz` is read transparently. Also used to *name* the input in progress lines when `lines` carries the text |
| `skip_comp` / `parse_pin` / `parse_blockage` / `parse_specialnet` / `parse_net` | which sections to build. With all of these off (the default except `parse_ndr`) the parse **stops at `END COMPONENTS`**, which is what makes a placement-only pass cheap |
| `parse_ndr` | non-default rule table; on by default, and needed to scale a wire's own width/spacing |
| `sink` | `sink(net, db_unit, ndrs)` called once per net as it is parsed, which is then dropped instead of accumulating in `getAllNets()`. This is how a 10⁸-segment DEF is read without holding it |
| `cancel` | callable, consulted once per heartbeat (`DefParser.HEARTBEAT_SECONDS`, 30 s). Returning `True` raises `Cancelled`, and what was already measured stays valid |
| `lines` | the DEF as an iterable of text lines instead of a file (the parallel path hands workers a slice of statements) |
| `puts` | where progress lines go; default `print` in `batch_mode` else the module's `Print` |

**Coordinates are raw DEF database units.** Divide by `dbUnit()` for microns — the unit is read from
`UNITS DISTANCE MICRONS`, and falls back to 2000 when the file does not say. That is the only
conversion the parser does; every rule it reports is in the file's own units too.

Accessors, with the shape each returned on `core.def` (`UNITS 1000`, 3994 components):

| call | returns |
|---|---|
| `designName` | **a `str` attribute, not a method** (`DefParser.designName` is shadowed by the instance attribute; the method at the bottom of the file is unreachable). `'core'` |
| `dbUnit()` | `int` — `1000` |
| `shape()`, `getDieArea()` | `[(x, y), ...]` in database units: the die outline, and `DIEAREA`'s two points. `[]` when the DEF declares no die |
| `getHeight()`, `getWidth()` | `int` database units, derived from the die |
| `getAllComponents()`, `getComponent(name)` | `List[DefComponent]` / one by name |
| `getAllPins()`, `getPin(name)` | `List[DefPin]` (only with `parse_pin=True`) |
| `getAllNets()`, `getNet(name)` | `List[DefNet]` (only with `parse_net`/`parse_specialnet`, and empty when a `sink` was given) |
| `getBlockages()` | `List[DefBlockage]` (only with `parse_blockage=True`) |
| `getTracks()` | `List[DefTrack]` — `TRACKS` clauses, in database units |
| `getNdrRules()` | `{rule_name: DefNdrRule}` |
| `getStats()` | what the *text* was like: `forms`, `points`, `lines`, `statement_lines_max`, `statement_chars_max`, `points_max`, `virtual`, `rects`, `layers_used` |
| `n_nets`, `n_special_nets`, `declared_nets`, `declared_special_nets` | the counts, declared vs parsed — compare them yourself, or let `parse_def` do it (layer 3) |

```python
>>> p = DefParser("sample_data/eda/core.def")
>>> p.designName, p.dbUnit(), p.shape()
('core', 1000, [(0, 0), (0, 88000), (122000, 88000), (122000, 0)])
>>> c = p.getAllComponents()[0]
>>> c.comp_name, c.model_name, c.pstatus, c.pos_x, c.pos_y, c.orient
('u0/b0/tap_1_0', 'TAP_1', 'PLACED', 6000, 40000, 'N')
>>> c.pos_x / p.dbUnit()                      # microns
6.0
```

Filtering is done by **class attributes**, because the parse happens inside `__init__` there is no
instance to configure first:

```python
DefParser.IGNORE_FILLER = True   # drop FILL*/DCAP*/GDCAP* while parsing
DefParser.IGNORE_PHY = True      # drop + SOURCE DIST components and COVER ones
```

Streaming the wiring instead of holding it:

```python
totals = {"nets": 0, "wires": 0, "vias": 0}

def sink(net, db_unit, ndrs):
    totals["nets"] += 1
    totals["wires"] += len(net.wiring)
    totals["vias"] += net.via_points

p = DefParser("sample_data/metal/sub.def", parse_net=True, parse_specialnet=True,
              skip_comp=True, sink=sink)
# {'nets': 14779, 'wires': 19928, 'vias': 0}   design 'SUB', 14777 NETS + 2 SPECIALNETS
```

`DefNet` keeps what the sections contain, and separates what would otherwise be conflated:
`net_name`, `connect_pins`, `wiring` (`DefWire`), `swiring` (`DefSWire`, a SPECIALNETS wire with an
extent), `polygons` (`DefSPolygon`, whole `+ POLYGON` rings — `swiring` holds only their edges),
`is_special` (which section it came from), `use` (`POWER`/`GROUND`/`SIGNAL` when the net says so),
`via_points` and `via_points_by_layer` (**counted, never built**: a via point is a zero-length shape
whose geometry nothing reads, and on a chip-level DEF they are most of the shapes), plus
`n_virtual`.

### `LefParser` / `TlefParser` — the cell library and the tech stack

```python
macros = LefParser(["sample_data/eda/cells.lef"]).getMacros()   # {name: LefMacro}
macro  = macros["SRAM_512"]
macro.macroName(), macro.macroClass(), macro.size()             # 'SRAM_512', 'BLOCK', (16.0, 8.0)
```

Several LEF files are **one** library (they are concatenated before parsing), so `getMacros()`
returns every macro from all of them. Sizes, pin geometry and obstruction geometry are in
**microns** — LEF is a micron format, unlike DEF.

| `LefMacro` | returns |
|---|---|
| `macroName()`, `macroClass()`, `size()` | name, the LEF `CLASS` (`CORE`, `BLOCK`, …), `(width, height)` in microns |
| `obstructions()` | `{layer name: [(x0, y0, x1, y1), ...]}` in the macro's own coordinates, **copied** so you may filter it. `{}` means the macro declares no `OBS` at all |
| `pins()`, `pin(name)` | `List[LefPin]` / one of them; `LefPin` carries `pin_name`, `direction`, `use`, `layer`, `shape` (its RECTs) and `centre` (of the union of them, `None` when it declares no RECT) |
| `getInputPinNum()`, `getOutputPinNum()`, `getInoutPinNum()` | counts by direction |

`TlefParser` reads a **tech** LEF. Its result is an *attribute*, not a call — the method of the same
name is shadowed:

```python
layers = TlefParser("sample_data/metal/tech.lef").layers     # {name: LefLayer}, 15 of them
m2 = layers["M2"]
m2.type, m2.direction, m2.width, m2.spacing, m2.pitch_x, m2.pitch_y
# 'ROUTING', 'VERTICAL', 0.07, 0.07, 0.19, 0.19
```

`LefLayer` fields: `name`, `type`, `lef58_type`, `direction`, `pitch_x`, `pitch_y`, `width`,
`min_width`, `max_width`, `spacing`, `area`, and `region_layer`/`region`/`based_layer` for the
`PROPERTY LEF58_REGION` variant (not a track system of the stack; layer 3 drops those). LEF is a
micron format, so these are microns exactly as written — unlike DEF, nothing is converted.

### `VerilogParser` / `InstExtractor` — a gate-level netlist

```python
vp = VerilogParser("sample_data/eda/core.v", ignore_conn=True)
mod = vp.module("core")
len(vp.allModules()), len(mod.allPorts), len(mod.allInsts), len(mod.allNets)
# 3, 2, 6, 0
```

`ignore_conn=True` skips building per-instance connection objects — on a large netlist they are the
bulk of the memory and a structural question ("which cell, where") does not need them. `allModules()`
gives `{module name: Module}`; `Module` has `allPorts`, `allInsts`, `allNets` (dicts by name) and its
instances are `ModuleInst` (`name`, `cell_name`); `ModulePort`/`ModuleNet` carry `name`, `direction`,
`l_bit`, `r_bit`, and a net also `is_power`/`is_ground`. `saveNetlist(path)` writes out the netlist
the parse *built* — with `ignore_conn=True` that is the modules and instances, without connections.

`InstExtractor` is the one most callers want — a flattened netlist, no placement:

```python
ex = InstExtractor("sample_data/eda/core.v", "core")
len(ex.insts)                       # 3724
list(ex.insts.items())[:2]
# [('u0/b0/and2_x1_svt_1', 'AND2_X1_SVT'), ('u0/b0/or2_x1_lvt_2', 'OR2_X1_LVT')]
```

`nl_file` is one path **or a list of them**: a netlist is normally split one module per file, so
every file's modules are merged into one lookup before the walk and the result is a single design.
Keys are hierarchical paths joined with `/`, built from the instantiation chain. A module defined in
more than one file is a broken netlist and is reported on stdout (first definition wins). There is no
placement here — a netlist has none — so nothing in this layer can tell you where an instance is.

### Shared helpers

`from vlsi_viewer.parsers import Cancelled`; `from vlsi_viewer.parsers._util import readFile, Print`.
`readFile(path)` returns the text of a file, transparently gunzipping a `.gz` name — and falling back
to a plain read when the file is merely *named* `.gz`. `Cancelled` is not an error: a caller that asks
for the stop is expected to use the partial result.

---

## Layer 2 — `parsers.convert`: the viewer's own JSON structures

This is the interface to prefer for "give me the instances". Every function returns plain `dict`s in
the same shape the `json` subcommand reads (see the [Input format](README.md#input-format) tables in
the README for the full attribute list), so anything built from them can also be dumped to JSON and
re-read by this project or by you.

```python
cells, pins = cell_info_from_lef(["sample_data/eda/cells.lef"], with_pins=True)
# cells: {cell_name: {"area": 0.4, "size_x": 0.4, "size_y": 1.0, "is_inverter": True, ...}}
# pins:  {cell_name: [(x, y), ...]}   signal pins only, in microns, with USE POWER/GROUND dropped

block = instance_info_from_def("sample_data/eda/core.def")
# block: {"top_name": "core", "boundary": [[x, y], ...], "instances": {...}}
# block["instances"]["smem_0"]
#   {"cell_name": "SRAM_512", "location_x": 6.0, "location_y": 74.0, "orient": "N"}

netlist = instance_info_from_verilog(["sample_data/eda/core.v"], "core")
# block: {"top_name": "core", "instances": {...}}   no boundary: a netlist has no placement
# netlist["instances"]["smem_0"] -> {"cell_name": "SRAM_512"}
```

| function | notes |
|---|---|
| `cell_info_from_lef(lef_paths, with_obstructions=False, with_pins=False)` | the cell library. Every macro is emitted, filler and tap included (their size is what draws their area). With `with_pins` it returns `(cells, pins)` where `pins` is the signal-pin **centres** per cell — one `(x, y)` per pin, power and ground already dropped. With `with_obstructions` it returns `(cells, obstructions)` keyed by cell and then by layer, for macros that declare `OBS` only (a standard cell's `OBS` is pin access, not a keep-out). The two flags are mutually exclusive and raise. The name heuristics (buffer/inverter/Vt/bit count/drive size) are library conventions in one table at the top of `convert.py` — edit them for another library |
| `instance_info_from_def(def_path, top=None)` | one block per DEF. **Coordinates are converted to microns** (divided by the DEF's own database unit). `top` overrides the `DESIGN` name; without either, a DEF with no `DESIGN` raises. `FILL*` components are dropped (they tile every row gap and would peg a density map at 100 %) and `UNPLACED` ones are skipped (the parser keeps them at (0, 0), which would pile them on the die origin) |
| `instance_info_from_verilog(verilog_paths, top)` | one block, flattened to instance-name paths, `cell_name` only — no `boundary`, hence no placement |
| `fill_instances(blocks, json_paths)` | fills instance attributes from `instance_info.json` files into converted blocks, in place (leakage/dynamic power in practice), matching records by hierarchy path. See `dev_plan/power_json_fill.md` |

Both converters log what they dropped (`logger.info`), and warn on a DEF whose declared component
count does not match what parsed, or one that omits `UNITS`.

---

## Layer 3 — `parsers.routing`: layers, and a DEF's wires as shapes

For anything geometric. Values here are **microns**, and every shape has already been classified
(routing layer or not, signal or power), filtered (a jog shorter than the layer's rule), expansion
done (each wire grown by half its spacing) and handed over as four coordinate arrays.

```python
tech = TechRouting.read(["sample_data/metal/tech.lef"])
len(tech)                                  # 12 - only TYPE ROUTING layers are kept
tech["M1"]                                 # RouteLayer(M1, HORIZONTAL, pitch=0.14, w=0.07, s=0.07)
[l.name for l in tech.usable]              # layers with a width rule, i.e. measurable
```

`TechRouting.read(paths)` drops non-routing layers (a real tech LEF is about half cut/masterslice
layers) and `LEF58_REGION` ones (their metal would be counted twice), keeps the file's stack order,
and derives a missing spacing from `pitch - width`. A `RouteLayer` has `name`, `index` (its position
in this stack), `direction`, `pitch`, `width`, `spacing`, `usable`, and `is_horizontal`.
`tech.trimmed(lo, hi)` returns a stack restricted to 1-based positions, remembering what it dropped
and how many were below it. `SIGNAL = 0` and `POWER = 1` are the scope constants you will see.

```python
class CollectingSink:
    """The whole sink interface: one method per shape kind, called from `ShapeStream.flush`."""

    def __init__(self):
        self.rects = 0
        self.first = None

    def add_rects(self, layer_index, scope, x0, y0, x1, y1):
        self.rects += len(x0)                        # four float64 arrays, in microns
        if self.first is None:
            self.first = (layer_index, scope, x0[:2], y0[:2])

    def add_diagonal(self, layer_index, scope, x0, y0, x1, y1, half):
        ...                                          # scalars: a 45-degree segment and its half width

    def add_polygon(self, layer_index, scope, exterior):
        ...                                          # one (n, 2) ring array, in microns


tech = TechRouting.read(["sample_data/metal/tech.lef"])
sink = CollectingSink()
stream = ShapeStream(tech, sink)                     # frames=() : the block's own coordinates
routing = parse_def("sample_data/metal/sub.def", stream=stream)
stream.flush()                                       # nothing arrives before this
sink.rects                                           # 19817
sink.first                                           # (0, 1, array([1.965, 1.965]), array([2.195, 10.682]))
```

- **`parse_def(def_path, stream=None, top=None, skip_components=False, cancel=None, lines=None, puts=None) -> DefRouting`**
  always enables net, special-net and rule parsing, compares the declared section counts against what
  parsed (warning on a mismatch, because a section placed after the parser's stopping point would
  otherwise be lost silently), and returns `design_name`, `db_unit`, `boundary` (microns),
  `components` (as the parser produced them, still in database units), `tracks` (**also still in
  database units** — the class docstring says otherwise, the code does not scale them: divide by
  `db_unit`), `ndrs` (these *are* scaled to microns) and `stats`. `skip_components=True` is for a
  caller that already read them — it still scans the section but stops building a `DefComponent` per
  instance.
- **Shapes arrive in batches**, from `ShapeStream.flush()` — either your explicit call or the stream's
  own batch threshold. Nothing is delivered before that, which is the one thing to remember when
  wiring a sink: forget `flush()` and every count is zero.
- `ShapeStream(tech, sink, db_unit=None, ndrs=None, frames=None, batch=..., min_segment=None)`:
  `frames` places the shapes — each entry needs `apply_rect(x0, y0, x1, y1)`,
  `apply_point(x, y)` and `apply_points(xs, ys)` (`vlsi_viewer.assembly.Frame` implements that).
  A *list*, because a block placed four times is parsed once and emitted four times. `min_segment`
  drops non-preferred-direction jogs shorter than the given length (`None` = each layer's own pitch).
  `db_unit`/`ndrs` normally come from `parse_def` itself, which configures the stream on the first
  net.
- **`stream.on_batch = callback`** hands each batch over *before* any frame is applied, in the DEF's
  own integer database units; **`stream.add_batch(kind, layer_index, scope, packed)`** puts such a
  batch back for the next flush. That pair is how this project stores a block's geometry in a db and
  replays it under different frames later; see `dev_plan/metal_def_db.md`.

---

## Quirks and limits worth knowing before you rely on this

Verified against the code and the committed samples; the sources are the parser docstrings and
`tests/test_parsers_eda.py`, which pins most of them.

- **Two attribute/method shadowings.** `DefParser.designName` is a `str`, not a call;
  `TlefParser(path).layers` is a `dict`, not a call. Everything else in the tables above is a method.
- **Parsing is eager** (`DefParser`, `LefParser`, `TlefParser`, `VerilogParser`, `InstExtractor` all
  read their inputs in the constructor). Budget for that, and pass a `sink` when the wiring is large.
- **A `*` coordinate carries the last point used in the same statement**, not the last one in the
  file. If you re-read statements yourself, keep them whole.
- **A component statement wrapped over several lines is skipped**, silently by the parser — the
  converter compares the declared `COMPONENTS n ;` count against what parsed and warns.
- **`ROWS` and `SITE` are not parsed**, so row height and site pitch are unavailable. Track pitch is
  (`getTracks()`, in database units).
- **Track and component numbers keep the DEF's own units** wherever you get them: `DefParser`
  reports them raw, and `DefRouting.tracks` does too, despite its docstring saying they are
  normalised. `DefRouting.ndrs` and `boundary` are the two that are scaled. When in doubt, divide by
  `db_unit`.
- **The LEF parser keeps one RECT per pin**: a `LefPin`'s `shape` is the *last* RECT the pin
  declared, not the whole pin. `centre` is the centre of the union of all of them, which is why it
  exists. Its loops also have no index bounds, so an unterminated `MACRO` raises `IndexError`.
- **DEF without `UNITS`** falls back to 2000 database units per micron and warns (in the converter).
  An unrecognised `TRACKS` clause is reported and skipped rather than aborting.
- **`.gz` works** for DEF and Verilog paths, in `DefParser` and `readFile`. A file that is merely
  *named* `.gz` is read as plain text.
- **Via points and `VIRTUAL` connections are counted, not built**; `+ POLYGON` rings survive whole in
  `DefNet.polygons` while `swiring` holds only their edges.
- **Only LEF/DEF/Verilog as produced by the tools this was written against has been exercised** —
  DEF 5.8, LEF with `LEF58` properties, gate-level Verilog. Behaviour on other dialects is a gap,
  not a guarantee.

## Where these are used inside this project

`cli.py` → `convert.py` → the tree and the physical heat maps; `convert.py` + `routing.py` →
`metal.py` for the wire-density maps; `assign`-free, no global state, so importing one layer does not
start anything. The tests that pin each behaviour: `tests/test_parsers_eda.py` (the converters and
their quirks), `tests/test_routing.py` and `tests/test_tech_lef.py` (layers and their rules),
`tests/test_def_nets.py` and `tests/test_def_ndr.py` (net and rule statements), `tests/test_merge.py`
(hierarchy from several blocks).
