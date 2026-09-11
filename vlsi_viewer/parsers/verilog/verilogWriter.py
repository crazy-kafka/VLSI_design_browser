from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .module import Module

from .._util import Print


class VerilogWriter:

    def __init__(self, module: Module):
        self.module = module
        self.outputs = []

    def write(self):
        self.outputs.append(f'module {self.module.name} (')
        port_def = []
        for port in self.module.allPorts.values():
            self.outputs.append(f'  {port.name},')
            if port.l_bit:
                port_def.append(f'  {port.direction} [{port.l_bit}:{port.r_bit}] {port.name};')
            else:
                port_def.append(f'  {port.direction} {port.name};')
        self.outputs[-1] = self.outputs[-1][:-1]
        self.outputs.append(f');')
        self.outputs += port_def
        self.outputs.append('endmodule')

