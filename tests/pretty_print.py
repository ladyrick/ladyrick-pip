import dataclasses
from typing import Mapping
from ladyrick.pprint import pretty_print as pp

from collections import namedtuple


A = namedtuple("A", "a b c")


class aSet(set):
    pass


class aList(list):
    pass


class aTuple(tuple):
    pass


class aDict(dict):
    pass


class aMap(Mapping):
    def __init__(self, data=None):
        self._data = data or {}

    def __getitem__(self, k):
        return self._data[k]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


@dataclasses.dataclass
class Data:
    a: int
    b: str


pp(
    {
        "namedtuple": A(1, 2, 3),
        "list": [],
        "dict": {},
        "tuple": (),
        "set": set(),
        "longstr": ["+" * 1000] * 1,
        "longstr2": ["+" * 1000] * 2,
        "aSet": aSet(),
        "aTuple": aTuple(),
        "aList": aList(),
        "aDict": aDict(),
        "aMap": aMap(),
        "aSet2": aSet([1, 2]),
        "aTuple2": aTuple([1, 2]),
        "aList2": aList([1, 2]),
        "aDict2": aDict([(1, 1), (2, 2)]),
        "aMap2": aMap({1: 1, 2: 2}),
        "dataclass": Data(1, "2"),
    }
)
