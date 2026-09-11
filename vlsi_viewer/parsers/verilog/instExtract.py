from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

from .verilogParser import VerilogParser


class InstExtractor:

    def __init__(self, nl_file: AnyStr, top_name: AnyStr):
        self.parser = VerilogParser(verilog_file=nl_file, ignore_conn=True)
        self.top_name = top_name
        self.insts = {}
        self.__deriveInsts(self.top_name)

    def __deriveInsts(self, current_module: AnyStr, current_hierarchy=''):
        for inst in self.parser.module(current_module).allInsts.values():
            if inst.cell_name in self.parser.allModules():
                if current_hierarchy:
                    self.__deriveInsts(inst.cell_name, f'{current_hierarchy}/{inst.name}')
                else:
                    self.__deriveInsts(inst.cell_name, f'{inst.name}')
            else:
                if current_hierarchy:
                    self.insts[current_hierarchy + '/' + inst.name] = inst.cell_name
                else:
                    self.insts[current_hierarchy + inst.name] = inst.cell_name


