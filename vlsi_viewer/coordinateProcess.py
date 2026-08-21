from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

import numpy as np
from utils import Print


class Orient:
    '''
    ### Orientation Mapping

    | LEF/DEF | OpenAccess | Description     |
    |---------|------------|-------------    |
    | N       | R0         | North (default) |
    | S       | R180       | South           |
    | W       | R90        | West            |
    | E       | R270       | East            |
    | FN      | MY         | Flipped North   |
    | FS      | MX         | Flipped South   |
    | FW      | MX90       | Flipped West    |
    | FE      | MY90       | Flipped East    |
    '''
    DEF_OA_map = {
        'N': 'R0',
        'S': 'R180',
        'W': 'R90',
        'E': 'R270',
        'FN': 'MY',
        'FS': 'MX',
        'FW': 'MX90',
        'FE': 'MY90'
    }

    OA_DEF_map = {
        'R0': 'N',
        'R180': 'S',
        'R90': 'W',
        'R270': 'E',
        'MY': 'FN',
        'MX': 'FS',
        'MX90': 'FW',
        'MY90': 'FE'
    }

    orient_map = {
        'N': {'R': 0, 'X': False, 'Y': False},
        'S': {'R': 180, 'X': False, 'Y': False},
        'W': {'R': 90, 'X': False, 'Y': False},
        'E': {'R': 270, 'X': False, 'Y': False},
        'FN': {'R': 0, 'X': False, 'Y': True},
        'FS': {'R': 0, 'X': True, 'Y': False},
        'FW': {'R': 90, 'X': True, 'Y': False},
        'FE': {'R': 90, 'X': False, 'Y': True}
    }

    @staticmethod
    def mergeOrient(orient_name0, orient_name1) -> str:
        if orient_name0 not in Orient.orient_map or orient_name1 not in Orient.orient_map:
            Print("Error: not valid orient")
            raise ValueError
        else:
            new_orient = {'R': (Orient.orient_map[orient_name0]['R'] + Orient.orient_map[orient_name1]['R']) % 360,
                          'X': Orient.orient_map[orient_name0]['X'] ^ Orient.orient_map[orient_name1]['X'],
                          'Y': Orient.orient_map[orient_name0]['Y'] ^ Orient.orient_map[orient_name1]['Y']}
            if new_orient['X'] is True and new_orient['Y'] is True:
                new_orient['X'] = False
                new_orient['Y'] = False
                new_orient['R'] = (new_orient['R'] + 180) % 360
            if new_orient['R'] == 180 and new_orient['X'] is True:
                new_orient['X'] = False
                new_orient['Y'] = True
                new_orient['R'] = 0
            elif new_orient['R'] == 180 and new_orient['Y'] is True:
                new_orient['X'] = True
                new_orient['Y'] = False
                new_orient['R'] = 0
            elif new_orient['R'] == 270 and new_orient['X'] is True:
                new_orient['X'] = False
                new_orient['Y'] = True
                new_orient['R'] = 90
            elif new_orient['R'] == 270 and new_orient['Y'] is True:
                new_orient['X'] = True
                new_orient['Y'] = False
                new_orient['R'] = 90

            for orient_name, orient in Orient.orient_map.items():
                if new_orient == orient:
                    return orient_name
            return None


class CoordinateProcess:

    @staticmethod
    def calulateBoundingBox(pt_list: list) -> list:
        x_list = []
        y_list = []
        for pt in pt_list:
            x_list.append(pt[0])
            y_list.append(pt[1])
        return [(min(x_list), min(y_list)), (max(x_list), max(y_list))]

    @staticmethod
    def calculateUrptByOrient(ll_pt: list, orient_name: str, height: float, width: float) -> list:
        orient = Orient.orient_map.get(orient_name)
        x0 = ll_pt[0]
        y0 = ll_pt[1]
        if orient['R'] // 90 % 2 == 1:
            return [x0 + height, y0 + width]
        else:
            return [x0 + width, y0 + height]

    @staticmethod
    def calculateOriginByOrient(ll_pt: Tuple[float, float], orient_name: str, height: float, width: float) -> Tuple[float, float]:
        x0 = ll_pt[0]
        y0 = ll_pt[1]

        if orient_name not in Orient.orient_map:
            Print(f'Error: invalid orient name!!')
            raise ValueError

        if orient_name == 'N':
            return x0, y0
        elif orient_name == 'S':
            return x0 + width, y0 + height
        elif orient_name == 'W':
            return x0 + height, y0
        elif orient_name == 'E':
            return x0, y0 + height
        elif orient_name == 'FN':
            return x0 + width, y0
        elif orient_name == 'FS':
            return x0, y0 + height
        elif orient_name == 'FW':
            return x0, y0
        elif orient_name == 'FE':
            return x0 + height, y0 + width

    @staticmethod
    def dbTransform(trans_type: str, pt: Tuple[float, float], orient_name: str, origin: Tuple[float, float]) -> Tuple[float, float]:
        x = pt[0]
        y = pt[1]
        x0 = origin[0]
        y0 = origin[1]

        if orient_name not in Orient.orient_map:
            Print(f'Error: invalid orient name!!')
            raise ValueError

        if trans_type == 'to_global':
            if orient_name == 'N':
                result = [x0 + x, y0 + y]
            elif orient_name == 'S':
                result = [x0 - x, y0 - y]
            elif orient_name == 'W':
                result = [x0 - y, y0 + x]
            elif orient_name == 'E':
                result = [x0 + y, y0 - x]
            elif orient_name == 'FN':
                result = [x0 - x, y0 + y]
            elif orient_name == 'FS':
                result = [x0 + x, y0 - y]
            elif orient_name == 'FW':
                result = [x0 + y, y0 + x]
            elif orient_name == 'FE':
                result = [x0 - y, y0 - x]
        elif trans_type == 'to_local':
            if orient_name == 'N':
                result = [x - x0, y - y0]
            elif orient_name == 'S':
                result = [x0 - x, y0 - y]
            elif orient_name == 'W':
                result = [y - y0, x0 - x]
            elif orient_name == 'E':
                result = [y0 - y, x - x0]
            elif orient_name == 'FN':
                result = [x0 - x, y - y0]
            elif orient_name == 'FS':
                result = [x - x0, y0 - y]
            elif orient_name == 'FW':
                result = [y - y0, x - x0]
            elif orient_name == 'FE':
                result = [y0 - y, x0 - x]
        else:
            Print(f'Error: Invalid trans_type({trans_type}) for dbTransform, only accept to_local&to_global')
            raise ValueError
        return round(result[0], 4), round(result[1], 4)

    @staticmethod
    def dbTransformBatch(trans_type: str, pt: Tuple[np.ndarray, np.ndarray], orient_name: str,
                         origin: Tuple[float, float]) -> Tuple[List[float], List[float]]:
        x = pt[0]
        y = pt[1]
        x0 = origin[0]
        y0 = origin[1]

        if orient_name not in Orient.orient_map:
            Print(f'Error: invalid orient name!!')
            raise ValueError

        if trans_type == 'to_global':
            if orient_name == 'N':
                result = [x0 + x, y0 + y]
            elif orient_name == 'S':
                result = [x0 - x, y0 - y]
            elif orient_name == 'W':
                result = [x0 - y, y0 + x]
            elif orient_name == 'E':
                result = [x0 + y, y0 - x]
            elif orient_name == 'FN':
                result = [x0 - x, y0 + y]
            elif orient_name == 'FS':
                result = [x0 + x, y0 - y]
            elif orient_name == 'FW':
                result = [x0 + y, y0 + x]
            elif orient_name == 'FE':
                result = [x0 - y, y0 - x]
        elif trans_type == 'to_local':
            if orient_name == 'N':
                result = [x - x0, y - y0]
            elif orient_name == 'S':
                result = [x0 - x, y0 - y]
            elif orient_name == 'W':
                result = [y - y0, x0 - x]
            elif orient_name == 'E':
                result = [y0 - y, x - x0]
            elif orient_name == 'FN':
                result = [x0 - x, y - y0]
            elif orient_name == 'FS':
                result = [x - x0, y0 - y]
            elif orient_name == 'FW':
                result = [y - y0, x - x0]
            elif orient_name == 'FE':
                result = [y0 - y, x0 - x]
        else:
            Print(f'Error: Invalid trans_type({trans_type}) for dbTransform, only accept to_local&to_global')
            raise ValueError
        return np.round(result[0], 4).tolist(), np.round(result[1], 4).tolist()

    @staticmethod
    def resizeBox(box: List, resize_x: int, resize_y: int) -> List[Tuple[int, int]]:
        x_min = min([pt[0] for pt in box]) - resize_x
        x_max = max([pt[0] for pt in box]) + resize_x
        y_min = min([pt[1] for pt in box]) - resize_y
        y_max = max([pt[1] for pt in box]) + resize_y
        return [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]

    @staticmethod
    def getManhattanLength(pt_0: Tuple[float, float], pt_1: Tuple[float, float]) -> float:
        return abs(pt_0[0] - pt_1[0]) + abs(pt_0[1] - pt_1[1])


class PathOperation:

    @staticmethod
    def getPathLength(path_coords: List) -> float:
        total_distance = 0.0
        idx = 1
        for coord in path_coords[1:]:
            _coord = path_coords[idx - 1]
            total_distance += ((coord[0] - _coord[0]) ** 2 + (coord[1] - _coord[1]) ** 2) ** 0.5
            idx += 1
        return total_distance

    @staticmethod
    def mapLenToPath(path_coords: List, target_len: float) -> Tuple:
        total_distance = 0.0
        idx = 1
        for coord in path_coords[1:]:
            _coord = path_coords[idx - 1]
            delta = ((coord[0] - _coord[0]) ** 2 + (coord[1] - _coord[1]) ** 2) ** 0.5
            if total_distance + delta >= target_len:
                delta_x = coord[0] - _coord[0]
                delta_y = coord[1] - _coord[1]
                out_coord = (round(delta_x * (target_len - total_distance) / delta + _coord[0], 4),
                             round(delta_y * (target_len - total_distance) / delta + _coord[1], 4))
                return out_coord
            else:
                total_distance += delta
            idx += 1
        Print(f'ERROR: {target_len} is more than total len of path {path_coords}')
        raise ValueError

    @staticmethod
    def getEvenCoordInPath(path_coords: List, cnt: int) -> List:
        if len(path_coords) < 2:
            Print(f'ERROR: Invalid path_coords {path_coords} for getEvenCoordInPath function')
            return [(0, 0)]
        elif cnt == 0:
            return []
        else:
            total_distance = PathOperation.getPathLength(path_coords)
            period = total_distance / (cnt + 1)
            return list(map(PathOperation.mapLenToPath, [path_coords for _ in range(1, cnt + 1)], [period * ii for ii in range(1, cnt + 1)]))

    @staticmethod
    def assignPathNode(path_coords: List, cnt: int, lbias=None, rbias=None) -> List:
        if cnt == 0:
            return []
        total_distance = PathOperation.getPathLength(path_coords)
        period = total_distance / cnt
        if len(path_coords) < 2:
            Print(f'ERROR: Invalid path_coords {path_coords} for assignPathNode function')
            return [(0, 0)]
        elif cnt == 1:
            return [PathOperation.mapLenToPath(path_coords, period / 2)]
        else:
            if lbias is None:
                lbias = period / 2
            if rbias is None:
                rbias = period / 2
            len_list = [lbias]
            for ii in range(1, cnt):
                len_list.append(ii * (total_distance - lbias - rbias) / (cnt - 1) + lbias)
            return list(map(PathOperation.mapLenToPath, [path_coords for _ in range(1, cnt + 1)], len_list))

    @staticmethod
    def isBetween(a: tuple, b: tuple, c: tuple):
        if a == b:
            return False
        a_x = a[0]
        a_y = a[1]
        b_x = b[0]
        b_y = b[1]
        c_x = c[0]
        c_y = c[1]
        cross_product = (c_y - a_y) * (b_x - a_x) - (c_x - a_x) * (b_y - a_y)
        epsilon = 0.001
        if abs(cross_product) > epsilon:
            return False
        dot_product = (c_x - a_x) * (b_x - a_x) + (c_y - a_y) * (b_y - a_y)
        if dot_product < 0:
            return False
        squared_lengthba = (b_x - a_x) * (b_x - a_x) + (b_y - a_y) * (b_y - a_y)
        if dot_product > squared_lengthba:
            return False
        return True

    @staticmethod
    def cutPathByPoint(path_coord: List, point: Tuple, reverse_flag=False):
        idx = 1
        out_coords = []
        if reverse_flag:
            path = list(reversed(path_coord))
        else:
            path = path_coord
        for coord in path[1:]:
            _coord = path[idx - 1]
            out_coords.append(_coord)
            if PathOperation.isBetween(_coord, coord, point):
                out_coords.append(point)
                if reverse_flag:
                    return list(reversed(out_coords))
                else:
                    return out_coords
            idx += 1
        Print(f'ERROR: {point} is not on {path_coord} in cutPathByPoint function')

    @staticmethod
    def cutPathBy2Point(path_coords: List, point_0: Tuple[float, float], point_1: Tuple[float, float]):
        _path_coords = list(reversed(PathOperation.cutPathByPoint(path_coords, point_1)))
        __path_coords = PathOperation.cutPathByPoint(_path_coords, point_0)
        return list(reversed(__path_coords))

    @staticmethod
    def cutPathByLen(path_coords: list, target_len: float) -> list:
        total_distance = 0.0
        idx = 1
        out_coords = []
        for coord in path_coords[1:]:
            _coord = path_coords[idx - 1]
            out_coords.append(_coord)
            delta = ((coord[0] - _coord[0]) ** 2 + (coord[1] - _coord[1]) ** 2) ** 0.5
            if total_distance + delta >= target_len:
                delta_x = coord[0] - _coord[0]
                delta_y = coord[1] - _coord[1]
                end_coord = (round(delta_x * (target_len - total_distance) / delta + _coord[0], 4),
                             round(delta_y * (target_len - total_distance) / delta + _coord[1], 4))
                out_coords.append(end_coord)
                return out_coords
            else:
                total_distance += delta
            idx += 1
        Print(f'ERROR: {target_len} is more than total len of path {path_coords}')
        raise ValueError


