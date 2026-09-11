import os
import sys
import os
import re
from typing import TYPE_CHECKING
import tkinter
import json

_DIR_ = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))

if TYPE_CHECKING:
    from chipV.LEF import LefParser
    from chipV.DEF import DefParser
    from chipV.verilog import verilogParser
    from chipV.LEF.lefMacro import LefMacro
else:
    sys.path.append(f'{_DIR_}/chipV')
    from LEF import LefParser
    from DEF import DefParser
    from verilog import verilogParser
    from LEF.lefMacro import LefMacro

tcl = tkinter.Tcl()
tcl.eval('source /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/PDS/PDSSetup_N+3_956_C_tlef_update.tcl')
all_lef = tcl.getvar('gaPDSSesign(linc_core_clamp_wrap,LeFRef)').strip().split()

for lef in all_lef:
    print(lef)

parser = LefParser(lef_list=all_lef)
cell_info = {}
for cell_name, macro_obj in parser.getMacros().items():
    area = 0.0
    size_x = 0.0
    size_y = 0.0
    is_combinational_cell = False
    is_pulse_latch = False
    is_register_cell = False
    register_bit_count = 0
    drive_size = 0
    is_SVT = False
    is_LVT = False
    is_ULVT = False
    is_sram = False
    is_macro = False
    is_buffer = False
    is_inverter = False
    is_clock_cell = False
    is_integrated_clock_gating_cell = False

    size_x, size_y = macro_obj.size()
    area = size_x * size_y

    if re.search(r'FILL|BOUNDARY|BHD|ANTENNA|DCAP|TIE|TAP|GDCAP|HDDI', cell_name):
        continue

    if macro_obj.macroClass() == "CORE":
        if re.search(r'^BUF|CKBD', cell_name):
            is_buffer = True
        elif re.search(r'^INV|CKND', cell_name):
            is_inverter = True
        if re.search(r'^CK|^DCCK', cell_name):
            is_clock_cell = True
        if re.search(r'^CKLN', cell_name):
            is_integrated_clock_gating_cell = True
        if 'PUL' in cell_name:
            is_pulse_latch = True
        else:
            is_pulse_latch = False
        if 'SDF' in cell_name or 'LN' in cell_name or 'LH' in cell_name:
            is_combinational_cell = False
        else:
            is_combinational_cell = True
        if 'SDF' in cell_name:
            is_register_cell = True
            register_bit_count = 1
        if cell_name.endswith(('CPDULVT')):
            is_ULVT = True
        elif cell_name.endswith(('CPDLVT')):
            is_LVT = True
        elif cell_name.endswith(('CPDSVT')):
            is_SVT = True
        if match := re.search(r'^MB(d)', cell_name):
            register_bit_count = int(match.group(1))
        # print(cell_name)

        if drive_match := re.search(r'D(\d+)(?:PUL)?COT.*VT', cell_name):
            drive_size = int(drive_match.group(1))
        # print(cell_name, drive_size)

        if drive_size == 0:
            print(f'Cannot find drive size for {cell_name}')
        else:
            is_macro = True
            if 'SRAM' in cell_name:
                is_sram = True

    cell_info[cell_name] = {
        'area': area,
        'size_x': size_x,
        'size_y': size_y,
        'is_combinational_cell': is_combinational_cell,
        'is_pulse_latch': is_pulse_latch,
        'is_register_cell': is_register_cell,
        'register_bit_count': register_bit_count,
        'drive_size': drive_size,
        'is_SVT': is_SVT,
        'is_LVT': is_LVT,
        'is_ULVT': is_ULVT,
        'is_sram': is_sram,
        'is_macro': is_macro,
        'is_buffer': is_buffer,
        'is_inverter': is_inverter,
        'is_clock_cell': is_clock_cell,
        'is_integrated_clock_gating_cell': is_integrated_clock_gating_cell,
    }

out_file = 'NP1PP_cell_info.json'
with open(out_file, 'w') as fh:
    json.dump(cell_info, fh, indent=2)