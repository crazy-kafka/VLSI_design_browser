from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass

import re
import gzip
import time
from .compiledRe import CompiledRe
from .defTrack import DefTrack
from .defComponent import DefComponent
from .defBlockage import DefBlockage
from .defPin import DefPin
from .defNet import DefNet
from .defWire import DefWire
from .defSWire import DefSWire
from .._util import Print


class DefParser:

    CURRENT_LINE_CNT = 0
    LINE_CNT_STEP = 1000000
    IGNORE_PHY = False
    IGNORE_FILLER = False
    IGNORE_COVER = False

    def __init__(self, def_file: AnyStr, skip_comp=False, parse_pin=False, batch_mode=False, parse_net=False, parse_blockage=False, parse_specialnet=False):
        if batch_mode is True:
            self.puts = print
        else:
            self.puts = Print
        self.puts(f'Load DEF file {def_file}')
        self.def_file = def_file

        self.skip_comp = skip_comp
        self.parse_pin = parse_pin
        self.parse_net = parse_net
        self.parse_blockage = parse_blockage
        self.parse_specialnet = parse_specialnet

        if self.def_file.endswith('.gz'):
            self.fh = gzip.open(self.def_file)
            self.fetchLine_method = self.fetchLineGz
        else:
            self.fh = open(self.def_file)
            self.fetchLine_method = self.fetchLine

        self.__design_name = ''
        self.__db_unit = 2000
        self.__components: Dict[AnyStr, DefComponent] = {}
        self.__nets: Dict[AnyStr, DefNet] = {}
        self.__pins: Dict[AnyStr, DefPin] = {}
        self.__blockages: List[DefBlockage] = []
        self.__die_area: List[Tuple[int, int]] = []
        self.__tracks: List[DefTrack] = []
        self.__height = 0
        self.__width = 0

        self.__parsingStart()

        self.fh.close()
        delattr(self, 'fh')

    def __parsingStart(self):
        t0 = time.time()
        func_dict = {
            'DESIGN': self.__extractDesignName,
            'UNITS': self.__extractDbUnit,
            'PROPERTYDEFINITIONS': self.__extractPropertyDefinition,
            'DIEAREA': self.__extractDieSize,
            'TRACKS': self.__extractTracks,
            'COMPONENTS': self.__extractComponents,
            'PINS': self.__extractPins,
            'BLOCKAGES': self.__extractBlockages,
            'SPECIALNETS': self.__extractSpecialNets,
            'NETS': self.__extractNets
        }
        if self.skip_comp:
            del func_dict['COMPONENTS']
        if self.parse_pin is False:
            del func_dict['PINS']
        if self.parse_blockage is False:
            del func_dict['BLOCKAGES']
        if self.parse_specialnet is False:
            del func_dict['SPECIALNETS']
        if self.parse_net is False:
            del func_dict['NETS']
        last_type = list(func_dict.keys())[-1]
        while True:
            line = self.fetchLine_method()

            if not line or CompiledRe.re_end_design.search(line):
                break
            for mtype in func_dict:
                if line.startswith(mtype):
                    func_dict[mtype](line)
                    if mtype == last_type:
                        self.puts(f'End DEF parsing in {round(time.time() - t0, 4)}s')
                        return
                    continue

    def __extractDesignName(self, line: AnyStr):
        design_match = CompiledRe.re_design.search(line)
        self.__design_name = design_match.groupdict()['design']

    def __extractDbUnit(self, line: AnyStr):
        db_unit_match = CompiledRe.re_db_unit.search(line)
        self.__db_unit = int(db_unit_match.groupdict()['unit'])

    def __extractPropertyDefinition(self, line: AnyStr):
        while True:
            if not line or CompiledRe.re_end_design.search(line):
                return
            if CompiledRe.re_end_property_definition.search(line):
                return
            line = self.fetchLine_method()

    def __extractDieSize(self, line: AnyStr):
        flag_on = False
        die_lines = []
        while True:
            if not line or CompiledRe.re_end_design.search(line):
                break
            if re.search(r'DIEAREA\s+\(', line):
                flag_on = True
            if flag_on:
                die_lines.append(line)
                if ';' in line:
                    break
            line = self.fetchLine_method()
        die_part = ''.join(die_lines)
        self.__die_area = [(int(ii[0]), int(ii[1])) for ii in CompiledRe.re_pt.findall(die_part)]
        if len(self.__die_area) < 3:
            x0 = self.__die_area[0][0]
            y0 = self.__die_area[0][1]
            x1 = self.__die_area[1][0]
            y1 = self.__die_area[1][1]
            self.__shape = [
                (x0, y0),
                (x0, y1),
                (x1, y1),
                (x1, y0)
            ]
        else:
            self.__shape = self.__die_area
        self.__deriveHeightWidth()

    def __extractTracks(self, line: AnyStr):
        track_match = CompiledRe.re_track.search(line)
        layer_name = track_match['layer']
        direction = track_match['direction']
        offset = int(track_match['offset'])
        step = int(track_match['step'])
        mask = int(track_match['mask_num']) if track_match['mask_num'] else 0
        self.__tracks.append(DefTrack(layer_name, direction, offset, step, mask))

    def __extractComponents(self, line: AnyStr):
        while True:
            if not line or CompiledRe.re_end_component.search(line):
                break
            if self.skip_comp is False:
                match = CompiledRe.re_component.search(line)
                if match:
                    match_dict = match.groupdict()
                    if match_dict['pstatus'] == 'UNPLACED':
                        match_dict['x'] = 0
                        match_dict['y'] = 0
                        match_dict['orient'] = 'N'
                    else:
                        match_dict['x'] = int(match_dict['x'])
                        match_dict['y'] = int(match_dict['y'])
                    component = DefComponent(
                        comp_name=match_dict['compName'],
                        model_name=match_dict['modelName'],
                        source=match_dict['source'],
                        pstatus=match_dict['pstatus'],
                        x=match_dict['x'],
                        y=match_dict['y'],
                        orient=match_dict['orient']
                    )
                    if self.__compFilter(component):
                        self.__components[component.comp_name] = component
            line = self.fetchLine_method()

    def __compFilter(self, comp: DefComponent) -> bool:
        flag = True
        model = comp.model_name
        if self.IGNORE_PHY is True and comp.source == 'DIST':
            flag = False
        if self.IGNORE_FILLER is True and (model.startswith('FILL') or model.startswith('DCAP') or model.startswith('GDCAP')):
            flag = False
        if self.IGNORE_PHY is True and comp.pstatus == 'COVER':
            flag = False
        return flag

    def __extractPins(self, line: AnyStr):
        while True:
            line = self.fetchLine_method()
            if not line or CompiledRe.END_PIN in line:
                break
            pin_string = line
            match = CompiledRe.re_pin.search(pin_string)
            if match:
                self._addPin(match)
            while line and ';' not in line:
                line = self.fetchLine_method()
                pin_string += line.replace('\n', '')
                match = CompiledRe.re_pin.search(pin_string)
                if match:
                    self._addPin(match)

    def _addPin(self, match):
        pin = DefPin(
            pin_name=match['pin_name'],
            direction=match['direction'],
            layer=match['layer'],
            pstatus=match['pstatus'],
            x=int(match['x2']),
            y=int(match['y2']),
            orient=match['orient']
        )
        self.__pins[pin.pin_name] = pin

    def __extractBlockages(self, line: AnyStr):
        blockage_lines = []
        while True:
            if not line or 'END BLOCKAGES' in line:
                break
            blockage_lines.append(line)
            line = self.fetchLine_method()
        content = ''.join(blockage_lines).replace('\n', '')
        for line in content.split(';'):
            blk_match = CompiledRe.re_blockage.search(line)
            if blk_match:
                layer_name = blk_match.groupdict()['layer_name']
                shape_type = blk_match.groupdict()['shape_type']
                pts = [(int(ii[0]), int(ii[1])) for ii in CompiledRe.re_pt.findall(line)]
                self.__blockages.append(DefBlockage(layer_name, shape_type, pts))

    def __extractSpecialNets(self, line: AnyStr):
        while True:
            if not line or 'END SPECIALNETS' in line:
                break
            net_match = CompiledRe.re_net.search(line)
            if net_match:
                net_name = net_match.groupdict()['net_name']
                if net_name in self.__nets:
                    net = self.__nets[net_name]
                else:
                    net = DefNet(net_name)
                    self.__nets[net_name] = net
                while True:
                    wiring_match = CompiledRe.re_special_wiring.search(line)
                    if wiring_match:
                        match_dict = wiring_match.groupdict()
                        for k, v in match_dict.items():
                            if isinstance(v, str) and v.isdigit():
                                match_dict[k] = int(v)
                            elif v is None and k in ['e0', 'e1']:
                                match_dict[k] = 0
                        if match_dict['x0'] == '*':
                            match_dict['x0'] = match_dict['x1']
                        elif match_dict['x1'] == '*':
                            match_dict['x1'] = match_dict['x0']
                        if match_dict['y0'] == '*':
                            match_dict['y0'] = match_dict['y1']
                        elif match_dict['y1'] == '*':
                            match_dict['y1'] = match_dict['y0']
                        net.swiring.append(DefSWire(
                            layer_name=match_dict['layer'],
                            width=match_dict['width'],
                            x0=match_dict['x0'],
                            y0=match_dict['y0'],
                            e0=match_dict['e0'],
                            x1=match_dict['x1'],
                            y1=match_dict['y1'],
                            e1=match_dict['e1'],
                            via=match_dict['via']
                        ))
                    if ';' in line:
                        break
                    line = self.fetchLine_method()
            line = self.fetchLine_method()

    def __extractNets(self, line: AnyStr):
        while True:
            if not line or 'END NETS' in line:
                break
            net_match = re.search(CompiledRe.re_net, line)
            if net_match:
                net_name = net_match.groupdict()['net_name']
                if net_name in self.__nets:
                    net = self.__nets[net_name]
                else:
                    net = DefNet(net_name)
                    self.__nets[net_name] = net
                rule = 'default'
                while True:
                    ndr_match = CompiledRe.re_ndr.search(line)
                    if ndr_match:
                        rule = ndr_match['ndr']
                    else:
                        wiring_match = CompiledRe.re_regular_wiring.search(line)
                        if wiring_match:
                            _rule = rule
                            if wiring_match['TAPER']:
                                if 'TAPERRULE' in wiring_match['TAPER']:
                                    _rule = wiring_match['TAPER'].split()[1]
                                else:
                                    _rule = 'default'
                            pts = CompiledRe.re_routing_point.findall(line)
                            for i in range(1, len(pts)):
                                from_pt, to_pt = self.__decodeWire(pts[i - 1], pts[i])
                                wire = DefWire(
                                    layer_name=wiring_match['layer'],
                                    rule=rule,
                                    from_pt=from_pt,
                                    to_pt=to_pt
                                )
                                net.wiring.append(wire)
                        else:
                            conn_match = CompiledRe.re_net_conn.findall(line)
                            if conn_match:
                                for conn in conn_match:
                                    inst_name = conn[0]
                                    term_name = conn[1]
                                    conn_pin = term_name if inst_name == 'PIN' else f'{inst_name}/{term_name}'
                                    net.connect_pins.append(conn_pin)
                    if ';' in line:
                        break
                    line = self.fetchLine_method()
            line = self.fetchLine_method()

    def __deriveHeightWidth(self):
        try:
            # Inlined from the upstream CoordinateProcess.calulateBoundingBox, which
            # returned [(min_x, min_y), (max_x, max_y)]. min() still raises ValueError
            # on an empty DIEAREA, which is what the handler below expects.
            die_pts = self.getDieArea()
            xs = [pt[0] for pt in die_pts]
            ys = [pt[1] for pt in die_pts]
            ll_pt = (min(xs), min(ys))
            ur_pt = (max(xs), max(ys))
            self.__width = ur_pt[0] - ll_pt[0]
            self.__height = ur_pt[1] - ll_pt[1]
        except ValueError:
            self.puts(f'ERROR: Got some problem when extracting die size in {self.def_file}')
            raise ValueError

    @staticmethod
    def __decodeWire(pt_0: List[AnyStr], pt_1: List[AnyStr]):
        if pt_0[0] == '*':
            x0 = pt_1[0]
            x1 = x0
        elif pt_1[0] == '*':
            x1 = pt_0[0]
            x0 = x1
        else:
            x0 = pt_0[0]
            x1 = pt_1[0]

        if pt_0[1] == '*':
            y0 = pt_1[1]
            y1 = y0
        elif pt_1[1] == '*':
            y1 = pt_0[1]
            y0 = y1
        else:
            y0 = pt_0[1]
            y1 = pt_1[1]

        return (int(x0), int(y0)), (int(x1), int(y1))

    @staticmethod
    def __isPhysicalOnly(module_name: AnyStr) -> bool:
        if 'FILL' in module_name or 'DCAP' in module_name or 'TAPCELL' in module_name or 'BOUNDARY' in module_name:
            return True
        else:
            return False

    def fetchLineGz(self) -> AnyStr:
        self.CURRENT_LINE_CNT += 1
        if self.LINE_CNT_STEP and self.CURRENT_LINE_CNT % self.LINE_CNT_STEP == 0:
            self.puts(f'Read DEF {self.CURRENT_LINE_CNT} lines')
        return self.fh.readline().decode()

    def fetchLine(self) -> AnyStr:
        self.CURRENT_LINE_CNT += 1
        if self.LINE_CNT_STEP and self.CURRENT_LINE_CNT % self.LINE_CNT_STEP == 0:
            self.puts(f'Read DEF {self.CURRENT_LINE_CNT} lines')
        return self.fh.readline()

    @property
    def designName(self) -> AnyStr:
        return self.__design_name

    def dbUnit(self) -> int:
        return self.__db_unit

    def getTracks(self) -> List[DefTrack]:
        return self.__tracks

    def getComponent(self, comp_name: AnyStr) -> DefComponent:
        return self.__components[comp_name]

    def getAllComponents(self) -> List[DefComponent]:
        return list(self.__components.values())

    def getAllPins(self) -> List[DefPin]:
        return list(self.__pins.values())

    def getPin(self, pin_name: AnyStr) -> DefPin:
        return self.__pins[pin_name]

    def getAllNets(self) -> List[DefNet]:
        return list(self.__nets.values())

    def getNet(self, net_name: AnyStr) -> DefNet:
        return self.__nets[net_name]

    def getBlockages(self) -> List[DefBlockage]:
        return self.__blockages

    def getDieArea(self) -> List[Tuple[int, int]]:
        return self.__die_area

    def shape(self) -> List[Tuple[int, int]]:
        return self.__shape

    def getHeight(self) -> int:
        return self.__height

    def getWidth(self) -> int:
        return self.__width

    def __repr__(self):
        return f'''
DEF parser for {self.def_file}
    DESIGN   {self.__design_name}
    DIESHAPE {self.__die_area}
    HEIGHT   {self.__height}
    WIDTH    {self.__width}
    INST_CNT {len(self.__components)}
    NET_CNT  {len(self.__nets)}
    PIN_CNT  {len(self.__pins)}
'''







