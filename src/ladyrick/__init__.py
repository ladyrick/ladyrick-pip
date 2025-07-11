"ladyrick's tools"

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ladyrick import allgather  # noqa
    from ladyrick import debug  # noqa
    from ladyrick import loader  # noqa
    from ladyrick import pickle  # noqa
    from ladyrick import pprint  # noqa
    from ladyrick import print_utils  # noqa
    from ladyrick import terminal  # noqa
    from ladyrick import torch  # noqa
    from ladyrick import typing  # noqa
    from ladyrick import utils  # noqa
    from ladyrick import vars  # noqa
    from ladyrick.debug import debugpy, embed, pdb, remote_pdb  # noqa
    from ladyrick.loader import auto_load  # noqa
    from ladyrick.pprint import pretty_print  # noqa
    from ladyrick.print_utils import parallel_print, print_col, print_table, rich_print  # noqa
    from ladyrick.terminal import forward_terminal  # noqa
    from ladyrick.torch import print_rank_0, print_rank_last, rank  # noqa
    from ladyrick.typing import type_like  # noqa
    from ladyrick.utils import class_name, get_local_ip, get_timestr, utc_8_now  # noqa
    from ladyrick.vars import Dump, V, Vars, dump  # noqa


def __getattr__(name):
    # lazy import
    import_from_where = getattr(__getattr__, "import_from_where", {})
    if not import_from_where:
        import pathlib
        import re

        __getattr__.import_from_where = import_from_where
        cur_file_content = pathlib.Path(__file__).read_text()
        for line in cur_file_content.split("\n"):
            if m := re.match(r"^ +from (ladyrick[a-zA-Z0-9._]*) import ([a-zA-Z0-9_, ]+)  # noqa", line):
                module = m.group(1)
                for n in m.group(2).split(", "):
                    import_from_where[n.strip()] = module

    from importlib import import_module

    if name in import_from_where:
        module_name = import_from_where[name]
        if "." in module_name:
            return getattr(import_module(module_name), name)
        else:
            return import_module(f"{module_name}.{name}")
    raise AttributeError(name)
