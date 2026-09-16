"""Linux-style CLI launcher for the VLSI hierarchy viewer.

Three input flows, one per subcommand:

``json``
    Pre-processed ``cell_info.json`` + ``instance_info.json`` (the original interface).
``verilog``
    Gate-level Verilog plus a macro LEF. A netlist has no placement, so this flow has
    no physical mode - the flag does not exist on the subparser at all.
``def``
    DEF plus a macro LEF. DEF carries placement, so physical mode works here.

The ``verilog`` and ``def`` flows convert their inputs into exactly the structures the
``json`` flow reads, and hand them straight to the pipeline in memory - a run writes
nothing to disk. ``--out DIR`` additionally dumps the converted JSON there -
``cell_info.json`` and ``<top>.instance_info.json`` (``.compare.json`` for the second
design) - as a copy to inspect or to feed back to the ``json`` subcommand.
"""
import argparse
import json
import logging
import os
import sys

from . import __version__, config
from .metrics import load_or_build

logger = logging.getLogger(__name__)


def _add_shared(parser):
    """Options every subcommand reads, including ``metal``."""
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="verbose (debug) logging")


def _add_pipeline(parser):
    """Options for the JSON pipeline and the metric tree - everything but ``metal``.

    Metal mode converts no JSON, builds no tree, and caches nothing: it reads DEF and LEF
    straight into grids, so a threshold, a macro-column toggle and a cache directory are not
    things it can act on. They used to be accepted and ignored, which is worse than absent -
    the help text described a hierarchy filter in a mode that has no hierarchy.
    """
    parser.add_argument(
        "--min-instances", type=int, default=config.DEFAULT_MIN_INST_COUNT, metavar="N",
        help="hide hierarchies with fewer than N instances (default: %(default)s)")
    parser.add_argument("--include-macros", action="store_true",
                        help="show macro count/area columns")
    parser.add_argument("--cache-dir", metavar="DIR",
                        help="pickle cache directory override")
    parser.add_argument("--force", action="store_true",
                        help="ignore cache and re-preprocess")


def _add_physical(parser):
    """Heat-map options, only for the subcommands that place instances."""
    parser.add_argument(
        "--grid_size", type=float, default=config.DEFAULT_GRID_SIZE, metavar="N",
        help="physical-mode heat-map grid cell size (default: %(default)s)")
    parser.add_argument(
        "--contour_gap", type=float, default=None, metavar="N",
        help="physical-mode hierarchy contour merge gap; defaults to "
             f"{config.DEFAULT_CONTOUR_GAP_FACTOR} x grid_size")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="vlsi-viewer",
        description="VLSI design hierarchy visualization tool.",
    )
    # On the top-level parser so --version prints "vlsi-viewer", not a subcommand name.
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    p = sub.add_parser("json", help="pre-processed cell_info.json / instance_info.json")
    p.add_argument("--cell_info", required=True, metavar="CELL",
                   help="path to cell_info.json")
    p.add_argument("--block_info", required=True, nargs="+", metavar="BLOCK",
                   help="one or more instance_info.json block files")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--compare_block_info", nargs="+", metavar="BLOCK",
                      help="instance_info.json block files for the second design "
                           "(reuses --cell_info)")
    mode.add_argument("--physical_mode", action="store_true",
                      help="render a 2-D heat map (layout view) instead of compare")
    _add_physical(p)
    _add_pipeline(p)
    _add_shared(p)

    p = sub.add_parser("verilog", help="gate-level Verilog + macro LEF (no physical mode)")
    p.add_argument("--verilog", required=True, nargs="+", metavar="V",
                   help="gate-level netlist file(s)")
    p.add_argument("--lef", required=True, nargs="+", metavar="LEF",
                   help="macro LEF file(s) describing the cell library")
    p.add_argument("--top", required=True, metavar="NAME",
                   help="top-level module name in the netlist")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--compare_verilog", nargs="+", metavar="V",
                      help="netlist file(s) for the second design")
    p.add_argument("--compare_top", metavar="NAME",
                   help="top module of the second design (defaults to --top)")
    p.add_argument("--out", metavar="DIR",
                   help="dump the converted JSON here as cell_info.json and "
                        "<top>.instance_info.json (.compare.json for the second design); "
                        "by default nothing is written")
    _add_pipeline(p)
    _add_shared(p)

    p = sub.add_parser("def", help="DEF + macro LEF (physical mode supported)")
    # dest is explicit because the default would be `args.def`, and `def` is a keyword.
    p.add_argument("--def", dest="def_files", required=True, nargs="+", metavar="DEF",
                   help="DEF file(s) with placement")
    p.add_argument("--lef", required=True, nargs="+", metavar="LEF",
                   help="macro LEF file(s) describing the cell library")
    p.add_argument("--top", metavar="NAME",
                   help="override the DEF DESIGN name")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--compare_def", nargs="+", metavar="DEF",
                      help="DEF file(s) for the second design (reuses --lef)")
    mode.add_argument("--physical_mode", action="store_true",
                      help="render a 2-D heat map (layout view) instead of compare")
    p.add_argument("--compare_top", metavar="NAME",
                   help="override the second design's DESIGN name")
    p.add_argument("--out", metavar="DIR",
                   help="dump the converted JSON here as cell_info.json and "
                        "<top>.instance_info.json (.compare.json for the second design); "
                        "by default nothing is written")
    _add_physical(p)
    _add_pipeline(p)
    _add_shared(p)

    p = sub.add_parser("metal", help="DEF + macro LEF + tech LEF: metal-density maps")
    # dest is explicit because the default would be `args.def`, and `def` is a keyword.
    p.add_argument("--def", dest="def_files", nargs="+", metavar="DEF",
                   help="DEF file(s) with routing; several are assembled into one "
                        "hierarchy with a single top. Optional only when --db covers every "
                        "block of the design")
    p.add_argument("--lef", required=True, nargs="+", metavar="LEF",
                   help="macro LEF file(s) describing the cell library")
    p.add_argument("--tech-lef", dest="tech_lef", required=True, nargs="+", metavar="TLEF",
                   help="tech LEF file(s) declaring the routing layers")
    p.add_argument("--top", metavar="NAME", help="override the top block name")
    p.add_argument("--grid-size", type=float, default=config.DEFAULT_METAL_GRID_SIZE,
                   metavar="N",
                   help="heat-map grid cell size in um (default: %(default)s)")
    p.add_argument("--macro-block-layers", type=int,
                   default=config.DEFAULT_MACRO_BLOCK_LAYERS, metavar="N",
                   help="fallback only: how many bottom layers of the whole stack a macro "
                        "that declares no OBS takes capacity from, counted from the bottom "
                        "before any --min-layer/--max-layer takes effect (default: "
                        "%(default)s)")
    # The underscore spellings are aliases: the metal group is hyphenated (`--grid-size`,
    # `--min-segment-length`), but these two name parameters of `build_metal`, and a caller
    # reading the source should not have to guess which spelling the CLI chose.
    p.add_argument("--min-layer", "--min_layer", dest="min_layer", type=int, default=None,
                   metavar="N",
                   help="lowest routing layer to measure, as a 1-based position in the stack: "
                        "the layer panel numbers its rows from 1 at the bottom, so 2 is the "
                        "second routing layer your tech LEF declares (default: the bottom "
                        "layer)")
    p.add_argument("--max-layer", "--max_layer", dest="max_layer", type=int, default=None,
                   metavar="N",
                   help="highest routing layer to measure, in the same 1-based positions "
                        "(default: the top layer). Wiring on the layers left out is reported "
                        "as filtered, not as a layer your LEF is missing")
    p.add_argument("--min-segment-length", type=float, default=None, metavar="N",
                   help="drop non-preferred-direction jogs shorter than N um; default is "
                        "each layer's track pitch, 0 keeps every jog")
    p.add_argument("--jobs", type=int, default=1, metavar="N",
                   help="processes to use for the wiring pass (default: %(default)s). The pass "
                        "is per-net work with no dependency between nets, so it scales nearly "
                        "linearly with cores; 1 keeps everything in one process. It is a cap "
                        "rather than an instruction - a small DEF is parsed in one process "
                        "whatever you ask for - and every worker re-reads the whole file, so "
                        "match it to the cores you were allocated rather than to your host")
    p.add_argument("--profile", nargs="?", const="", metavar="PSTATS",
                   help="time the build with cProfile and print the top 15 by self time; "
                        "optionally write a .pstats file. The wall clock it reports is "
                        "inflated, so use it to find the cost, not to measure it")
    # The underscore spellings are aliases here too, for the same reason as the layer flags:
    # these name parameters of `build_metal`.
    p.add_argument("--dump-db", "--dump_db", dest="dump_db", metavar="DIR",
                   help="write one intermediate db per DEF input into DIR, named from the DEF "
                        "(A.def.gz -> A.def.db), so a later run rebuilds the map without parsing "
                        "the DEF again")
    p.add_argument("--db", dest="db_files", nargs="+", metavar="DB",
                   help="intermediate db file(s) written by --dump-db. A block whose db still "
                        "matches this run - same DEF, same knobs, same LEFs, same placement - is "
                        "not parsed at all; with --def, only the DEFs that changed are")
    p.add_argument("--dump-only", "--dump_only", dest="dump_only", action="store_true",
                   help="write the dbs (with --dump-db) and exit without opening a window")
    _add_shared(p)

    return parser.parse_args(argv)


def _block_out_path(args, block, compare=False):
    """``<top>.instance_info.json``, or ``<top>.instance_info.compare.json``.

    The name comes from the design's own top cell rather than the input file: the two
    sides of a version diff are normally the *same* file name in different directories
    (``v1/core.def`` against ``v2/core.def``), so a file-derived name would collide and
    silently lose a design. The cell library needs no such name - several LEF files are
    one library - so it is always plain ``cell_info.json``.
    """
    name = f"{block['top_name']}.instance_info"
    if compare:
        name += ".compare"
    return os.path.join(args.out, name + ".json")


def _dump_json(path, data, written=None):
    """Write a copy of the converted data where the user asked for it.

    ``written`` is the set of paths already dumped this run. A repeat means two inputs
    mapped to one output name, so say so rather than let one file quietly replace the
    other.
    """
    if written is not None:
        if path in written:
            logger.warning("two inputs convert to the same output name; %s is overwritten",
                           path)
        written.add(path)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    logger.info("wrote %s", path)
    return path


def resolve_inputs(args):
    """``(cell_info, blocks, compare_blocks, pins)`` for whichever subcommand ran.

    ``json`` returns the paths it was given. ``verilog`` and ``def`` return the converted
    data itself - dicts, not files - so a run writes nothing to disk unless ``--out DIR``
    was given, in which case the JSON is dumped there purely as a copy to inspect or feed
    back to the ``json`` subcommand.

    ``pins`` is the pin-density map's geometry, and only the ``def`` flow has any: it is read
    out of the same LEF walk that builds ``cell_info``. A ``cell_info.json`` cannot carry it,
    so the json flow passes ``None`` and that map is simply not offered.

    Split out from :func:`main` so the conversion is testable without Qt.
    """
    if args.cmd == "json":
        return (args.cell_info, list(args.block_info),
                list(args.compare_block_info) if args.compare_block_info else None, None)

    from .parsers.convert import (cell_info_from_lef, instance_info_from_def,
                                  instance_info_from_verilog)

    if args.cmd == "def":
        cells, pins = cell_info_from_lef(args.lef, with_pins=True)
    else:
        cells, pins = cell_info_from_lef(args.lef), None

    if args.cmd == "verilog":
        # One netlist, however many files it is split across.
        blocks = [instance_info_from_verilog(args.verilog, args.top)]
        compare = ([instance_info_from_verilog(args.compare_verilog,
                                               args.compare_top or args.top)]
                   if args.compare_verilog else None)
    else:
        # Each DEF is a complete design, so they stay separate blocks.
        blocks = [instance_info_from_def(path, args.top) for path in args.def_files]
        compare = ([instance_info_from_def(path, args.compare_top)
                    for path in args.compare_def] if args.compare_def else None)

    if args.out:
        # A block is named after its top cell, so the dump has to follow the conversion.
        written = set()
        _dump_json(os.path.join(args.out, "cell_info.json"), cells, written)
        for block in blocks:
            _dump_json(_block_out_path(args, block), block, written)
        for block in compare or []:
            _dump_json(_block_out_path(args, block, compare=True), block, written)

    logger.warning("%s input carries no power data: the leakage and dynamic heat maps "
                   "will be empty", args.cmd)
    return cells, blocks, compare, pins


def _run_metal(args):
    """Build the metal-density grids and open the view.

    The grids are built before the window exists, with progress logged to the terminal. For
    the sizes this is comfortable with - about 10^6 wire segments, a handful of seconds -
    that is invisible; a full-chip flat DEF would spend minutes here with no window on
    screen, and moving the build behind a visible window with a progress bar is the first
    thing to do if that becomes the normal case. Recorded rather than hidden: the same
    synchronous-startup shape is what the physical mode's performance review identified as
    its "stuck GUI at launch".
    """
    import signal
    import threading

    from .metal import build_metal

    # An interrupt asks the build to stop and keep what it has, instead of killing the job.
    # The parse checks this during its heartbeat, so the response is within ~30 s.
    stop = threading.Event()

    def on_interrupt(_signum, _frame):
        if stop.is_set():
            raise KeyboardInterrupt                   # a second ^C means it
        stop.set()
        logger.warning("metal: interrupt received; stopping after what has been read")

    previous = signal.signal(signal.SIGINT, on_interrupt)
    profiler = None
    if args.profile is not None:
        import cProfile
        profiler = cProfile.Profile()
        profiler.enable()
    if not args.def_files and not args.db_files:
        print("error: metal mode needs --def, --db, or both", file=sys.stderr)
        return 1
    if args.dump_only and not args.dump_db:
        print("error: --dump_only needs --dump-db DIR to write into", file=sys.stderr)
        return 1
    def_files = list(args.def_files or ())
    logger.info("metal: reading %d DEF file(s)%s", len(def_files),
                f" and {len(args.db_files)} db(s)" if args.db_files else "")
    try:
        data = build_metal(def_files, args.lef, args.tech_lef,
                           grid_size=args.grid_size,
                           macro_block_layers=args.macro_block_layers,
                           min_segment=args.min_segment_length, top=args.top,
                           on_progress=lambda message: logger.info("metal: %s", message),
                           cancel=stop.is_set, jobs=args.jobs,
                           min_layer=args.min_layer, max_layer=args.max_layer,
                           db_paths=args.db_files, dump_db=args.dump_db)
    except Exception as exc:  # surface load errors on the CLI, no window needed
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous)
        if profiler is not None:
            import pstats
            profiler.disable()
            stats = pstats.Stats(profiler)
            stats.sort_stats("tottime").print_stats(15)
            if args.profile:
                stats.dump_stats(args.profile)
                logger.info("metal: profile written to %s", args.profile)

    for warning in data.warnings:
        logger.warning("metal: %s", warning)

    if args.dump_only:
        # Everything this run was asked for has happened; the window is the part it did not ask
        # for. Returning here also keeps Qt out of a dump, which is what lets several of them run
        # side by side on a machine with no display.
        logger.info("metal: --dump_only: not opening a window")
        return 0

    from PyQt5.QtWidgets import QApplication

    from . import theme
    from .ui_main import MainWindow

    app = QApplication(sys.argv)
    theme.apply_theme(app)
    win = MainWindow(metal=data)
    win.show()
    return app.exec_()


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    # Metal mode takes neither the JSON structures nor the metric tree, so it has its own
    # path rather than a branch inside `resolve_inputs`.
    if args.cmd == "metal":
        return _run_metal(args)

    physical = None
    try:
        cell_info, blocks, compare_blocks, pins = resolve_inputs(args)
        design1 = load_or_build(blocks, cell_info,
                                cache_dir=args.cache_dir, force=args.force)
        design2 = None
        # Only the json and def subparsers define --physical_mode, which is how
        # "verilog has no physical mode" is enforced: the flag does not exist there.
        if getattr(args, "physical_mode", False):
            from .physical import build_physical
            physical = build_physical(blocks, cell_info,
                                      grid_size=args.grid_size,
                                      contour_gap=args.contour_gap, pins=pins)
        elif compare_blocks:
            design2 = load_or_build(compare_blocks, cell_info,
                                    cache_dir=args.cache_dir, force=args.force)
    except Exception as exc:  # surface load errors on the CLI, no window needed
        print(f"error: {exc}", file=sys.stderr)
        return 1

    from PyQt5.QtWidgets import QApplication

    from . import theme
    from .ui_main import MainWindow

    app = QApplication(sys.argv)
    theme.apply_theme(app)
    win = MainWindow(design1, design2, physical=physical,
                     threshold=args.min_instances, include_macros=args.include_macros)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
