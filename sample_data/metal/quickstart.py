"""Quick start for the metal-density sample. Run it from anywhere.

    python sample_data/metal/quickstart.py            # open the GUI on the sample
    python sample_data/metal/quickstart.py --check    # print the numbers, no GUI
    python sample_data/metal/quickstart.py --grid-size 5 --verbose

Metal mode takes four required inputs - two DEFs, a macro LEF and a tech LEF - which is more
than any other mode, and the sample is the only place those four are known to fit together.
Both paths here delegate: `--check` calls :func:`vlsi_viewer.metal.build_metal` and the GUI
path calls the real CLI, so there is no second copy of the flags to drift out of step. That
is the same contract as the repository-level `quickstart.py`.

`--check` is the one to reach for when a DEF of your own is in question: point it at the
sample first to see what a healthy map looks like, then at yours.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

SAMPLE_FILES = ("top.def", "sub.def", "cells.lef", "tech.lef")


def missing_files():
    """Which of the sample's inputs are not on disk.

    The DEFs are generated, not authored by hand, so a fresh clone that has never run the
    generator is a real case rather than a corrupt checkout.
    """
    return [name for name in SAMPLE_FILES if not os.path.exists(os.path.join(HERE, name))]


def sample_argv(extra=None):
    """The CLI arguments for the sample, as the real CLI would receive them."""
    argv = ["metal", "--def", os.path.join(HERE, "top.def"), os.path.join(HERE, "sub.def"),
            "--lef", os.path.join(HERE, "cells.lef"),
            "--tech-lef", os.path.join(HERE, "tech.lef")]
    return argv + list(extra or [])


def check(grid_size=None, macro_block_layers=None, top=None, min_layer=None,
          max_layer=None) -> int:
    """Build the metric and print what it says, without Qt."""
    import numpy as np

    from vlsi_viewer.metal import SCOPE_ALL, SCOPE_POWER, SCOPE_SIGNAL, build_metal

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    data = build_metal([os.path.join(HERE, "top.def"), os.path.join(HERE, "sub.def")],
                       [os.path.join(HERE, "cells.lef")],
                       [os.path.join(HERE, "tech.lef")],
                       grid_size=grid_size, macro_block_layers=macro_block_layers, top=top,
                       min_layer=min_layer, max_layer=max_layer)

    print(f"{data!r}")
    blocked = ", ".join(data.layers[index].name for index in data.blocked_layers) or "none"
    print(f"die {data.extent[2] - data.extent[0]:.0f} x "
          f"{data.extent[3] - data.extent[1]:.0f} um   blocked layers: {blocked}")
    if data.blockage.get("fallback_cells"):
        print(f"  {data.blockage['fallback_cells']} macro(s) declare no OBS, so the bottom "
              f"{data.macro_block_layers} layer(s) of their footprint are taken as blocked")
    print()
    print(f"{'layer':6} {'dir':4} {'pitch':>6} {'W':>5} {'S':>5} {'(W+S)/P':>8} {'mean U':>7}")
    for layer in data.layers:
        factor = (layer.width + layer.spacing) / layer.pitch if layer.pitch else 1.0
        print(f"{layer.name:6} {'H' if layer.is_horizontal else 'V':4} "
              f"{layer.pitch:6.3f} {layer.width:5.3f} {layer.spacing:5.3f} "
              f"{factor:8.3f} {data.layer_util(layer):7.3f}")

    every = data.group_kind([layer.name for layer in data.layers])
    print()
    for scope in (SCOPE_SIGNAL, SCOPE_POWER, SCOPE_ALL):
        data.set_scope(scope)
        grid = data.heat(every)
        print(f"  {scope:7} max {grid.max():6.3f}   mean over routable cells "
              f"{data.mean_util(every):6.3f}")
    assert np.isfinite(data.heat(every)).all(), "the map contains NaN, which would paint garbage"

    data.set_scope(SCOPE_ALL)
    horizontal = data.group_kind([layer.name for layer in data.horizontal])
    vertical = data.group_kind([layer.name for layer in data.vertical])
    print(f"\n  horizontal layers  max {data.max_util(horizontal):6.3f}")
    print(f"  vertical layers    max {data.max_util(vertical):6.3f}")
    print("  a cell is a real bottleneck when both read high\n")

    busiest = np.unravel_index(np.argmax(data.heat(every)), data.heat(every).shape)
    detail = data.cell_detail(int(busiest[1]), int(busiest[0]), every)
    print(f"busiest cell ({detail['ix']}, {detail['iy']}) at "
          f"x={detail['x']:.1f} y={detail['y']:.1f}")
    for entry in detail["layers"]:
        if entry["consumed"] > 0:
            print(f"    {entry['name']:6} D {entry['consumed']:8.4f}  "
                  f"C {entry['capacity']:8.4f}  U {entry['util']:6.3f}")
    print(f"    {'group':6} {detail['consumed']:8.4f} / {detail['capacity']:.4f} "
          f"= {detail['util']:.4f}")
    for warning in data.warnings:
        print(f"  warning: {warning}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="quickstart.py",
        description="Launch or check the bundled metal-density sample.",
        epilog="Extra flags are passed through to `vlsi-viewer metal` in GUI mode.")
    parser.add_argument("--check", action="store_true",
                        help="print the metric instead of opening the window")
    parser.add_argument("--grid-size", type=float, default=None, metavar="N",
                        help="heat-map grid cell size in um (default: 10)")
    parser.add_argument("--macro-block-layers", type=int, default=None, metavar="N",
                        help="fallback: how many bottom layers a macro without OBS blocks "
                             "(default: 4)")
    parser.add_argument("--top", default=None, metavar="NAME",
                        help="override the top block name")
    parser.add_argument("--min-layer", "--min_layer", dest="min_layer", type=int, default=None,
                        metavar="N",
                        help="lowest routing layer to measure, as a 1-based position in the "
                             "stack (the layer panel's row number)")
    parser.add_argument("--max-layer", "--max_layer", dest="max_layer", type=int, default=None,
                        metavar="N", help="highest routing layer to measure")
    args, extra = parser.parse_known_args(argv)

    missing = missing_files()
    if missing:
        print(f"error: the sample is incomplete, missing {', '.join(missing)}", file=sys.stderr)
        print("       generate it with:  python sample_data/metal/generate_metal.py",
              file=sys.stderr)
        return 2

    if args.check:
        return check(grid_size=args.grid_size,
                     macro_block_layers=args.macro_block_layers, top=args.top,
                     min_layer=args.min_layer, max_layer=args.max_layer)

    forwarded = list(extra)
    if args.grid_size is not None:
        forwarded += ["--grid-size", str(args.grid_size)]
    if args.macro_block_layers is not None:
        forwarded += ["--macro-block-layers", str(args.macro_block_layers)]
    if args.top is not None:
        forwarded += ["--top", args.top]
    if args.min_layer is not None:
        forwarded += ["--min-layer", str(args.min_layer)]
    if args.max_layer is not None:
        forwarded += ["--max-layer", str(args.max_layer)]

    # The real CLI, so the flags here cannot drift from the ones that exist.
    from vlsi_viewer.cli import main as cli_main
    return cli_main(sample_argv(forwarded))


if __name__ == "__main__":
    sys.exit(main())
