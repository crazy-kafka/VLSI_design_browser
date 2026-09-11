from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

from .module import Module
from .compileRe import CompiledRe
from .verilogWriter import VerilogWriter
from .._util import readFile, Print
import time


class VerilogParser:

    def __init__(self, verilog_file: str, ignore_conn=False, target_modules=None):
        self.__modules: Dict[str, Module] = {}
        self.TARGET_MODULES = target_modules
        self.ignore_conn = ignore_conn
        self.verilog_file = verilog_file
        self.parseStart()

    def parseStart(self):
        t0 = time.time()
        Print(f'Start parsing verilog file {self.verilog_file}')
        content = readFile(self.verilog_file).replace('\n', '').replace('\t', '')
        module_str_list = CompiledRe.re_module.findall(content)
        module_str_list.sort(key=lambda x: len(x), reverse=True)
        # Print(f'Find {len(module_str_list)} modules')

        if self.TARGET_MODULES is None:
            for module in map(self.parseModule, module_str_list):
                self.__modules[module.name] = module
        else:
            for module_str in module_str_list:
                module_name = CompiledRe.re_module_name.search(module_str)['module_name']
                if module_name in self.TARGET_MODULES:
                    self.__modules[module_name] = self.parseModule(module_str)

        Print(f'End parsing of {self.verilog_file} in {round(time.time() - t0, 3)}s')

    def parseModule(self, module_string: str) -> Module:
        return Module(module_string, self.ignore_conn)

    def module(self, module_name: str) -> Module:
        return self.__modules[module_name]

    def allModules(self) -> Dict[str, Module]:
        return self.__modules

    def saveNetlist(self, out_file: AnyStr):
        with open(out_file, 'w') as fh:
            for module in self.__modules.values():
                writer = VerilogWriter(module)
                writer.write()
                fh.writelines('\n'.join(writer.outputs))
        Print(f'Write Netlist to {out_file}')

    def __repr__(self):
        return f'Verilog parser for file: {self.verilog_file}\nTotal {len(self.__modules)} module(s) parsed.'
