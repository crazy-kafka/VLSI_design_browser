from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr, Match

if TYPE_CHECKING:
    pass

from .verilogBaseObj import VerilogBaseObj
from .compileRe import CompiledRe
from .modulePort import ModulePort
from .moduleNet import ModuleNet
from .moduleInst import ModuleInst


class Module(VerilogBaseObj):
    def __init__(self, module_string: str, ignore_conn: bool):
        super().__init__()
        self.ignore_conn = ignore_conn
        self.__ports: Dict[str, ModulePort] = {}
        self.__nets: Dict[str, ModuleNet] = {}
        self.__insts: Dict[str, ModuleInst] = {}
        self.__assigns: Dict[str, str] = {}
        self.parseString(lines=module_string.split(';')[:-1])

    def parseString(self, lines: List[str]):
        module_match = CompiledRe.re_module_declare.search(lines[0])
        self.__moduleMatch(match=module_match)
        for line in lines[1:]:
            if port_match := CompiledRe.re_port_declare.search(line):
                self.__portMatch(match=port_match)
            elif net_match := CompiledRe.re_net_declare.search(line):
                self.__netMatch(match=net_match)
            elif inst_match := CompiledRe.re_instantiate.search(line):
                self.__instMatch(match=inst_match)
            elif assign_match := CompiledRe.re_assign_declare.search(line):
                self.__assignMatch(match=assign_match)
            else:
                print(f'ERROR: Unrecognized pattern for <{line}>')

    def __assignMatch(self, match: Match):
        self.__assigns[match.groupdict()['lvalue']] = match.groupdict()['rvalue']
        self.__assigns[match.groupdict()['rvalue']] = match.groupdict()['lvalue'] 

    def __moduleMatch(self, match: Match):
        self.name = match.groupdict()['module_name']
        if match.groupdict()['ports']:
            for port_name in [ii.strip(' ') for ii in match.groupdict()['ports'].split(',')]:
                self.__ports[port_name] = ModulePort(port_name)

    def __portMatch(self, match: Match):
        for port_name in [ii.strip(' ') for ii in match['ports_name'].split(',')]:
            port = ModulePort(port_name)
            port.direction = match['direction']
            port.l_bit = match['l_bit']
            port.r_bit = match['r_bit']
            self.__ports[port_name] = port

    def __netMatch(self, match: Match):
        match_dict = match.groupdict()
        net_names = match_dict['net_name']
        #print(match_dict)
        l_bit = match_dict['l_bit']
        r_bit = match_dict['r_bit']
        for net_name in [ii.strip(' ') for ii in net_names.split(',')]:
            net = ModuleNet(net_name)
            net.l_bit = l_bit
            net.r_bit = r_bit
            self.__nets[net_name] = net

    def __instMatch(self, match: Match):
        match_dict = match.groupdict()
        ref_name = match_dict['ref_name']
        inst_name = match_dict['inst_name']
        conn = match_dict['pin_conn'] if self.ignore_conn is False else None
        self.__insts[inst_name] = ModuleInst(inst_name=inst_name, ref_name=ref_name, pin_conn_str=conn)

    def port(self, port_name: AnyStr) -> ModulePort:
        return self.__ports[port_name]

    def deleteInst(self, inst_name: AnyStr):
        if inst_name in self.__insts:
            del self.__insts[inst_name]

    @property
    def allPorts(self) -> Dict[str, ModulePort]:
        return self.__ports

    def net(self, net_name: str) -> ModuleNet:
        return self.__nets[net_name]

    @property
    def allNets(self) -> Dict[str, ModuleNet]:
        return self.__nets

    def inst(self, inst_name: str) -> ModuleInst:
        return self.__insts[inst_name]

    @property
    def allInsts(self) -> Dict[str, ModuleInst]:
        return self.__insts

    @property
    def assigns(self) -> Dict[str, str]:
        return self.__assigns

    def __repr__(self):
        return f'Module {self.name}: {len(self.__nets)} nets, {len(self.__insts)} insts, {len(self.__ports)} ports, {len(self.__assigns)} assigns'





