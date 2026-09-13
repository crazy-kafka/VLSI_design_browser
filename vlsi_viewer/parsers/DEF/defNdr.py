from __future__ import annotations
from typing import AnyStr, Dict, List


class DefNdrLayer:
    """One ``+ LAYER`` entry of a non-default rule.

    Distances are in DEF database units exactly as written; the caller scales them, the
    same way it scales wire coordinates. Every field is optional - the reference makes
    them all so, and a rule commonly overrides only some of them on the layers it names.
    """

    def __init__(self, layer_name: AnyStr):
        self.layer_name = layer_name
        self.width = None
        self.spacing = None
        self.diagwidth = None
        self.wireext = None

    def __repr__(self):
        fields = ", ".join(
            f"{name}={value}" for name, value in
            (("width", self.width), ("spacing", self.spacing),
             ("diagwidth", self.diagwidth), ("wireext", self.wireext))
            if value is not None)
        return f"DefNdrLayer {self.layer_name}({fields})"


class DefNdrRule:
    """A named non-default rule: per-layer width and spacing overrides.

    A net carrying ``+ NONDEFAULTRULE <name>`` routes at these widths and spacings
    instead of the layer defaults - the 2W2S clock rule is the usual example, and it
    roughly doubles both, so ignoring it understates a clock region's metal by about 2x.

    A rule may override only some layers; a layer it does not name keeps the LEF default.
    """

    def __init__(self, rule_name: AnyStr):
        self.rule_name = rule_name
        self.hardspacing = False
        self.layers: Dict[AnyStr, DefNdrLayer] = {}
        # Clause kinds seen but not modelled, kept so a caller can tell "the rule states
        # nothing about spacing" apart from "we did not read that part".
        self.unparsed: List[AnyStr] = []

    def __repr__(self):
        out = [f"DefNdrRule {self.rule_name}"
               + (" hardspacing" if self.hardspacing else "")]
        for layer in self.layers.values():
            out.append(f"  {layer}")
        for clause in self.unparsed:
            out.append(f"  ({clause} not modelled)")
        return "\n".join(out)
