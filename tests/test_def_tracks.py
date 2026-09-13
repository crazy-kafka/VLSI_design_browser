"""DEF TRACKS parsing.

The reported failure: a normal track clause carrying a MASK but no SAMEMASK did not
match `re_track`, and `__extractTracks` then indexed the failed match - so a `TypeError`
aborted the *whole* DEF parse, components, DIEAREA and all.

Spec: the reference's TRACKS statement (lines 510-517):

    TRACKS
      [{X|Y} start DO numtracks STEP space
        [MASK maskNum [SAMEMASK]]
        [LAYER layerName ...]
      ;] ...

`SAMEMASK` is separately optional, and `LAYER` may name several layers.
"""
from vlsi_viewer.parsers.DEF.defParser import DefParser

# TRACKS sits between DIEAREA and COMPONENTS in the DEF section order (reference
# 440-470), and the dispatcher stops once it has read COMPONENTS - so the tracks have to
# come first, as they do in a real file.
PRE = """DESIGN trackcase ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
"""
POST = """COMPONENTS 1 ;
- u1 INV_X1 + PLACED ( 0 0 ) N ;
END COMPONENTS
END DESIGN
"""


def _parse(tmp_path, body, name="tracks.def"):
    path = tmp_path / name
    path.write_text(PRE + body + POST)
    return DefParser(str(path))


def test_mask_without_samemask(tmp_path):
    """The reported line: 'MASK 1 LAYER M4' - one space, SAMEMASK omitted."""
    parser = _parse(tmp_path, "TRACKS X 41 DO 24095 STEP 88 MASK 1 LAYER M4 ;\n")
    tracks = parser.getTracks()
    assert len(tracks) == 1
    track = tracks[0]
    assert (track.direction, track.offset, track.num_tracks, track.step,
            track.mask, track.layer_name) == ("X", 41, 24095, 88, 1, "M4")


def test_mask_with_samemask(tmp_path):
    parser = _parse(tmp_path, "TRACKS X 41 DO 24095 STEP 88 MASK 2 SAMEMASK LAYER M5 ;\n")
    track = parser.getTracks()[0]
    assert (track.mask, track.layer_name) == (2, "M5")


def test_without_a_mask_clause(tmp_path):
    parser = _parse(tmp_path, "TRACKS Y 9 DO 100 STEP 10 LAYER M2 ;\n")
    track = parser.getTracks()[0]
    assert (track.direction, track.mask, track.layer_name) == ("Y", 0, "M2")


def test_several_layers_in_one_clause(tmp_path):
    """'[LAYER layerName ...]' - a track pattern applies to each named layer."""
    parser = _parse(tmp_path, "TRACKS X 41 DO 100 STEP 88 LAYER M3 M4 ;\n")
    assert [t.layer_name for t in parser.getTracks()] == ["M3", "M4"]
    assert {t.step for t in parser.getTracks()} == {88}


def test_several_clauses(tmp_path):
    parser = _parse(tmp_path, "TRACKS X 41 DO 100 STEP 88 LAYER M3 ;\n"
                              "TRACKS Y 41 DO 100 STEP 88 MASK 1 LAYER M4 ;\n")
    assert [(t.direction, t.layer_name) for t in parser.getTracks()] == [
        ("X", "M3"), ("Y", "M4")]


def test_an_unreadable_clause_warns_without_aborting(tmp_path, capsys):
    """The actual reported symptom: one bad TRACKS line killed the entire parse."""
    parser = _parse(tmp_path, "TRACKS X 41 BOGUS ;\n")
    out = capsys.readouterr().out
    assert "TRACKS" in out and "BOGUS" in out, out
    assert parser.getTracks() == []
    # everything else still parsed
    assert len(parser.getAllComponents()) == 1
    assert parser.designName == "trackcase"
    assert parser.shape() == [(0, 0), (0, 10000), (10000, 10000), (10000, 0)]
