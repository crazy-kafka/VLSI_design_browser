"""Launch the GUI on the bundled samples - no argument lists to type.

    python quickstart.py            list the shortcuts
    python quickstart.py json       sample_data/*.json           (two-version compare)
    python quickstart.py physical   sample_data/physical/*.json  (2-D density heat map)
    python quickstart.py def        sample_data/eda/core.def   + cells.lef
    python quickstart.py verilog    sample_data/eda/core.v     + cells.lef

Extra flags are passed through to the real CLI, so these still work:

    python quickstart.py def --grid_size 2.0 --verbose
    python quickstart.py json --min-instances 0

Each shortcut only builds the argv for ``vlsi_viewer.cli.main``, which stays the single
source of truth for flags and validation - nothing here can drift from the real CLI.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_data")

SHORTCUTS = {
    "json": ("sample_data/*.json", "two-version compare"),
    "physical": ("sample_data/physical/*.json", "2-D density heat map"),
    "def": ("sample_data/eda/core.def", "DEF + LEF + power JSON, heat map"),
    "verilog": ("sample_data/eda/core.v", "Verilog + LEF, tree only"),
    "metal": ("sample_data/metal/*.def", "DEF + tech LEF, metal density"),
}


def argv_for(name):
    """The CLI arguments for a shortcut, or raise KeyError."""
    if name == "json":
        return ["json",
                "--cell_info", os.path.join(SAMPLE, "cell_info.json"),
                "--block_info", os.path.join(SAMPLE, "instance_info.json"),
                os.path.join(SAMPLE, "block_B.instance_info.json"),
                "--compare_block_info", os.path.join(SAMPLE, "instance_info_v2.json"),
                os.path.join(SAMPLE, "block_B.instance_info_v2.json")]
    if name == "physical":
        p = os.path.join(SAMPLE, "physical")
        return ["json", "--cell_info", os.path.join(p, "cell_info.json"),
                "--block_info", os.path.join(p, "instance_info.json"),
                os.path.join(p, "CORE.json"), os.path.join(p, "IFU.json"),
                os.path.join(p, "IEX.json"), os.path.join(p, "LSU.json"),
                "--physical_mode"]
    eda = os.path.join(SAMPLE, "eda")
    if name == "def":
        # DEF carries placement, so this flow gets the heat map; drop the flag for the
        # tree on its own. The DEF itself carries no power, so --json fills it in and
        # the leakage and dynamic maps have something to draw.
        return ["def", "--def", os.path.join(eda, "core.def"),
                "--lef", os.path.join(eda, "cells.lef"),
                "--json", os.path.join(eda, "core.power.json"), "--physical_mode"]
    if name == "verilog":
        return ["verilog", "--verilog", os.path.join(eda, "core.v"),
                "--lef", os.path.join(eda, "cells.lef"), "--top", "core"]
    if name == "metal":
        metal = os.path.join(SAMPLE, "metal")
        # A hierarchy is normally several DEFs: the top one places the sub-block, and only
        # together do they describe a design.
        return ["metal", "--def", os.path.join(metal, "top.def"),
                os.path.join(metal, "sub.def"),
                "--lef", os.path.join(metal, "cells.lef"),
                "--tech-lef", os.path.join(metal, "tech.lef")]
    raise KeyError(name)


def usage(stream=sys.stdout):
    print("Launch the GUI on the bundled samples.\n", file=stream)
    print("Usage: python quickstart.py <shortcut> [extra CLI flags]\n", file=stream)
    print("Shortcuts:", file=stream)
    for name, (sample, what) in SHORTCUTS.items():
        print(f"  {name:<9} {sample:<32} {what}", file=stream)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        usage()
        return 0
    name = argv[0]
    if name not in SHORTCUTS:
        print(f"error: unknown shortcut {name!r}\n", file=sys.stderr)
        usage(sys.stderr)
        return 2

    args = argv_for(name)
    # The first path in argv is the sample input; missing samples mean the repo checkout
    # is incomplete or generated data was deleted.
    source = next((a for a in args[1:] if os.sep in a or "/" in a), None)
    if source and not os.path.exists(source):
        print(f"error: sample input not found: {source}", file=sys.stderr)
        return 1

    from vlsi_viewer.cli import main as cli_main

    return cli_main(args + argv[1:])


if __name__ == "__main__":
    sys.exit(main())
