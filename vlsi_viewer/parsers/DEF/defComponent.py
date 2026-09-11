from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DefComponent:

    def __init__(self, comp_name: AnyStr, model_name: AnyStr, source: AnyStr, pstatus: AnyStr, x: int, y :int, orient: AnyStr):
        self.comp_name = comp_name
        self.model_name = model_name
        self.source = source
        self.pstatus = pstatus
        self.pos_x = x
        self.pos_y = y
        self.orient = orient

    def __repr__(self):
        return f'''
DefComp
    comp_name  {self.comp_name}
    model_name {self.model_name}
    source     {self.source}
    pstatus    {self.pstatus}
    loc        {self.pos_x} {self.pos_y}
    orient     {self.orient}    
'''


