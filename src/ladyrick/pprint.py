#!/usr/bin/env python3
import argparse
import dataclasses
import json
import os
import re
import sys
import types
import typing

from setproctitle import getproctitle, setproctitle

from ladyrick.loader import FORMATS, auto_load
from ladyrick.print_utils import rich_print
from ladyrick.utils import class_name

if typing.TYPE_CHECKING:
    import numpy
    import torch


class Writable(typing.Protocol):
    def write(self, s: str, /) -> int:
        return 0


def get_tensor_data_repr(obj):
    match = re.match(r".*(tensor|array)\(([\[\]\n 0-9.eE+-ainf]+).*\)", repr(obj), re.DOTALL)
    assert match, repr(obj)
    return match.group(2).rstrip(", ")


class Printer:
    def __init__(self, indent="  "):
        self.indent = indent

    _dispatch = typing.OrderedDict()

    def print(self, obj, stream: typing.Optional[Writable] = None):
        self.format_object(obj, stream or sys.stdout, 0)

    def format_object(self, obj, stream: Writable, level):
        for k, v in self._dispatch.items():
            if k(self, obj):
                v(self, obj, stream, level)
                break
        else:
            stream.write(f"{obj!r}")
        if level == 0:
            stream.write("\n")

    def is_map(self, obj):
        return isinstance(obj, typing.Mapping)

    def format_map(self, obj, stream: Writable, level: int):
        class_name = obj.__class__.__name__
        if class_name == "dict":
            stream.write("{")
        else:
            stream.write(f"{class_name}({{")
        for k, v in obj.items():
            stream.write(f"\n{self.indent * (level + 1)}{k!r}: ")
            self.format_object(v, stream, level + 1)
            stream.write(",")
        if obj:
            stream.write(f"\n{self.indent * level}")
        if class_name == "dict":
            stream.write("}")
        else:
            stream.write("})")

    _dispatch[is_map] = format_map

    def is_tensor(self, obj):
        return class_name(obj) in {
            "torch.Tensor",
            "torch.nn.parameter.Parameter",
        }

    def format_tensor(self, obj: "torch.Tensor", stream: Writable, level: int):
        name = {
            "torch.Tensor": "tensor",
            "torch.nn.parameter.Parameter": "parameter",
        }[class_name(obj)]
        nele = obj.nelement()
        if nele == 0 or nele <= 5 and nele == obj.shape[-1]:
            stream.write(f"{name}(size={list(obj.shape)}, dtype={obj.dtype}, {get_tensor_data_repr(obj)})")
        else:
            stream.write(f"{name}(size={list(obj.shape)}, dtype={obj.dtype})")

    _dispatch[is_tensor] = format_tensor

    def is_ndarray(self, obj):
        return class_name(obj) == "numpy.ndarray"

    def format_ndarray(self, obj: "numpy.ndarray", stream: Writable, level: int):
        nele = obj.size
        if nele == 0 or nele <= 5 and nele == obj.shape[-1]:
            stream.write(f"array(size={list(obj.shape)}, dtype={obj.dtype}, {get_tensor_data_repr(obj)})")
        else:
            stream.write(f"array(size={list(obj.shape)}, dtype={obj.dtype})")

    _dispatch[is_ndarray] = format_ndarray

    def is_namedtuple(self, obj):
        return isinstance(obj, tuple) and hasattr(obj, "_fields")

    def format_namedtuple(self, obj, stream: Writable, level: int):
        stream.write(f"{obj.__class__.__name__}(\n")
        for k, v in zip(obj._fields, obj):
            stream.write(f"{self.indent * (level + 1)}{k}=")
            self.format_object(v, stream, level + 1)
            stream.write(",\n")
        stream.write(f"{self.indent * level})")

    _dispatch[is_namedtuple] = format_namedtuple  # must before is_simple_sequence

    def is_simple_sequence(self, obj):
        return isinstance(obj, (list, tuple, set))

    def format_simple_sequence(self, obj, stream: Writable, level: int):
        class_name = obj.__class__.__name__
        if not obj:
            if class_name in ("list", "tuple", "set"):
                stream.write(f"{obj!r}")
            elif isinstance(obj, list):
                stream.write(f"{class_name}([])")
            elif isinstance(obj, tuple):
                stream.write(f"{class_name}(())")
            else:  # set
                stream.write(f"{class_name}(set())")
            return

        if class_name not in ("list", "tuple", "set"):
            if isinstance(obj, list):
                stream.write(f"{class_name}([")
            elif isinstance(obj, tuple):
                stream.write(f"{class_name}((")
            else:  # set
                stream.write(f"{class_name}({{")
        else:
            if isinstance(obj, list):
                stream.write("[")
            elif isinstance(obj, tuple):
                stream.write("(")
            else:  # set
                stream.write("{")

        last_type = None
        items_has_same_simple_type = True
        max_render_len = 10
        for _, item in zip(range(max_render_len), obj):
            if item is not None and not isinstance(item, (int, float, complex, bool)):
                items_has_same_simple_type = False
                break
            if last_type is None:
                last_type = type(item)
            else:
                if type(item) is not last_type:
                    items_has_same_simple_type = False
                    break
        is_list_of_str = True
        for _, item in zip(range(max_render_len), obj):
            if not isinstance(item, (str, bytes)):
                is_list_of_str = False
                break

        if items_has_same_simple_type:
            if len(obj) > max_render_len:
                for i, item in zip(range(max_render_len), obj):
                    stream.write(f"{item!r}, ")
                stream.write(f"...{len(obj) - max_render_len} more")
            elif len(obj) == 1 and isinstance(obj, tuple):
                stream.write(f"{next(iter(obj))!r},")
            else:
                for i, item in enumerate(obj):
                    stream.write(f"{item!r}" if i == 0 else f", {item!r}")
        elif is_list_of_str and (
            len(obj) < max_render_len and sum(len(s) for _, s in zip(range(max_render_len), obj)) < 80
        ):
            if len(obj) == 1 and isinstance(obj, tuple):
                stream.write(f"{next(iter(obj))!r},")
            else:
                for i, item in enumerate(obj):
                    stream.write(f"{item!r}" if i == 0 else f", {item!r}")
        else:
            stream.write("\n")
            for item in obj:
                stream.write(f"{self.indent * (level + 1)}")
                self.format_object(item, stream, level + 1)
                stream.write(",\n")
            stream.write(self.indent * level)

        if class_name not in ("list", "tuple", "set"):
            if isinstance(obj, list):
                stream.write("])")
            elif isinstance(obj, tuple):
                stream.write("))")
            else:  # set
                stream.write("}})")
        else:
            if isinstance(obj, list):
                stream.write("]")
            elif isinstance(obj, tuple):
                stream.write(")")
            else:  # set
                stream.write("}")

    _dispatch[is_simple_sequence] = format_simple_sequence

    def is_namespace(self, obj):
        return isinstance(obj, (argparse.Namespace, types.SimpleNamespace)) or dataclasses.is_dataclass(obj)

    def format_namespace(self, obj, stream: Writable, level: int):
        stream.write(f"{obj.__class__.__name__}(\n")
        for k, v in vars(obj).items():
            stream.write(f"{self.indent * (level + 1)}{k}=")
            self.format_object(v, stream, level + 1)
            stream.write(",\n")
        stream.write(f"{self.indent * level})")

    _dispatch[is_namespace] = format_namespace

    def is_long_str(self, obj):
        return isinstance(obj, (str, bytes)) and len(obj) > 100

    def format_long_str(self, obj, stream: Writable, level: int):
        r = repr(obj[:100])
        stream.write(f"{r[:-1]} ...{len(obj) - 100} more{r[-1]}")

    _dispatch[is_long_str] = format_long_str


class FakeRichStream:
    def __init__(self, stderr=False):
        self.line = ""

    def write(self, s: str, /) -> int:
        self.line += s
        idx = self.line.rfind("\n")
        if self.line and idx == len(self.line) - 1:
            rich_print(self.line, end="")
            self.line = ""
        elif idx != -1:
            rich_print(self.line[:idx], end="")
            self.line = self.line[idx:]
        return len(s)


def pretty_print(model):
    Printer().print(model, FakeRichStream())


def reg_ipython_cmd():
    from IPython.core.magic import register_line_magic

    @register_line_magic
    def pp(line: str):
        if line.strip():
            pretty_print(eval(line))
        else:
            rich_print("pp is pretty_print.\nusage: pp <exps>")


@dataclasses.dataclass
class load_failed:
    file: str
    format: str
    ignore_errors: bool
    raw: bool
    exc: Exception


def main():
    if os.getenv("__pretty_print_interactive_args__"):
        args = argparse.Namespace(**json.loads(os.environ.pop("__pretty_print_interactive_args__")))
        interactive_mode = True
        setproctitle(os.environ.pop("__proctitle__"))
        sys.path[:] = json.loads(os.environ.pop("__sys_path__"))
    else:
        parser = argparse.ArgumentParser("pretty_print")
        parser.add_argument("-i", action="store_true")
        parser.add_argument("files", nargs="*")
        parser.add_argument("-e", "--ignore-errors", action="store_true")
        parser.add_argument("-r", "--raw", action="store_true", help="no map_location")
        parser.add_argument("-f", "--format", choices=FORMATS, default=FORMATS[0])
        args = parser.parse_args()
        if not args.files and not args.i:
            parser.parse_args(["-h"])  # nothing to do. print a help
            return
        interactive_mode = False
        if args.i:
            dumps = lambda obj: json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
            os.execlpe(
                sys.executable,
                sys.executable,
                "-m",
                "IPython",
                "-i",
                "--no-banner",
                "--no-confirm-exit",
                __file__,
                *args.files,
                {
                    **os.environ,
                    "__pretty_print_interactive_args__": dumps(vars(args)),
                    "__proctitle__": getproctitle(),
                    "__sys_path__": dumps(sys.path),
                },
            )
    add_to_globals = {}
    paths = []
    models = []
    add_to_globals["paths"] = paths
    add_to_globals["models"] = models
    for file in args.files:
        paths.append(file)
        try:
            model = auto_load(file, args.format, args.ignore_errors, args.raw)
        except Exception as e:
            model = load_failed(file, args.format, args.ignore_errors, args.raw, e)
        models.append(model)
    if len(models) == 1:
        add_to_globals["path"] = paths[0]
        add_to_globals["model"] = models[0]
        pretty_print(models[0])
    else:
        for file, model in zip(paths, models):
            print(file)
            pretty_print(model)
    if interactive_mode:
        if "torch" in sys.modules:
            add_to_globals["torch"] = sys.modules["torch"]
        globals().update(add_to_globals)
        reg_ipython_cmd()


if __name__ == "__main__":
    main()
