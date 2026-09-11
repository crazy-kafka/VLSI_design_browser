from __future__ import annotations

import typing
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

from .verilogBaseObj import VerilogBaseObj
from .compileRe import CompiledRe
from .moduleInstTerm import ModuleInstTerm


class ModuleInst(VerilogBaseObj):

    def __init__(self, inst_name: AnyStr, ref_name: AnyStr, pin_conn_str: str):
        super().__init__()
        self.name = inst_name
        self.__cell_name = ref_name
        self.__term: Dict[str, ModuleInstTerm] = {}
        if pin_conn_str:
            self.parsePinConn(pin_conn_str=pin_conn_str)

    def parsePinConn(self, pin_conn_str: str):
        for match in CompiledRe.re_pin_net_conn.findall(pin_conn_str):
            term_name = match[0]
            nets_by_name = match[1]
            self.__term[term_name] = ModuleInstTerm(term_name=term_name, nets_string=nets_by_name)

    def term(self, term_name: str) -> ModuleInstTerm:
        return self.__term[term_name]

    @property
    def cell_name(self) -> str:
        return self.__cell_name

    @property
    def allTerms(self) -> Dict[str, ModuleInstTerm]:
        return self.__term

    def __repr__(self):
        return f'''
ModuleInst {self.name}
    ref_name {self.__cell_name}
    term_cnt {len(self.__term.keys())}
'''



