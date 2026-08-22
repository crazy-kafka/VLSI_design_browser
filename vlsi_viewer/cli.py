"""Linux-style CLI launcher for the VLSI hierarchy viewer."""
import argparse
import logging
import sys

from . import __version__, config
from .metrics import load_or_build


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="vlsi-viewer",
        description="VLSI design hierarchy visualization tool.",
    )
    parser.add_argument("--cell_info", required=True, metavar="CELL",
                        help="path to cell_info.json")
    parser.add_argument("--block_info", required=True, nargs="+", metavar="BLOCK",
                        help="one or more instance_info.json block files")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--compare_block_info", nargs="+", metavar="BLOCK",
                      help="instance_info.json block files for the second design "
                           "(reuses --cell_info)")
    mode.add_argument("--physical_mode", action="store_true",
                      help="render a 2-D heat map (layout view) instead of compare")
    parser.add_argument(
        "--min-instances", type=int, default=config.DEFAULT_MIN_INST_COUNT, metavar="N",
        help="hide hierarchies with fewer than N instances (default: %(default)s)")
    parser.add_argument(
        "--grid_size", type=float, default=config.DEFAULT_GRID_SIZE, metavar="N",
        help="physical-mode heat-map grid cell size (default: %(default)s)")
    parser.add_argument(
        "--contour_gap", type=float, default=None, metavar="N",
        help="physical-mode hierarchy contour merge gap; defaults to "
             f"{config.DEFAULT_CONTOUR_GAP_FACTOR} x grid_size")
    parser.add_argument("--include-macros", action="store_true",
                        help="show macro count/area columns")
    parser.add_argument("--cache-dir", metavar="DIR",
                        help="pickle cache directory override")
    parser.add_argument("--force", action="store_true",
                        help="ignore cache and re-preprocess")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="verbose (debug) logging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    physical = None
    try:
        design1 = load_or_build(args.block_info, args.cell_info,
                                cache_dir=args.cache_dir, force=args.force)
        design2 = None
        if args.physical_mode:
            from .physical import build_physical
            physical = build_physical(args.block_info, args.cell_info,
                                      grid_size=args.grid_size,
                                      contour_gap=args.contour_gap)
        elif args.compare_block_info:
            design2 = load_or_build(args.compare_block_info, args.cell_info,
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
