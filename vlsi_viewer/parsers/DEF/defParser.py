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
from .defNdr import DefNdrLayer, DefNdrRule
from .defSPolygon import DefSPolygon
from .._util import Cancelled, Print


def _with_lookahead(forms: Iterable) -> Iterable:
    """Yield ``(match, next_match)`` for every match, ``None`` for the one after the last.

    The wiring loops need each form's end, which is where the next form starts - and they
    need it without materialising every match first, because one statement can carry tens of
    millions of them. A generator rather than ``zip(forms, chain(forms, ...))``: that shares
    one iterator between the two arguments, so each round consumes two forms and visits every
    other one - which a test caught, and this shape cannot get wrong.
    """
    match = next(forms, None)
    while match is not None:
        following = next(forms, None)
        yield match, following
        match = following

# Parsed-versus-declared counters per section, for the heartbeat's estimate. Only the sections
# a DEF declares a size for are listed - a DEF's line count is not declared anywhere, and its
# net counts are.
_SECTION_PROGRESS = {"NETS": ("n_nets", "declared_nets"),
                     "SPECIALNETS": ("n_special_nets", "declared_special_nets")}


class DefParser:

    CURRENT_LINE_CNT = 0
    # How often to report progress, in seconds. It used to be every million lines, which on a
    # chip-level DEF is 230 s of silence per line - and the print was unflushed, so a job that
    # was killed lost even that.
    HEARTBEAT_SECONDS = 30.0
    IGNORE_PHY = False
    IGNORE_FILLER = False
    IGNORE_COVER = False

    def __init__(self, def_file: AnyStr, skip_comp=False, parse_pin=False, batch_mode=False, parse_net=False, parse_blockage=False, parse_specialnet=False, parse_ndr=True, sink=None, cancel=None, lines=None, puts=None):
        # Every progress line the parser writes goes through `puts`, so a caller that has to tell
        # its lines apart from another process's - the pooled metal path, where eight workers
        # share one stdout - supplies its own. Without one this is what it has always been.
        self.puts = puts if puts is not None else (print if batch_mode is True else Print)
        self.puts(f'Load DEF file {def_file}')
        self.def_file = def_file

        self.skip_comp = skip_comp
        self.parse_pin = parse_pin
        self.parse_net = parse_net
        self.parse_blockage = parse_blockage
        self.parse_specialnet = parse_specialnet
        self.parse_ndr = parse_ndr
        # When set, each net is handed to `sink` as soon as it is parsed and then dropped,
        # so a design with 10^8 wire segments never has to fit in memory. Without a sink
        # the nets accumulate in `self.__nets`, which is what the existing callers expect.
        self.sink = sink

        # Called once per heartbeat; returning True abandons the parse (see `__count_line`).
        # A callable rather than a flag so the caller keeps ownership of the policy - and a
        # constructor argument rather than something to set afterwards, because the parse
        # runs from `__parsingStart` below, before any caller could assign it.
        self.cancel = cancel

        # Input characterisation: how much text, how it is divided into statements, and which
        # layers it names. Counted per statement or per form, never per character, so it costs
        # nothing measurable - and it is what says whether a benchmark resembles the file it
        # is standing in for. See `getStats`.
        self.n_forms = 0
        self.n_points = 0
        self.statement_lines_max = 0
        self.statement_chars_max = 0
        self.points_max = 0
        # `VIRTUAL` connections (not metal), inline `RECT`s (metal, and once dropped), and how
        # many non-orthogonal segments were seen at all - the last one bounded, see below.
        self.n_virtual = 0
        self.n_rects = 0
        self.n_non_orthogonal = 0
        self.layers_used: Set[AnyStr] = set()

        # Heartbeat state; see `__count_line`.
        self.__started_at = time.time()
        self.__reported_at = self.__started_at
        self.__section = None
        self.__section_started_at = self.__started_at
        self.__section_start_count = 0

        # A DEF also arrives as text: the parallel wiring pass hands each worker a block of
        # statements, and a worker has no file to open. `def_file` is still required, for the
        # heartbeat's log line and for a caller to name where the text came from.
        self.__lines: Optional[List] = None if lines is None else list(lines)
        self.__at = 0
        if lines is not None:
            self.fh = None
            self.fetchLine_method = self.fetchLineMemory
        elif self.def_file.endswith('.gz'):
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
        self.__ndrs: Dict[AnyStr, DefNdrRule] = {}
        self.__height = 0
        self.__width = 0
        # A DEF with no DIEAREA is legal (a netlist-only or partial file), so the accessor
        # has to answer rather than raise on an attribute that was never set.
        self.__shape: List[Tuple[int, int]] = []
        # Section counts, taken from the section headers as they go past. Counting this way
        # rather than re-reading the file means it works at any design size, and it is the
        # only way to compare declared against parsed when a sink is discarding the nets.
        self.n_nets = 0
        self.n_special_nets = 0
        self.declared_nets = None
        self.declared_special_nets = None

        self.__parsingStart()

        # A DEF handed over as text has no handle to close; `def_file` still names where it
        # came from, which is what the log and the heartbeat use.
        if self.fh is not None:
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
            # Inserted after TRACKS so it stays ahead of COMPONENTS: the standard DEF
            # order puts NONDEFAULTRULES before COMPONENTS, and 'last_type' below is the
            # last *surviving* key - keeping the position preserves the existing
            # termination behaviour for callers that do not ask for nets.
            'NONDEFAULTRULES': self.__extractNdrRules,
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
        if self.parse_ndr is False:
            del func_dict['NONDEFAULTRULES']
        last_type = list(func_dict.keys())[-1]
        while True:
            line = self.fetchLine_method()

            if not line or CompiledRe.re_end_design.search(line):
                break
            for mtype in func_dict:
                if line.startswith(mtype):
                    self.__enter_section(mtype)
                    func_dict[mtype](line)
                    if mtype == last_type:
                        self.puts(f'End DEF parsing in {round(time.time() - t0, 4)}s', flush=True)
                        return
                    continue

    def __enter_section(self, name: AnyStr) -> None:
        """Note which section is being read, so the heartbeat can say what is left of it."""
        self.__section = name
        self.__section_started_at = time.time()
        pair = _SECTION_PROGRESS.get(name)
        self.__section_start_count = getattr(self, pair[0]) if pair else 0

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
        """Tracks from one TRACKS clause (reference 510-517).

        An unrecognised clause is reported and skipped rather than raised: one track line
        we cannot read must not abort the whole DEF parse, which is what used to happen -
        indexing the failed match raised TypeError and took the components and DIEAREA
        down with it. A LAYER clause may name several layers, and each gets a DefTrack.
        """
        track_match = CompiledRe.re_track.search(line)
        if track_match is None:
            self.puts(f'WARNING: unrecognised TRACKS clause skipped: {line.strip()}')
            return
        match_dict = track_match.groupdict()
        mask = int(match_dict['mask_num']) if match_dict['mask_num'] else 0
        num_tracks = int(match_dict['num_tracks'])
        for layer_name in match_dict['layers'].split():
            self.__tracks.append(DefTrack(
                layer_name, match_dict['direction'], int(match_dict['offset']),
                int(match_dict['step']), mask, num_tracks))

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

    # -- nets ------------------------------------------------------------------
    #
    # A net statement spans lines until its ';', and its clauses are independent of each
    # other: connections, the non-default rule and the wiring all appear in any order.
    # So each statement is read whole and then picked apart, rather than being scanned
    # one line at a time with an if/elif chain (which lost connections whenever a
    # statement also carried a rule clause, and lost every segment after the first).

    def __read_statement(self, first_line: AnyStr) -> Tuple[AnyStr, AnyStr]:
        """Join a statement's lines up to its terminating ';'.

        Returns ``(statement_text, next_line)``. Also stops at an ``END <SECTION>``
        marker, which keeps a malformed statement from swallowing the rest of the file.
        The ';' split is not quote-aware, so a property string containing ';' would
        still truncate the statement - a known limit, unchanged from before.

        The lines are joined into blocks as they arrive rather than all being kept and joined
        at the end. A chip-level power net is one statement of 58,549,358 lines (measured:
        4,979,560,694 characters), and the list of them plus the single join at the end was
        the largest allocation in a real read - about twice the text, on top of the text.
        """
        chunk = [first_line]
        chunks: List[AnyStr] = []
        lines = 1
        last = first_line
        while ';' not in last:
            line = self.fetchLine_method()
            if not line or line.lstrip().startswith('END '):
                return self.__size(chunks, chunk, lines), line
            last = line
            chunk.append(line)
            lines += 1
            if len(chunk) >= self.STATEMENT_CHUNK_LINES and ';' not in line:
                chunks.append(' '.join(chunk))
                chunk = []
        chunk[-1] = chunk[-1].split(';', 1)[0]
        return self.__size(chunks, chunk, lines), self.fetchLine_method()

    # How many lines are joined in one go while a statement is read. Big enough that the
    # join is still one operation over a real statement, small enough that the line strings
    # of a giant one are released as it is read instead of at the end.
    STATEMENT_CHUNK_LINES = 4096

    def __size(self, chunks: List, tail: List, lines: int) -> AnyStr:
        """Join a statement and record how big it was.

        ``chunks`` holds the text of every block of lines already joined and ``tail`` the
        lines not yet joined, so the result is the same string one ``' '.join`` of all the
        lines would give, assembled without ever holding all of them.

        A statement's size is not reported anywhere else, and it is the first thing to check
        when a benchmark is supposed to stand in for a real file: a power net written as one
        statement of a million points is not the same input as a million statements of one
        point, and the two cost differently.
        """
        statement = ' '.join(chunks + [' '.join(tail)])
        if lines > self.statement_lines_max:
            self.statement_lines_max = lines
        if len(statement) > self.statement_chars_max:
            self.statement_chars_max = len(statement)
        return statement

    def __statement_net(self, header: AnyStr) -> DefNet:
        """The net a statement defines, created on first sight, with its connections.

        ``header`` is the part of the statement before its wiring. Connections are read
        from there rather than from the whole statement, because a routing point
        ``( 0 0 )`` has exactly the same shape as a connection ``( u1 A )``.

        ``( compName pinName )`` and ``( PIN pinName )`` are both handled, so the
        connections no longer depend on where the other clauses sit. ``MUSTJOIN`` has
        the same parenthesised shape and is recorded as an ordinary connection.
        """
        name = CompiledRe.re_net.search(header).groupdict()['net_name']
        net = self.__nets.get(name)
        if net is None:
            net = DefNet(name)
            self.__nets[name] = net
        for inst_name, term_name in CompiledRe.re_net_conn.findall(header):
            net.connect_pins.append(
                term_name if inst_name == 'PIN' else f'{inst_name}/{term_name}')
        return net

    @staticmethod
    def __resolve_coord(token: AnyStr, last: List, index: int) -> int:
        """One routing coordinate: an integer, or '*' meaning the last value used."""
        if token != '*':
            return int(token)
        if last[index] is None:
            raise ValueError(
                "'*' used as the first routing coordinate, which the DEF reference "
                "forbids ('First coordinate cannot use *')")
        return last[index]

    def __scan_tokens(self, tail: AnyStr, last: List) -> List[Tuple]:
        """Ordered points, vias, virtual points and rectangles from a routing-points tail.

        ``last`` is shared across the statement so ``*`` reuses the last coordinate per
        the reference. Returns ``('pt', x, y, ext)``, ``('vpt', x, y, ext)`` for a
        ``VIRTUAL`` point, ``('rect', x0, y0, x1, y1)`` and ``('via', name, orient)``.
        """
        out = []
        # '(*703600)' and '(1760*)' are handled defensively, not because they were seen: a
        # sweep of a real routed DEF (`sample_data/real/nangate45/gcd_nangate45.def`) found
        # zero occurrences - tools write the spaced form, `( 52630 55580 ) ( 53770 * )`. They
        # are split before tokenising so the point pattern can keep requiring a separator
        # between coordinates, which is what stops a malformed '(1234)' from silently
        # splitting into 123 and 4.
        # The substitution only fires across a digit/star boundary, so a tail without a '*'
        # is returned unchanged - and most tails have none, which makes the check worth
        # making (a regex call per form on every DEF costs more than the scan it guards).
        if '*' in tail:
            tail = CompiledRe.re_glued_star.sub(' ', tail)
        if (len(tail) >= 48
                and CompiledRe.re_word_char.search(tail) is None):
            # A tail with no via-name character may be nothing but points - via
            # arrays and whole power nets, the bulk of a chip-level DEF. Short
            # tails do not repay the dispatch (measured); lettered ones cannot win.
            pure = self.__points_only(tail, last)
            if pure is not None:
                return pure
        for token in CompiledRe.re_wire_token.finditer(tail):
            # One `group` call per token rather than one per field: `group` is a C method with
            # an argument parse and a return-tuple build, and a real design's read makes
            # billions of these calls - measured as `re.Match.group`, 4.9 % of the profile.
            # Asking for several groups at once returns the same strings in one call, and an
            # unparticipated group still answers `None`.
            x, y, ext, vx, vy, rx, ry, rx2, ry2 = token.group(
                'x', 'y', 'ext', 'vx', 'vy', 'rx0', 'ry0', 'rx1', 'ry1')
            if vx is not None:
                # `VIRTUAL ( x y )`: a non-physical zero-width connection, whose point is where
                # the path continues from (reference 874). Kept as its own kind rather than
                # resolved away - the caller drops the segment *into* it and keeps the one out.
                vx = self.__resolve_coord(vx, last, 0)
                vy = self.__resolve_coord(vy, last, 1)
                last[0], last[1] = vx, vy
                out.append(('vpt', vx, vy, None))
            elif rx is not None:
                # `RECT ( deltax1 deltay1 deltax2 deltay2 )`: real metal, a rectangle placed
                # from the previous point by those deltas. Resolved here because that is the
                # only moment the point it is relative to is known - and it does *not* become
                # the current point, which the reference states explicitly.
                if last[0] is None:
                    raise ValueError("a RECT placed before any routing point, so there is "
                                     "nothing for its deltas to be relative to")
                out.append(('rect', last[0] + int(rx), last[1] + int(ry),
                            last[0] + int(rx2), last[1] + int(ry2)))
            elif x is not None:
                x = self.__resolve_coord(x, last, 0)
                y = self.__resolve_coord(y, last, 1)
                last[0], last[1] = x, y
                out.append(('pt', x, y, int(ext) if ext is not None else None))
            else:
                name, orientation = token.group('via', 'via_orient')
                if name in CompiledRe.WIRE_KEYWORDS:
                    # A clause keyword where a via name would sit ('+ SHAPE STRIPE'). The
                    # token pattern no longer rejects these with a lookahead, because that
                    # test was retried at every character of the tail; here it is paid once
                    # per matched word. No metric path reads a via name.
                    continue
                out.append(('via', name, orientation))
        return out

    def __points_only(self, tail: AnyStr, last: List) -> Union[List[Tuple], None]:
        """The token list for a tail that holds routing points and nothing else.

        Via arrays and whole power nets - the bulk of a chip-level DEF's text - have
        tails like that, and the point pattern alone scans them ~1.2x cheaper than
        the full tokeniser (no via/RECT/VIRTUAL alternatives, ``findall``'s C-level
        extraction instead of a ``group()`` call per token). The substitution is the
        coverage check: strip every point, and anything left that is not whitespace
        means the tail held something else - a digit-named via, junk - and the caller
        falls back to the full tokeniser, so nothing is ever dropped silently.
        ``last`` is written back only on success: a fallback must see it untouched.
        """
        if CompiledRe.re_points_tail.sub('', tail).strip():
            return None
        local = [last[0], last[1]]
        out = []
        append = out.append
        for xs, ys, exts in CompiledRe.re_points_tail.findall(tail):
            x = self.__resolve_coord(xs, local, 0)
            y = self.__resolve_coord(ys, local, 1)
            local[0], local[1] = x, y
            # findall answers '' where a group() would answer None.
            append(('pt', x, y, int(exts) if exts else None))
        last[0], last[1] = local
        return out

    @staticmethod
    def __split_points(tokens: List[Tuple]) -> Tuple[List[Tuple], dict, List[Tuple]]:
        """Points in order, the via anchored to each point's index, and the rectangles.

        A via sits *at* a routing point, so it rides the segment that starts there; a
        via appearing before the first point rides the first segment instead. A ``VIRTUAL``
        point is a point here - the path does run through it - and whether the segment leading
        to it is metal is the emit loops' decision rather than this one's.
        """
        points, vias, rects, leading = [], {}, [], None
        for token in tokens:
            if token[0] == 'pt' or token[0] == 'vpt':
                points.append(token)
                if leading is not None:
                    vias[len(points) - 1] = leading
                    leading = None
            elif token[0] == 'rect':
                rects.append(token)
            elif points:
                vias.setdefault(len(points) - 1, (token[1], token[2]))
            else:
                leading = (token[1], token[2])
        return points, vias, rects

    def __segments(self, points, vias, net):
        """The wire segments a form's points describe, and the virtual ones it does not.

        A connection *into* a ``VIRTUAL`` point is not metal (reference 874), so it yields no
        segment; the connection out of that point is an ordinary one. Yields
        ``(index, from_point, to_point, (via, orientation))``, counting each virtual connection
        it skips on the net - which is where the stream picks the number up - and in the run's
        own statistics.
        """
        for i in range(len(points) - 1):
            if points[i + 1][0] == 'vpt':
                self.n_virtual += 1
                net.virtual_points += 1
                continue
            yield i, points[i], points[i + 1], vias.get(i, (None, None))

    def __note_non_orthogonal(self, net, layer, a, b, text) -> None:
        """Report the first few non-orthogonal segments, with the form text behind each one.

        A real run counted 8,777,752 of these on layers whose design rules forbid 45 degrees -
        and a counter cannot say whether that is geometry the tool wrote or a construct this
        parser reads wrongly, which `VIRTUAL` turned out to be. The form's own text settles it:
        it can be grepped for in the DEF, and the points are in database units, which is what
        the file itself uses. Bounded to five per worker, and only ever for a segment that is
        about to be measured as metal.
        """
        if self.n_non_orthogonal >= 5 or a[1] == b[1] or a[2] == b[2]:
            return
        self.n_non_orthogonal += 1
        self.puts(f"NOTE: non-orthogonal segment on {layer} in net {net.net_name}: "
                  f"({a[1]} {a[2]}) -> ({b[1]} {b[2]})"
                  f"{' [form uses *]' if '*' in text else ''} from: {text[:200]}")

    @staticmethod
    def __split_statement(statement: AnyStr, form_re) -> Tuple[AnyStr, int, int]:
        """Split a statement into its pre-wiring header and the span of its wiring.

        Returns ``(header, start, end)`` - positions into ``statement`` rather than a copy of
        the wiring, because that copy is one of the largest allocations a real read makes: a
        power net's statement is gigabytes, and its wiring is nearly all of it. Callers scan
        ``statement[start:end]`` in place, and ``finditer(text, pos, endpos)`` searches exactly
        what the slice held - checked against the real files in the tests.

        The header (net name, connections, ``+ NONDEFAULTRULE`` …) comes first in both
        grammars; the wiring runs from the first form up to the next non-wiring clause.
        Separating them is what keeps a routing point from being read as a connection,
        and keeps a trailing ``+ SOURCE DIST`` from being read as a via.
        """
        first = form_re.search(statement)
        if first is None:
            return statement, len(statement), len(statement)
        # Every clause keyword needs a '+', so a text without one cannot hold a clause and
        # the scan is skipped. The scan then walks the same text the form scan walks, so an
        # avoidable scan here costs as much as the one that matters.
        cut = (CompiledRe.re_non_wiring_clause.search(statement, first.start())
               if statement.find('+', first.start()) >= 0 else None)
        return (statement[:first.start()], first.start(),
                cut.start() if cut else len(statement))

    def __extractNdrRules(self, line: AnyStr):
        """Read the NONDEFAULTRULES section.

        A rule's '+ LAYER' clauses carry no terminator of their own - one ';' ends the
        whole rule - so __read_statement joins each rule into a single statement and it
        is split here.

        Nothing in this section may raise. An unreadable rule is reported and kept as an
        empty rule rather than aborting the parse: the same lesson __extractTracks
        learned, where one unrecognised clause took down components, die area and density
        with it.
        """
        while line and 'END NONDEFAULTRULES' not in line:
            if CompiledRe.re_ndr_rule.search(line):
                statement, line = self.__read_statement(line)
                self.__parse_ndr_statement(statement)
            else:
                line = self.fetchLine_method()

    def __parse_ndr_statement(self, statement: AnyStr) -> None:
        name_match = CompiledRe.re_ndr_rule.search(statement)
        if name_match is None:
            return
        rule = DefNdrRule(name_match.groupdict()['rule_name'])
        for layer_match in CompiledRe.re_ndr_layer.finditer(statement):
            fields = layer_match.groupdict()
            layer = DefNdrLayer(fields['layer'])
            for field_match in CompiledRe.re_ndr_field.finditer(fields['body']):
                field = field_match.groupdict()
                value = float(field['value'])
                # Database units are integers and DefTrack keeps them as such; keep the
                # same convention so a caller scales both the same way.
                setattr(layer, field['field'].lower(),
                        int(value) if value.is_integer() else value)
            rule.layers[layer.layer_name] = layer
        rule.hardspacing = CompiledRe.re_ndr_hardspacing.search(statement) is not None
        rule.unparsed = [match.groupdict()['clause']
                         for match in CompiledRe.re_ndr_other.finditer(statement)]
        if not rule.layers:
            self.puts(f'WARNING: non-default rule {rule.rule_name!r} names no readable '
                      f'layer; nets using it fall back to the layer defaults')
        self.__ndrs[rule.rule_name] = rule

    def __add_special_wiring(self, net: DefNet, statement: AnyStr, start: int, end: int):
        """Emit ``DefSWire`` segments for every special-wiring form in the statement.

        Scanned in place and one form ahead, as the regular path is - and this is the one
        that matters most, because a power net is exactly the statement that is enormous.
        """
        forms = CompiledRe.re_special_wiring_form.finditer(statement, start, end)
        last = [None, None]
        for match, nxt in _with_lookahead(forms):
            form_end = end if nxt is None else nxt.start()
            self.n_forms += 1
            # One `group` call for the five fields this loop uses, rather than a `groupdict`
            # (a dict, then a lookup and a `get` per field) - see `__scan_tokens`.
            via_name, form_width, rect_layer, poly_layer, layer = match.group(
                'via_name', 'width', 'rect_layer', 'poly_layer', 'layer')
            points, vias, rects = self.__split_points(
                self.__scan_tokens(statement[match.end():form_end], last))
            self.n_points += len(points)
            if len(points) > self.points_max:
                self.points_max = len(points)
            for name in (poly_layer, rect_layer, layer):
                if name:
                    self.layers_used.add(name)
            for _, x0, y0, x1, y1 in rects:
                net.rects.append((layer, x0, y0, x1, y1))
                self.n_rects += 1

            if via_name:
                # '+ VIA via [orient] pt ...': each point carries the via, so there is no
                # segment. The points are *scanned* (so '*' keeps resolving across the
                # statement) but not turned into shapes: the stream counts a via point and
                # reads nothing else about it, so building one zero-length object per point
                # buys exactly the same counter at the price of the allocation.
                net.via_points += len(points)
                if layer:
                    net.via_points_by_layer[layer] = \
                        net.via_points_by_layer.get(layer, 0) + len(points)
                continue

            width = int(form_width) if form_width else None
            if rect_layer:
                layer, shape = rect_layer, 'RECT'
            elif poly_layer:
                layer, shape = poly_layer, 'POLYGON'
                # This is the only point at which the whole vertex list exists. The
                # per-edge DefSWires emitted below cannot be reassembled into the ring -
                # they carry no polygon id and the closing edge is never emitted - so the
                # filled shape, and with it the area, is captured here.
                if len(points) >= 3:
                    net.polygons.append(
                        DefSPolygon(layer, [(point[1], point[2]) for point in points]))
            else:
                shape = 'PATH'
            self.__emit_special(net, layer, width, shape, points, vias)

    def __emit_special(self, net: DefNet, layer, width, shape, points, vias):
        if len(points) == 1:
            if points[0][0] == 'vpt':
                # A lone virtual point is a connection to nowhere, and it is not a via either.
                return
            _, x, y, ext = points[0]
            via, via_orient = vias.get(0, (None, None))
            net.swiring.append(DefSWire(layer, width, x, y, ext or 0, x, y, ext or 0,
                                        via=via, via_orient=via_orient, shape=shape))
            return
        for _i, a, b, (via, via_orient) in self.__segments(points, vias, net):
            _, x0, y0, e0 = a
            _, x1, y1, e1 = b
            net.swiring.append(DefSWire(layer, width, x0, y0, e0 or 0, x1, y1, e1 or 0,
                                        via=via, via_orient=via_orient, shape=shape))

    def __add_regular_wiring(self, net: DefNet, statement: AnyStr, start: int, end: int,
                             rule: AnyStr):
        """Emit ``DefWire`` segments for every regular-wiring form in the statement.

        The wiring is scanned where it sits - ``statement[start:end]`` - rather than through a
        copy of itself, and one form ahead of the current one rather than through a list of
        every match: a statement can carry tens of millions of forms, and a match object is
        208 bytes, so the list alone was several gigabytes on a real power net.
        """
        forms = CompiledRe.re_regular_wiring_form.finditer(statement, start, end)
        last = [None, None]
        for match, nxt in _with_lookahead(forms):
            form_end = end if nxt is None else nxt.start()
            self.n_forms += 1
            layer_name, taper_rule = match.group('layer', 'taper_rule')
            # A per-wire TAPERRULE wins over the net-level + NONDEFAULTRULE.
            wire_rule = taper_rule or rule
            self.layers_used.add(layer_name)
            points, vias, rects = self.__split_points(
                self.__scan_tokens(statement[match.end():form_end], last))
            self.n_points += len(points)
            if len(points) > self.points_max:
                self.points_max = len(points)
            for _, x0, y0, x1, y1 in rects:
                net.rects.append((layer_name, x0, y0, x1, y1))
                self.n_rects += 1
            if len(points) == 1:
                if points[0][0] == 'vpt':
                    continue
                _, x, y, _ext = points[0]
                via, via_orient = vias.get(0, (None, None))
                net.wiring.append(DefWire(layer_name, wire_rule, (x, y), (x, y),
                                          via=via, via_orient=via_orient))
                continue
            for _j, a, b, (via, via_orient) in self.__segments(points, vias, net):
                self.__note_non_orthogonal(net, layer_name, a, b,
                                           statement[match.end():form_end])
                net.wiring.append(DefWire(layer_name, wire_rule, (a[1], a[2]), (b[1], b[2]),
                                          via=via, via_orient=via_orient))

    @staticmethod
    def __section_count(line: AnyStr) -> Union[int, None]:
        """The declared count from a section header such as ``NETS 497 ;``."""
        count_match = re.search(r'(\d+)', line or '')
        return int(count_match.group(1)) if count_match else None

    def __extractSpecialNets(self, line: AnyStr):
        self.declared_special_nets = self.__section_count(line)
        while line and 'END SPECIALNETS' not in line:
            if CompiledRe.re_net.search(line):
                self.n_special_nets += 1
                statement, line = self.__read_statement(line)
                header, start, end = self.__split_statement(
                    statement, CompiledRe.re_special_wiring_form)
                net = self.__statement_net(header)
                net.is_special = True
                self.__record_use(net, statement)
                if start < end:
                    self.__add_special_wiring(net, statement, start, end)
                self.__release(net)
            else:
                line = self.fetchLine_method()

    def __extractNets(self, line: AnyStr):
        self.declared_nets = self.__section_count(line)
        while line and 'END NETS' not in line:
            if CompiledRe.re_net.search(line):
                self.n_nets += 1
                statement, line = self.__read_statement(line)
                header, start, end = self.__split_statement(
                    statement, CompiledRe.re_regular_wiring_form)
                net = self.__statement_net(header)
                self.__record_use(net, statement)
                # Searched over the whole statement, not only the header:
                # __split_statement cuts the wiring text at the first non-wiring clause,
                # so a '+ NONDEFAULTRULE X' sitting after the wiring belongs to neither
                # part and was dropped silently - leaving the net on the default rule,
                # which reads a 2W2S clock net as 1W1S.
                ndr_match = (CompiledRe.re_ndr.search(statement)
                             if 'NONDEFAULTRULE' in statement else None)
                rule = ndr_match['ndr'] if ndr_match else 'default'
                if start < end:
                    self.__add_regular_wiring(net, statement, start, end, rule)
                self.__release(net)
            else:
                line = self.fetchLine_method()

    def __release(self, net: DefNet) -> None:
        """Hand a finished net to the sink and forget it, if one is set.

        Clearing eagerly is the point: the shapes are already handed over, and holding
        them until the parse ends is what makes a large DEF unfittable in memory.

        The sink also receives the database unit and the rule table, because it cannot
        read them for itself: it is called *during* construction, so the caller has not yet
        been handed the parser it would have to ask. Both are populated by the time a net
        is reached - UNITS and NONDEFAULTRULES both precede NETS in the grammar.
        """
        if self.sink is not None:
            self.sink(net, self.__db_unit, self.__ndrs)
            self.__nets.clear()

    @staticmethod
    def __record_use(net: DefNet, statement: AnyStr) -> None:
        """Record a net's '+ USE' clause.

        The grammar allows it on either side of the wiring, so it is read from the whole
        statement rather than from the header.
        """
        # The pattern needs the literal 'USE', so a statement without it cannot match and
        # the scan over the whole statement is skipped. A guard has to be a *superset* of
        # the pattern's own requirement - '+ USE' would be wrong, since '+\tUSE' matches.
        use_match = CompiledRe.re_net_use.search(statement) if 'USE' in statement else None
        if use_match:
            net.use = use_match.groupdict()['use']

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
    def __isPhysicalOnly(module_name: AnyStr) -> bool:
        if 'FILL' in module_name or 'DCAP' in module_name or 'TAPCELL' in module_name or 'BOUNDARY' in module_name:
            return True
        else:
            return False

    def fetchLineGz(self) -> AnyStr:
        self.__count_line()
        return self.fh.readline().decode()

    def fetchLine(self) -> AnyStr:
        self.__count_line()
        return self.fh.readline()

    def fetchLineMemory(self) -> AnyStr:
        """One line from the text handed to the constructor, or '' once it runs out.

        Empty is what a caller reads as end-of-input, the same contract as a file at EOF.
        """
        self.__count_line()
        if self.__at >= len(self.__lines):
            return ''
        line = self.__lines[self.__at]
        self.__at += 1
        return line

    def __count_line(self) -> None:
        """One line read: the counter, the heartbeat, and the cancel check.

        The heartbeat carries the rate and, inside a section whose size the header declares,
        what is left of it - the only estimate available, since a DEF does not say how long it
        is. It is flushed every time: to a pipe, an unflushed line is a line the job log does
        not have.
        """
        self.CURRENT_LINE_CNT += 1
        now = time.time()
        if now - self.__reported_at < self.HEARTBEAT_SECONDS:
            return
        self.__reported_at = now
        elapsed = now - self.__started_at
        rate = self.CURRENT_LINE_CNT / elapsed if elapsed > 0 else 0.0
        self.puts(f"Read DEF {self.CURRENT_LINE_CNT:,} lines  {rate:,.0f} lines/s  "
                  f"{elapsed / 60:.0f} min elapsed{self.__section_eta(now, rate)}",
                  flush=True)
        if self.cancel is not None and self.cancel():
            raise Cancelled(f"stopped after {self.CURRENT_LINE_CNT:,} lines")

    def __section_eta(self, now, rate) -> AnyStr:
        """What is left of the section being read, when its header declared a size."""
        pair = _SECTION_PROGRESS.get(self.__section)
        if pair is None:
            return ""
        done = getattr(self, pair[0])
        declared = getattr(self, pair[1])
        if not declared:
            return f"  {self.__section} {done:,}"
        span = now - self.__section_started_at
        pace = (done - self.__section_start_count) / span if span > 0 else 0.0
        if pace <= 0:
            return f"  {self.__section} {done:,}/{declared:,}"
        return (f"  {self.__section} {done:,}/{declared:,}"
                f"  ~{(declared - done) / pace / 60:.1f} min left")

    @property
    def designName(self) -> AnyStr:
        return self.__design_name

    def dbUnit(self) -> int:
        return self.__db_unit

    def getTracks(self) -> List[DefTrack]:
        return self.__tracks

    def getNdrRules(self) -> Dict[AnyStr, DefNdrRule]:
        return self.__ndrs

    def getStats(self) -> Dict:
        """What the file was like, as opposed to what was parsed out of it.

        Reported by the metal flow so its log describes its input: a run's cost follows
        the shape of the text - statements per net, points per statement, which layers are
        named - and none of that is visible in a DEF's header or in a counter of what was
        dropped.
        """
        return {"forms": self.n_forms, "points": self.n_points,
                "lines": self.CURRENT_LINE_CNT,
                "statement_lines_max": self.statement_lines_max,
                "statement_chars_max": self.statement_chars_max,
                "points_max": self.points_max,
                "virtual": self.n_virtual,
                "rects": self.n_rects,
                "layers_used": sorted(self.layers_used)}

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







