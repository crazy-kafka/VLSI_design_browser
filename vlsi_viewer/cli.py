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
    parser.add_argument("instance_info", help="path to instance_info.json")
    parser.add_argument("cell_info", help="path to cell_info.json")
    parser.add_argument(
        "--compare", nargs=2, metavar=("INSTANCE", "CELL"),
        help="second (instance_info.json, cell_info.json) pair for two-version diff")
    parser.add_argument(
        "--min-instances", type=int, default=config.DEFAULT_MIN_INST_COUNT, metavar="N",
        help="hide hierarchies with fewer than N instances (default: %(default)s)")
    parser.add_argument("--include-macros", action="store_true",
                        help="show macro count/area columns")
    parser.add_argument("--cache-dir", metavar="DIR",
                        help="pickle cache directory override")
    parser.add_argument("--force", action="store_true",
                        help="ignore cache and re-preprocess")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)

    try:
        design1 = load_or_build(args.instance_info, args.cell_info,
                                cache_dir=args.cache_dir, force=args.force)
        design2 = None
        if args.compare:
            design2 = load_or_build(args.compare[0], args.compare[1],
                                    cache_dir=args.cache_dir, force=args.force)
    except Exception as exc:  # surface load errors on the CLI, no window needed
        print(f"error: {exc}", file=sys.stderr)
        return 1

    from PyQt5.QtWidgets import QApplication

    from . import theme
    from .ui_main import MainWindow

    app = QApplication(sys.argv)
    theme.apply_theme(app)
    win = MainWindow(design1, design2,
                     threshold=args.min_instances, include_macros=args.include_macros)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
