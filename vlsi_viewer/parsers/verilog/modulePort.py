from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

from .verilogBaseObj import VerilogBaseObj
from .._util import Print


class ModulePort(VerilogBaseObj):

    def __init__(self, port_name: AnyStr):
        super().__init__()
        self.name = port_name
        self.direction = None
        self.l_bit = None
        self.r_bit = None
        self.__granulate = []
        self.__is_granulate = False

    def granulate(self) -> List[AnyStr]:
        if not self.__is_granulate:
            if self.l_bit is None:
                self.__granulate = [self.name]
            elif self.r_bit is None:
                self.__granulate = [f'{self.name}[{self.l_bit}]']
            else:
                l_bit = int(self.l_bit)
                r_bit = int(self.r_bit)
                if l_bit < r_bit:
                    l_bit, r_bit = r_bit, l_bit
                self.__granulate = [f'{self.name}[{i}]' for i in range(l_bit, r_bit - 1, -1)]
            self.__is_granulate = True
        return self.__granulate

    def __repr__(self):
        return f'''
ModulePort "{self.name}"
    direction {self.direction}
    l_bit     {self.l_bit}
    r_bit     {self.r_bit}
'''

