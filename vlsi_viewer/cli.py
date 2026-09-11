"""Linux-style CLI launcher for the VLSI hierarchy viewer.

Three input flows, one per subcommand:

``json``
    Pre-processed ``cell_info.json`` + ``instance_info.json`` (the original interface).
``verilog``
    Gate-level Verilog plus a macro LEF. A netlist has no placement, so this flow has
    no physical mode - the flag does not exist on the subparser at all.
``def``
    DEF plus a macro LEF. DEF carries placement, so physical mode works here.

The ``verilog`` and ``def`` flows convert their inputs into exactly the JSON the
``json`` flow consumes, writing it beside the input (or into ``--out``) so it can be
inspected and fed back in. Nothing downstream can tell the difference.
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
    parser.add_argument(
        "--min-instances", type=int, default=config.DEFAULT_MIN_INST_COUNT, metavar="N",
        help="hide hierarchies with fewer than N instances (default: %(default)s)")
    parser.add_argument("--include-macros", action="store_true",
                        help="show macro count/area columns")
    parser.add_argument("--cache-dir", metavar="DIR",
                        help="pickle cache directory override")
    parser.add_argument("--force", action="store_true",
                        help="ignore cache and re-preprocess")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="verbose (debug) logging")


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
                   help="where to write the generated JSON (default: beside the input)")
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
                   help="where to write the generated JSON (default: beside the input)")
    _add_physical(p)
    _add_shared(p)

    return parser.parse_args(argv)


def _out_path(args, source, suffix):
    """Generated-JSON path for ``source``: beside it, or under ``--out``.

    The suffix is appended to the whole file name (``core.def`` ->
    ``core.def.instance_info.json``) so a ``core.def`` and a ``core.v`` in one
    directory cannot collide.
    """
    name = os.path.basename(source) + suffix
    directory = args.out or os.path.dirname(source)
    return os.path.join(directory, name) if directory else name


def _write_json(path, data):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    logger.info("wrote %s", path)
    return path


def resolve_inputs(args):
    """``(cell_info, blocks, compare_blocks)`` paths for whichever subcommand ran.

    For ``json`` these are the arguments as given. For ``verilog``/``def`` the inputs
    are converted first: the LEF becomes a ``cell_info.json`` and each netlist/DEF
    becomes an ``instance_info.json``, which is what the rest of the pipeline reads.
    Split out from :func:`main` so the conversion is testable without Qt.
    """
    if args.cmd == "json":
        return (args.cell_info, list(args.block_info),
                list(args.compare_block_info) if args.compare_block_info else None)

    from .parsers.convert import (cell_info_from_lef, instance_info_from_def,
                                  instance_info_from_verilog)

    cell_path = _write_json(_out_path(args, args.lef[0], ".cell_info.json"),
                            cell_info_from_lef(args.lef))
    if args.cmd == "verilog":
        convert, top = instance_info_from_verilog, args.top
        compare_top = args.compare_top or args.top
        sources, compare = args.verilog, args.compare_verilog
    else:
        convert, top = instance_info_from_def, args.top
        compare_top = args.compare_top
        sources, compare = args.def_files, args.compare_def

    blocks = [_write_json(_out_path(args, path, ".instance_info.json"),
                          convert(path, top)) for path in sources]
    compare_paths = None
    if compare:
        compare_paths = [_write_json(_out_path(args, path, ".instance_info.json"),
                                     convert(path, compare_top)) for path in compare]
    logger.warning("%s input carries no power data: the leakage and dynamic heat maps "
                   "will be empty", args.cmd)
    return cell_path, blocks, compare_paths


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    physical = None
    try:
        cell_info, blocks, compare_blocks = resolve_inputs(args)
        design1 = load_or_build(blocks, cell_info,
                                cache_dir=args.cache_dir, force=args.force)
        design2 = None
        # Only the json and def subparsers define --physical_mode, which is how
        # "verilog has no physical mode" is enforced: the flag does not exist there.
        if getattr(args, "physical_mode", False):
            from .physical import build_physical
            physical = build_physical(blocks, cell_info,
                                      grid_size=args.grid_size,
                                      contour_gap=args.contour_gap)
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
