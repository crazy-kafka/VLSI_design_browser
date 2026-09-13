from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

from .._util import Print
from .verilogParser import VerilogParser


class InstExtractor:
    """Flatten a gate-level netlist to ``{hierarchical path: leaf cell_name}``.

    ``nl_file`` is one path or several. A netlist is normally split across files (one
    per module, or one per block), so the modules from every file are merged into one
    lookup before the walk, and the result is a single design.
    """

    def __init__(self, nl_file: Union[AnyStr, Iterable[AnyStr]], top_name: AnyStr):
        self.top_name = top_name
        self.modules: Dict[AnyStr, object] = {}
        duplicates = []
        for path in self.__paths(nl_file):
            for name, module in VerilogParser(verilog_file=path,
                                              ignore_conn=True).allModules().items():
                if name in self.modules:
                    duplicates.append(name)
                    continue
                self.modules[name] = module
        if duplicates:
            # A module defined twice is a broken netlist; say so rather than let the
            # result depend silently on file order.
            unique = sorted(set(duplicates))
            Print(f'WARNING: {len(unique)} module(s) defined in more than one file; '
                  f'keeping the first definition: {", ".join(unique[:5])}'
                  + (' ...' if len(unique) > 5 else ''))
        self.insts = {}
        self.__deriveInsts(self.top_name)

    @staticmethod
    def __paths(nl_file) -> List[AnyStr]:
        """A single path or an iterable of them - a plain string is one file."""
        if isinstance(nl_file, (str, bytes)):
            return [nl_file]
        return list(nl_file)

    def __deriveInsts(self, current_module: AnyStr, current_hierarchy=''):
        for inst in self.modules[current_module].allInsts.values():
            if inst.cell_name in self.modules:
                if current_hierarchy:
                    self.__deriveInsts(inst.cell_name, f'{current_hierarchy}/{inst.name}')
                else:
                    self.__deriveInsts(inst.cell_name, f'{inst.name}')
            else:
                if current_hierarchy:
                    self.insts[current_hierarchy + '/' + inst.name] = inst.cell_name
                else:
                    self.insts[current_hierarchy + inst.name] = inst.cell_name
