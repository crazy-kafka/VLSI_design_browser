"""What a metal run reports about itself: counters, input shape, and stopping early.

These matter more than they look. The runs this is for take hours, and when the design cannot
be shared the log *is* the evidence - a missing counter or a characterisation that does not
describe the file leaves the next person guessing, which is exactly what happened to the run
whose routing read took 7005 s: its log counted 147 M dropped shapes and never said how many
were measured, so the arithmetic could not be closed.
"""
import contextlib
import io
import json
import logging

from vlsi_viewer.metal import build_metal
from vlsi_viewer.parsers import DefParser
from vlsi_viewer.parsers.routing import ShapeStream, TechRouting, parse_def

TECH = """\
LAYER M1
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END M1
LAYER M2
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
END M2
"""

DEF = """\
VERSION 5.8 ;
DESIGN diag ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
COMPONENTS 1 ;
- u1 INV + PLACED ( 0 0 ) N ;
END COMPONENTS
SPECIALNETS 1 ;
- VDD + USE POWER
  NEW M1 400 + SHAPE FOLLOWPIN ( 100 100 ) ( 900 100 )
  + VIA V12 ( 200 200 ) ( 300 300 )
  ;
END SPECIALNETS
NETS 2 ;
- n1 ( u1 A )
  + ROUTED M2 ( 500 500 ) ( 500 1500 )
  NEW M1 ( 500 1500 ) via1_2 ;
- n2 ( u1 B )
  + ROUTED M3 ( 700 700 ) ( 700 900 ) ;
END NETS
END DESIGN
"""


class Sink:
    """Counts what it is handed, so the stream's own counter can be checked against it."""

    def __init__(self):
        self.rects = 0
        self.diagonals = 0
        self.polygons = 0

    def add_rects(self, layer_index, scope, x0, y0, x1, y1):
        self.rects += len(x0)

    def add_diagonal(self, *args):
        self.diagonals += 1

    def add_polygon(self, *args):
        self.polygons += 1


def _files(tmp_path):
    tech = tmp_path / "tech.lef"
    tech.write_text(TECH)
    path = tmp_path / "d.def"
    path.write_text(DEF)
    return str(path), str(tech)


def _parse(tmp_path, **kwargs):
    path, tech = _files(tmp_path)
    sink = Sink()
    with contextlib.redirect_stdout(io.StringIO()):
        stream = ShapeStream(TechRouting.read([tech]), sink)
        routing = parse_def(path, stream=stream, **kwargs)
        stream.flush()
    return routing, stream, sink


# -- counters ------------------------------------------------------------------------

def test_the_emitted_counter_matches_what_the_sink_was_handed(tmp_path):
    """`n_emitted` is the number the log did not have: the shapes actually measured."""
    _routing, stream, sink = _parse(tmp_path)
    assert stream.n_emitted > 0
    assert stream.n_emitted == sink.rects + sink.diagonals + sink.polygons


def test_the_via_points_are_counted_and_not_emitted(tmp_path):
    """The counter and the shapes have to agree about via points in both directions."""
    _routing, stream, sink = _parse(tmp_path)
    assert stream.n_via == 3                      # two from the '+ VIA' form, one NEW
    assert stream.n_emitted == sink.rects + sink.diagonals + sink.polygons


# -- input characterisation ----------------------------------------------------------

def test_the_characterisation_describes_the_text(tmp_path):
    """What the file was like - the thing a benchmark has to be checked against."""
    routing, _stream, _sink = _parse(tmp_path)
    stats = routing.stats
    assert stats["forms"] > 0
    assert stats["points"] > 0
    assert stats["lines"] > 0
    assert stats["points_max"] >= 2
    # The special net's statement spans three lines, so the shape of the input is visible.
    assert stats["statement_lines_max"] >= 3
    assert stats["statement_chars_max"] > 0
    # A layer the tech LEF never defines is named here rather than only counted later.
    assert {"M1", "M2", "M3"} <= set(stats["layers_used"])


# -- heartbeat -----------------------------------------------------------------------

def test_the_heartbeat_is_silent_until_its_interval_elapses(tmp_path):
    """A short parse prints nothing: the interval is what gates it, not the line count."""
    path, _tech = _files(tmp_path)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        DefParser(path, parse_net=True, parse_specialnet=True, parse_ndr=True)
    assert "lines/s" not in captured.getvalue()


def test_the_heartbeat_reports_the_rate_and_the_section(tmp_path, monkeypatch):
    """With the interval at zero every line reports, which is how the fields are checked."""
    monkeypatch.setattr(DefParser, "HEARTBEAT_SECONDS", 0)
    path, _tech = _files(tmp_path)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        DefParser(path, parse_net=True, parse_specialnet=True, parse_ndr=True)
    beats = [line for line in captured.getvalue().splitlines() if "lines/s" in line]
    assert beats
    assert "NETS" in beats[-1] or "SPECIALNETS" in beats[-1]


# -- cancel --------------------------------------------------------------------------

def test_a_cancel_stops_the_build_and_says_so(tmp_path, monkeypatch):
    """The point of cancelling is the partial map, so the warning is part of the result."""
    monkeypatch.setattr(DefParser, "HEARTBEAT_SECONDS", 0)
    path, tech = _files(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal([path], [], [tech], grid_size=10.0, cancel=lambda: True)
    assert any("stopped early" in warning for warning in data.warnings)
    assert data.totals["emitted"] == 0                  # nothing was measured
    assert data.rows > 0 and data.cols > 0              # but there is still a map


def test_without_a_cancel_the_same_build_measures_everything(tmp_path, monkeypatch):
    """The control for the test above: same input, no cancel, no warning, wiring measured."""
    monkeypatch.setattr(DefParser, "HEARTBEAT_SECONDS", 0)
    path, tech = _files(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal([path], [], [tech], grid_size=10.0)
    assert not any("stopped early" in warning for warning in data.warnings)
    assert data.totals["emitted"] > 0
    assert data.totals["vias"] == 3


# -- the summary line ----------------------------------------------------------------

SUMMARY_FIELDS = {"design", "grid", "stages_s", "shapes", "input_text", "layers",
                  "gc_counts", "gc_s", "warnings", "params", "inputs"}


def test_the_summary_line_is_one_line_of_json_with_the_evidence_in_it(tmp_path, caplog):
    """The artefact a run hands back: one line, parseable, with the fields that matter."""
    path, tech = _files(tmp_path)
    with caplog.at_level(logging.INFO, logger="vlsi_viewer.metal"):
        with contextlib.redirect_stdout(io.StringIO()):
            data = build_metal([path], [], [tech], grid_size=10.0)
    summaries = [record.getMessage() for record in caplog.records
                 if record.getMessage().startswith("metal-summary: ")]
    assert len(summaries) == 1
    summary = json.loads(summaries[0].split("metal-summary: ", 1)[1])
    assert SUMMARY_FIELDS <= set(summary)
    assert summary["design"] == "diag"
    assert summary["grid"] == [data.rows, data.cols]
    assert summary["shapes"]["emitted"] == data.totals["emitted"]
    assert summary["input_text"]["points"] > 0


def test_every_stage_of_a_build_is_announced_and_timed(tmp_path, caplog):
    """A stage that runs but is not timed is a stage whose cost nobody can see."""
    path, tech = _files(tmp_path)
    with caplog.at_level(logging.INFO, logger="vlsi_viewer.metal"):
        with contextlib.redirect_stdout(io.StringIO()):
            build_metal([path], [], [tech], grid_size=10.0)
    announced = {record.getMessage().split()[2] for record in caplog.records
                 if record.getMessage().startswith("metal: stage ")}
    assert {"components", "cell-index", "capacity", "blockage", "routing",
            "grids"} <= announced
    summary = json.loads([record.getMessage() for record in caplog.records
                          if record.getMessage().startswith("metal-summary: ")][0]
                         .split("metal-summary: ", 1)[1])
    # Announced, timed, and in the summary: the three places a stage has to appear.
    assert announced == set(summary["stages_s"])
