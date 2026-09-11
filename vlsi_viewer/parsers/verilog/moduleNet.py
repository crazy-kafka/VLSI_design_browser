from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

from .verilogBaseObj import VerilogBaseObj


class ModuleNet(VerilogBaseObj):

    POWER = 'POWER'
    GROUND = 'GROUND'

    def __init__(self, net_name: AnyStr):
        super().__init__()
        self.name = net_name
        self.l_bit = None
        self.r_bit = None
        self.__granulate = []
        self.__is_granulated = False
        self.is_power = False
        self.is_ground = False

        if self.name == self.POWER:
            self.is_power = True
        elif self.name == self.GROUND:
            self.is_ground = True

    def granulate(self) -> List[AnyStr]:
        if self.__is_granulated is False:
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
            self.__is_granulated = True
        return self.__granulate

    def __repr__(self):
        return f'''
ModuleNet "{self.name}"
    l_bit {self.l_bit}
    r_bit {self.r_bit}
'''

