"ladyrick's tools"

from typing import TYPE_CHECKING


def __getattr__(name):
    from importlib import import_module

    if name in (
        "allgather",
        "debug",
        "loader",
        "pickle",
        "pprint",
        "print_utils",
        "torch",
        "typing",
        "utils",
        "vars",
    ):
        return import_module(f"ladyrick.{name}")
    elif name in ("pretty_print",):
        m = import_module("ladyrick.pprint")
    elif name in ("class_name", "utc_8_now", "get_timestr"):
        m = import_module("ladyrick.utils")
    elif name in ("dump", "Dump", "V", "Vars"):
        m = import_module("ladyrick.vars")
    elif name in ("debugpy", "embed"):
        m = import_module("ladyrick.debug")
    elif name in ("parallel_print", "rich_print", "print_col", "print_table"):
        m = import_module("ladyrick.print_utils")
    elif name in ("rank", "print_rank_0", "print_rank_last"):
        m = import_module("ladyrick.torch")
    elif name in ("type_like",):
        m = import_module("ladyrick.typing")
    else:
        raise AttributeError(name)
    return getattr(m, name)


if TYPE_CHECKING:
    from ladyrick.debug import debugpy, embed  # noqa
    from ladyrick.pprint import pretty_print  # noqa
    from ladyrick.print_utils import parallel_print, print_col, print_table, rich_print  # noqa
    from ladyrick.torch import print_rank_0, print_rank_last, rank  # noqa
    from ladyrick.typing import type_like  # noqa
    from ladyrick.utils import class_name, get_timestr, utc_8_now  # noqa
    from ladyrick.vars import Dump, V, Vars, dump  # noqa
    from ladyrick import allgather  # noqa
    from ladyrick import debug  # noqa
    from ladyrick import loader  # noqa
    from ladyrick import pickle  # noqa
    from ladyrick import pprint  # noqa
    from ladyrick import print_utils  # noqa
    from ladyrick import torch  # noqa
    from ladyrick import typing  # noqa
    from ladyrick import utils  # noqa
    from ladyrick import vars  # noqa
