from __future__ import annotations

import typing
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

from .verilogBaseObj import VerilogBaseObj
from .moduleNet import ModuleNet
from .compileRe import CompiledRe
from .._util import Print

if typing.TYPE_CHECKING:
    from .module import Module


class ModuleInstTerm(VerilogBaseObj):

    def __init__(self, term_name: AnyStr, nets_string: AnyStr):
        super().__init__()
        self.name = term_name
        self.__nets: List[ModuleNet] = []
        self.parseNets(nets_string=nets_string)

    def parseNets(self, nets_string: AnyStr):
        for name in nets_string.replace(' ', '').replace('{', '').replace('}', '').split(','):
            net_match = CompiledRe.re_net.match(name)
            if net_match:
                match_dict = net_match.groupdict()
                l_bit = match_dict['l_bit']
                r_bit = match_dict['r_bit']
                net_name = match_dict['base_name']
                moduleNet = ModuleNet(net_name)
                moduleNet.l_bit = l_bit
                moduleNet.r_bit = r_bit
                self.__nets.append(moduleNet)
            elif name == r"1'b1":
                moduleNet = ModuleNet(ModuleNet.POWER)
                self.__nets.append(moduleNet)
            elif name == r"1'b0":
                moduleNet = ModuleNet(ModuleNet.GROUND)
                self.__nets.append(moduleNet)
            elif name != '':
                Print(f'ERROR: Unrecognized net_conn pattern {name} in {nets_string}')

    def granulate(self, pModule: Module, cModule: Module) -> Iterable[Tuple[str, Union[str, int]]]:
        net_list = []
        for net in self.__nets:
            if net.is_power is True:
                net_list.append(1)
            elif net.is_ground is True:
                net_list.append(0)
            elif net.l_bit is None and net.r_bit is None:
                try:
                    for ii in pModule.net(net.name).granulate():
                        net_list.append(ii)
                except KeyError:
                    for ii in pModule.port(net.name).granulate():
                        net_list.append(ii)
            elif net.l_bit is not None and net.r_bit is None:
                net_list.append(f'{net.name}[{net.l_bit}]')
            elif net.l_bit is not None and net.r_bit is not None:
                for ii in net.granulate():
                    net_list.append(ii)
        return zip(cModule.port(self.name).granulate(), net_list)

    @property
    def allNets(self) -> typing.List[ModuleNet]:
        return self.__nets




