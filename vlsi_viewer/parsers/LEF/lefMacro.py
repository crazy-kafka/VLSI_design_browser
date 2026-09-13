from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass


from .lefPin import LefPin


class LefMacro:

    def __init__(self, macro_name: str):
        self.__macro = {'name': macro_name,
                        'class': 'CORE',
                        'size': (0.0, 0.0),
                        'pin': {},
                        'input_pin_num': 0,
                        'output_pin_num': 0,
                        'inout_pin_num': 0,
                        'obs': {}}

    def macroName(self) -> str:
        return self.__macro['name']

    def macroClass(self) -> str:
        return self.__macro['class']

    def size(self) -> Tuple[float, float]:
        return self.__macro['size']

    def obstructions(self) -> Dict[str, List[Tuple[float, float, float, float]]]:
        """``OBS`` geometry by layer, in the macro's own coordinates: layer -> rects.

        An empty dict means the macro declares no obstructions at all, which is a different
        thing from declaring some that turn out to be negligible - the caller decides what to
        do with either, but it can only tell them apart if the parser does not conflate them.

        Copied on the way out: the caller filters this geometry, and a consumer that mutated
        the lists in place would poison the macro for every other consumer.
        """
        return {layer: list(rects) for layer, rects in self.__macro['obs'].items()}

    def pins(self) -> List[LefPin]:
        return list(self.__macro['pin'].values())

    def pin(self, pin_name: str) -> LefPin:
        return self.__macro['pin'][pin_name]

    def getInputPinNum(self):
        return self.__macro['input_pin_num']

    def getOutputPinNum(self):
        return self.__macro['output_pin_num']

    def getInoutPinNum(self):
        return self.__macro['inout_pin_num']

    def setClassType(self, class_type: str):
        self.__macro['class'] = class_type

    def setSize(self, width: float, height: float):
        self.__macro['size'] = (width, height)

    def setPin(self, pin_name, direction, use, layer, shape):
        self.__macro['pin'].update({pin_name: LefPin(pin_name, direction, use ,layer, shape)})

    def setInputPinNum(self, N):
        self.__macro['input_pin_num'] = N

    def setOutputPinNum(self, N):
        self.__macro['output_pin_num'] = N

    def setInoutPinNum(self, N):
        self.__macro['inout_pin_num'] = N

    def setObstruction(self, layer: str, rect: Tuple[float, float, float, float]):
        self.__macro['obs'].setdefault(layer, []).append(rect)





