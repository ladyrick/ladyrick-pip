import os
import sys
from typing import Literal, overload

from ladyrick.typing import type_like


@overload
def rank(allow_none: Literal[False] = False) -> int:
    pass


@overload
def rank(allow_none: Literal[True]) -> int | None:
    pass


def rank(allow_none=False) -> int | None:
    try:
        return int(os.getenv("RANK", ""))
    except Exception:
        pass

    if "torch" in sys.modules:
        # 如果之前从来没 import 过，则放弃这种获取 rank 的方式
        # 避免首次 import torch 导致的耗时
        try:
            import torch.distributed as dist

            return dist.get_rank()
        except Exception:
            pass
    if allow_none:
        return None
    raise RuntimeError("cannot get rank")


@overload
def world_size(allow_none: Literal[False] = False) -> int:
    pass


@overload
def world_size(allow_none: Literal[True]) -> int | None:
    pass


def world_size(allow_none=False) -> int | None:
    try:
        return int(os.getenv("WORLD_SIZE", ""))
    except Exception:
        pass

    if "torch" in sys.modules:
        # 如果之前从来没 import 过，则放弃这种获取 rank 的方式
        # 避免首次 import torch 导致的耗时
        try:
            import torch.distributed as dist

            return dist.get_world_size()
        except Exception:
            pass
    if allow_none:
        return None
    raise RuntimeError("cannot get world_size")


@type_like(print)
def print_rank_0(
    *values,
    sep: str | None = " ",
    end: str | None = "\n",
    file=None,
    flush=False,
):
    r = rank(True)
    if r is None or r == 0:
        print(*values, sep=sep, end=end, file=file, flush=flush)


@type_like(print)
def print_rank_last(
    *values,
    sep: str | None = " ",
    end: str | None = "\n",
    file=None,
    flush=False,
):
    r = rank(True)
    if r is None or r == world_size() - 1:
        print(*values, sep=sep, end=end, file=file, flush=flush)
