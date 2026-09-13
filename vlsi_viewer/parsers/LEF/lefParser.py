from __future__ import annotations

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
                cursor = self.__parseLayer(lines, cursor, layer_match['LAYER'])
            elif macro_match := CompiledRe.re_macro_start.search(lines[cursor]):
                cursor = self.__skipTo(lines, cursor, f'END {macro_match.group(1)}', raw=True)
            elif property_definitions_match := CompiledRe.re_property_definitions.search(lines[cursor]):
                cursor = self.__skipTo(lines, cursor,
                                       pattern=CompiledRe.re_end_property_definitions)
            elif via_match := CompiledRe.re_via.search(lines[cursor]):
                cursor = self.__skipTo(lines, cursor, f'END {via_match["VIA"]}')
            elif via_rule_match := CompiledRe.re_via_rule.search(lines[cursor]):
                cursor = self.__skipTo(lines, cursor, f'END {via_rule_match["VIARULE"]}')

    @staticmethod
    def __skipTo(lines, cursor, end_text=None, pattern=None, raw=False) -> int:
        """Advance past a block body, returning the index of its closing line.

        ``raw`` matches ``end_text`` anywhere in the line, which is what ``MACRO`` needs:
        its body may contain text that merely looks like a terminator.
        """
        lines_len = len(lines)
        while cursor < lines_len - 1:
            cursor += 1
            line = lines[cursor]
            if pattern is not None:
                if pattern.search(line):
                    break
            elif raw:
                if end_text in line:
                    break
            elif re.search(rf'^\s*END\s+{re.escape(end_text)}', line):
                break
        return cursor

    def __parseLayer(self, lines, cursor, name) -> int:
        """Read one ``LAYER`` stanza; return the index of its ``END`` line.

        The stanza is scanned as a nested block rather than line by line, because a
        ``SPACINGTABLE`` body is a matrix of ``WIDTH <breakpoint> <spacing>...`` rows that
        is shape-identical to the layer's own ``WIDTH`` statement - by shape alone the two
        cannot be told apart, so the table is consumed as a unit.

        Spacing is resolved after the stanza is read, not on the fly. A layer may declare
        several conditional ``SPACING`` clauses, and only the unqualified one is the
        default; taking whichever came last picks the widest-wire rule. Real tech LEFs
        break both ways silently - a layer declaring only a table ends up with no spacing
        at all, and a layer whose final clause is a conditional one ends up with a spacing
        several times too large. Either way the heat map is wrong with no error.
        """
        layer = LefLayer(name)
        lines_len = len(lines)
        widths: List[float] = []
        spacings: List[float] = []
        table_spacings: List[float] = []
        default_spacing = None
        in_table = False

        while cursor < lines_len - 1:
            cursor += 1
            line = lines[cursor]
            if re.search(rf'^\s*END\s+{re.escape(name)}\b', line):
                break

            if in_table:
                self.__readTableLine(line, table_spacings)
                if CompiledRe.re_layer_table_end.search(line):
                    in_table = False
                continue
            if CompiledRe.re_layer_spacing_table.search(line):
                # A one-line table carries only breakpoints on the opening line; a
                # multi-line one opens here and its rows follow. Either way
                # __readTableLine ignores anything that is not a WIDTH row.
                in_table = not CompiledRe.re_layer_table_end.search(line)
                continue
            if CompiledRe.re_property_statement.search(line):
                # A property *value* is a mini-language belonging to that property, not a
                # set of layer statements. Reading it as one is what put a spacing table's
                # PRL breakpoints (-0.2) into a layer's spacing, and a LEF58_SPACING
                # clause's 0.089 into another's.
                cursor = self.__readProperty(lines, cursor, layer)
                continue

            if type_match := CompiledRe.re_layer_type.search(line):
                layer.type = type_match['TYPE']
            elif direction_match := CompiledRe.re_layer_direction.search(line):
                layer.direction = direction_match['DIRECTION']
            elif pitch_match := CompiledRe.re_layer_pitch_single.search(line):
                layer.pitch_x = float(pitch_match['PITCH'])
                layer.pitch_y = float(pitch_match['PITCH'])
            elif pitch_match := CompiledRe.re_layer_pitch.search(line):
                layer.pitch_x = float(pitch_match['PITCH_X'])
                layer.pitch_y = float(pitch_match['PITCH_Y'])
            elif width_match := CompiledRe.re_layer_width.search(line):
                widths.append(float(width_match['WIDTH']))
            elif min_width_match := CompiledRe.re_layer_min_width.search(line):
                layer.min_width = float(min_width_match['MINWIDTH'])
            elif max_width_match := CompiledRe.re_layer_max_width.search(line):
                layer.max_width = float(max_width_match['MAXWIDTH'])
            elif spacing_match := CompiledRe.re_layer_spacing_default.search(line):
                default_spacing = float(spacing_match['SPACING'])
            elif spacing_match := CompiledRe.re_layer_spacing.search(line):
                spacings.append(float(spacing_match['SPACING']))
            elif area_match := CompiledRe.re_area.search(line):
                layer.area = float(area_match['AREA'])

        # The first WIDTH is the layer default; MINWIDTH is the fallback for a layer that
        # declares no WIDTH at all. Cut and masterslice layers may legitimately have
        # neither, which is why this is not an error.
        layer.width = widths[0] if widths else layer.min_width
        if default_spacing is not None:
            layer.spacing = default_spacing
        elif spacings:
            layer.spacing = min(spacings)
        elif table_spacings:
            layer.spacing = min(table_spacings)
        self.__layers[layer.name] = layer
        return cursor

    def __readProperty(self, lines, cursor, layer) -> int:
        """Consume one ``PROPERTY`` statement, returning the cursor at its last line.

        A property's value is a string that may span lines, and the opening quote may sit on
        the statement line *or* a later one - `asap7` writes `PROPERTY LEF58_SPACING` with a
        trailing space and the quote on the next line. It may also be unquoted
        (`PROPERTY propName propVal ;`), which is why the fast path exists: a rule that only
        waited for a closing quote would run past such a statement to the next quoted line,
        or to the end of the stanza, and the layer would silently lose everything after it.

        Nothing inside the value may be read as a layer statement - that is the whole point.
        Two properties are still consulted by name below, because they carry values this
        project uses; everything else is a mini-language belonging to its property.
        """
        if CompiledRe.re_property_one_line.search(lines[cursor]):
            return cursor
        text = lines[cursor]
        while cursor < len(lines) - 1:
            if text.count('"') % 2 == 0 and ';' in text:
                break
            cursor += 1
            line = lines[cursor]
            # A statement that never terminates must not swallow the rest of the layer. The
            # guard stops *on* this line, so the caller's next iteration sees it - the END
            # ends the stanza, a LAYER opens the next - and reports, because otherwise a
            # missing terminator just empties the layer with no explanation.
            if re.search(rf'^\s*END\s+{re.escape(layer.name)}\b', line) or \
                    CompiledRe.re_layer_name.search(line):
                logger.warning("tech LEF: unterminated PROPERTY in layer %s before %r",
                               layer.name, line.strip()[:40])
                break
            text += line
        self.__applyProperty(layer, text)
        return cursor

    @staticmethod
    def __applyProperty(layer, text: str) -> None:
        """Take the two property values this project uses; ignore every other payload."""
        if CompiledRe.re_LEF58_region_marker.search(text):
            layer.region_layer = True
            # The names, for reporting, matched with the payload's whitespace removed so
            # that a keyword split by a stray space (`BASEDLAYE R`) reads as one word.
            names = CompiledRe.re_LEF58_region_names.search(re.sub(r'\s+', '', text))
            if names:
                layer.region = names['REGION']
                layer.based_layer = names['BASEDLAYER']
        if type_match := CompiledRe.re_LEF58_type.search(text):
            layer.lef58_type = type_match['LEF58_TYPE']

    @staticmethod
    def __readTableLine(line, table_spacings: List[float]) -> None:
        """Collect spacing values from one line of a ``SPACINGTABLE`` body.

        Only ``WIDTH`` rows carry spacings, and their first number is the row's width
        breakpoint rather than a spacing, so it is dropped. Every other line -
        ``PARALLELRUNLENGTH``, ``TWOWIDTHS``, ``INFLUENCE`` - holds breakpoints, which
        must be ignored: including them would drag the minimum spacing to zero.
        """
        numbers = [float(number) for number in re.findall(CompiledRe.FLOAT, line)]
        if CompiledRe.re_layer_width_row.search(line):
            table_spacings.extend(numbers[1:])
        elif numbers and not CompiledRe.re_layer_table_header.search(line):
            # A continuation of the previous row: every number is a spacing.
            table_spacings.extend(numbers)

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
        # OBS geometry this parser does not model (POLYGON, PATH, ...). Counted rather than
        # guessed at: a shape it cannot read is a hole in a blockage, and a caller that wants
        # to say so needs a number.
        self.n_obs_unmodelled = 0
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
                while cursor < self.lines_len and macro_end not in lef_lines[cursor]:
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
                        elif CompiledRe.re_obs_start.search(lef_lines[cursor]):
                            cursor = self.__readObstructions(lef_lines, cursor, this_macro)
                    cursor += 1
                this_macro.setInputPinNum(input_pin_num)
                this_macro.setOutputPinNum(out_pin_num)
                this_macro.setInoutPinNum(inout_pin_num)
                self.__macro_list.append(this_macro)
                self.__macro_dict.update({macro_name: this_macro})
            else:
                cursor += 1

    def __readObstructions(self, lef_lines, cursor, macro):
        """Read an ``OBS`` body into ``macro``, returning the cursor **on** its closing ``END``.

        Leaving the cursor on the terminator, rather than past it, is what the caller's single
        ``cursor += 1`` expects - the same contract the pin loop above honours. Stepping past it
        here would make the caller skip ``END <macro>`` as well, and the enclosing walk would
        then run to the end of the file looking for a macro terminator that has already gone by
        and raise IndexError. Hence the bounds guard on the loops as well.

        The body is a sequence of ``LAYER <name> ;`` sections, each with its own geometry, and
        one bare ``END`` closes the lot - a *multi-layer* OBS is one block with several LAYER
        statements, not one block per layer, so the current layer has to be tracked rather than
        assumed.
        """
        layer = None
        cursor += 1
        while cursor < self.lines_len - 1:
            line = lef_lines[cursor]
            if CompiledRe.re_obs_end.search(line):
                break
            layer_match = CompiledRe.re_layer.search(line)
            if layer_match:
                layer = layer_match.group(1)
                cursor += 1
                continue
            rect_match = CompiledRe.re_rect.search(line)
            if rect_match:
                # A rect before any LAYER has no layer to belong to; dropping it is the only
                # honest option, and it cannot happen in a well-formed OBS.
                if layer is not None:
                    macro.setObstruction(layer, tuple(float(rect_match.group(index))
                                                      for index in (1, 2, 3, 4)))
                cursor += 1
                continue
            if CompiledRe.re_obs_unmodelled.search(line):
                self.n_obs_unmodelled += 1
            cursor += 1
        return cursor

    @staticmethod
    def getAllLefLines(lef_list):
        # Through readFile so a '.gz' macro LEF works like a '.gz' netlist; keepends
        # preserves the readlines() contract the macro search relies on.
        lef_lines = []
        for lef in lef_list:
            lef_lines += readFile(lef).splitlines(keepends=True)
        return lef_lines

    def __repr__(self):
        return f'''
LEF parser
    Total Macro {len(self.__macro_dict)}
'''





