from __future__ import annotations

import os.path
import re
import time
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass


from .lefMacro import LefMacro
from .leflayer import LefLayer
from .compiledRe import CompiledRe
from .._util import Print, readFile


class TlefParser:

    def __init__(self, tlef: str):
        Print(f'Start parsing tech lef {tlef}')
        t0 = time.time()
        self.tlef = tlef
        self.__layers: Dict[str, LefLayer] = {}
        self.__parseStart()
        Print(f'End parsing tech lef in {round(time.time() - t0, 3)}s')

    def __parseStart(self):
        lines = readFile(self.tlef).split('\n')
        lines_len = len(lines)
        cursor = -1
        while cursor < lines_len - 1:
            cursor += 1
            if layer_match := CompiledRe.re_layer_name.search(lines[cursor]):
                lef_layer = LefLayer(layer_match['LAYER'])
                while cursor < lines_len - 1:
                    cursor += 1
                    if type_match := CompiledRe.re_layer_type.search(lines[cursor]):
                        lef_layer.type = type_match['TYPE']
                    elif direction_match := CompiledRe.re_layer_direction.search(lines[cursor]):
                        lef_layer.direction = direction_match['DIRECTION']
                    elif pitch_match := CompiledRe.re_layer_pitch_single.search(lines[cursor]):
                        lef_layer.pitch_x = float(pitch_match['PITCH'])
                        lef_layer.pitch_y = float(pitch_match['PITCH'])
                    elif pitch_match := CompiledRe.re_layer_pitch.search(lines[cursor]):
                        lef_layer.pitch_x = float(pitch_match['PITCH_X'])
                        lef_layer.pitch_y = float(pitch_match['PITCH_Y'])
                    elif width_match := CompiledRe.re_layer_width.search(lines[cursor]):
                        lef_layer.width = float(width_match['WIDTH'])
                    elif min_width_match := CompiledRe.re_layer_min_width.search(lines[cursor]):
                        lef_layer.min_width = float(min_width_match['MINWIDTH'])
                    elif max_width_match := CompiledRe.re_layer_max_width.search(lines[cursor]):
                        lef_layer.max_width = float(max_width_match['MAXWIDTH'])
                    elif spacing_match := CompiledRe.re_layer_spacing.search(lines[cursor]):
                        lef_layer.spacing = float(spacing_match['SPACING'])
                    elif area_match := CompiledRe.re_area.search(lines[cursor]):
                        lef_layer.area = float(area_match['AREA'])
                    elif LEF58_type_match := CompiledRe.re_LEF58_type.search(lines[cursor]):
                        lef_layer.type = LEF58_type_match['TYPE']
                    elif LEF58_region_match := CompiledRe.re_LEF58_region.search(lines[cursor]):
                        lef_layer.region = LEF58_region_match['REGION']
                        lef_layer.based_layer = LEF58_region_match['BASEDLAYER']
                    elif re.search(rf'END\s+{lef_layer.name}', lines[cursor]):
                        break
                self.__layers[lef_layer.name] = lef_layer
            elif macro_match := CompiledRe.re_macro_start.search(lines[cursor]):
                macro_end = f'END {macro_match.group(1)}'
                while cursor < lines_len - 1:
                    cursor += 1
                    if macro_end in lines[cursor]:
                        break
            elif property_definitions_match := CompiledRe.re_property_definitions.search(lines[cursor]):
                while cursor < lines_len - 1:
                    cursor += 1
                    if CompiledRe.re_end_property_definitions.search(lines[cursor]):
                        break
            elif via_match := CompiledRe.re_via.search(lines[cursor]):
                while cursor < lines_len - 1:
                    cursor += 1
                    if re.search(rf'^\s*END\s+{via_match["VIA"]}', lines[cursor]):
                        break
            elif via_rule_match := CompiledRe.re_via_rule.search(lines[cursor]):
                while cursor < lines_len - 1:
                    cursor += 1
                    if re.search(rf'^\s*END\s+{via_rule_match["VIARULE"]}', lines[cursor]):
                        break

    @property
    def layers(self) -> Dict[str, LefLayer]:
        return self.__layers


class LefParser:

    def __init__(self, lef_list: List[str]):
        Print(f'Start parsing Lef files')
        Print(f'Total {lef_list.__len__()} LEF files')
        t0 = time.time()
        self.__macro_list = []
        self.__macro_dict = {}
        self.lef_list = lef_list
        for lef in lef_list:
            Print(f'Parsing {lef}')
            self.extractMacroInfo(self.getAllLefLines([lef]))
        #self.cf_lines = self.getAllLefLines(self.lef_list)
        #self.extractMacroInfo(self.cf_lines)
        #del self.cf_lines
        Print(f'End parsing {len(self.lef_list)} LEF file in {round(time.time() - t0, 3)}s')

    def getMacros(self) -> Dict[str, LefMacro]:
        return self.__macro_dict

    def getMacro(self, macro_name: str) -> LefMacro:
        return self.__macro_dict[macro_name]

    def extractMacroInfo(self, lef_lines):
        self.lines_len = len(lef_lines)
        cursor = 0
        while cursor < self.lines_len:
            macro_match = CompiledRe.re_macro_start.search(lef_lines[cursor])
            if macro_match:
                macro_name = macro_match.group(1)
                macro_end = f'END {macro_name}'
                this_macro = LefMacro(macro_name)
                input_pin_num = 0
                out_pin_num = 0
                inout_pin_num = 0
                cursor += 1
                while macro_end not in lef_lines[cursor]:
                    match_class = CompiledRe.re_class.search(lef_lines[cursor])
                    if match_class:
                        this_macro.setClassType(match_class.group(1))
                    match_size = CompiledRe.re_size.search(lef_lines[cursor])
                    if match_size:
                        width = float(match_size.group(1))
                        height = float(match_size.group(2))
                        this_macro.setSize(width, height)
                    else:
                        pin_name_match = CompiledRe.re_pin_start.search(lef_lines[cursor])
                        if pin_name_match:
                            pin_name = pin_name_match.group(1)
                            pin_end = f'END {pin_name}'
                            cursor += 1
                            direction = 'UNKNOWN'
                            use = 'SIGNAL'
                            layer = 'UNKNOWN'
                            shape = [(0.0, 0.0), (0.0, 0.0)]
                            while pin_end not in lef_lines[cursor]:
                                direction_match = CompiledRe.re_direction.search(lef_lines[cursor])
                                if direction_match:
                                    direction = direction_match.group(1)
                                    cursor += 1
                                    continue
                                use_match = CompiledRe.re_use.search(lef_lines[cursor])
                                if use_match:
                                    use = use_match.group(1)
                                    cursor += 1
                                    continue

                                layer_match = CompiledRe.re_layer.search(lef_lines[cursor])
                                if layer_match:
                                    layer = layer_match.group(1)
                                    cursor += 1
                                    continue

                                pin_shape_match = CompiledRe.re_rect.search(lef_lines[cursor])
                                if pin_shape_match:
                                    shape = [(float(pin_shape_match.group(1)),
                                            float(pin_shape_match.group(2))),
                                            (float(pin_shape_match.group(3)),
                                            float(pin_shape_match.group(4)))]
                                    cursor += 1
                                    continue
                                cursor += 1

                            if use == "POWER" or use == "GROUND":
                                direction = 'INOUT'
                                inout_pin_num += 1
                            else:
                                if direction == 'INPUT':
                                    input_pin_num += 1
                                elif direction == 'OUTPUT':
                                    out_pin_num += 1
                                elif direction == 'INOUT':
                                    inout_pin_num += 1

                            this_macro.setPin(pin_name, direction, use, layer, shape)
                    cursor += 1
                this_macro.setInputPinNum(input_pin_num)
                this_macro.setOutputPinNum(out_pin_num)
                this_macro.setInoutPinNum(inout_pin_num)
                self.__macro_list.append(this_macro)
                self.__macro_dict.update({macro_name: this_macro})
            else:
                cursor += 1

    @staticmethod
    def getAllLefLines(lef_list):
        lef_lines = []
        for lef in lef_list:
            with open(os.path.realpath(lef) , 'r') as lef_f:
                lef_lines += lef_f.readlines()
        return lef_lines

    def __repr__(self):
        return f'''
LEF parser
    Total Macro {len(self.__macro_dict)}
'''





