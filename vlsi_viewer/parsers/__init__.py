"""Vendored LEF / DEF / Verilog parsers.

The three subpackages keep the directory names and the internal relative imports of
the project they came from, so they stay traceable to that code; only the ``utils``
import was repointed at :mod:`vlsi_viewer.parsers._util`. ``DEF`` keeps its original
spelling because ``def`` is a Python keyword and cannot be a package name.

Public entry points::

    DefParser      DEF placement (DESIGN/DIEAREA/UNITS/COMPONENTS). All coordinates
                   are raw DEF database units - divide by ``dbUnit()`` for microns.
    LefParser      macro LEF: ``getMacros()`` -> name -> LefMacro with ``size()`` in
                   microns and ``macroClass()``. ``TlefParser`` covers tech LEF layers.
    VerilogParser  module/netlist parser; ``InstExtractor`` flattens a gate-level
                   netlist to ``{hierarchical path: cell_name}`` - no placement.

See :mod:`vlsi_viewer.parsers.convert` for turning these into the viewer's JSON.
"""
from .DEF import DefParser
from .LEF import LefParser, TlefParser
from ._util import Cancelled
from .verilog import VerilogParser, InstExtractor

__all__ = ["Cancelled", "DefParser", "LefParser", "TlefParser", "VerilogParser",
           "InstExtractor"]
