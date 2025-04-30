#!/usr/bin/env python3
import argparse
import dataclasses
import functools
import json
import os
import pickle
import re
import sys
import types
import typing

from setproctitle import getproctitle, setproctitle

if typing.TYPE_CHECKING:
    import numpy
    import torch


class CustomPickleModule:
    class ClassNotFound:
        def __init__(self, module, name, *args, **kwargs):
            self.module = module
            self.name = name
            self.args = args
            self.kwargs = kwargs

        def __repr__(self):
            comps = []
            if self.args:
                comps += [repr(a) for a in self.args]
            if self.kwargs:
                comps += [f"{k}={v!r}" for k, v in self.kwargs.items()]
            return f"{self.module}.{self.name}({', '.join(comps)})"

        def __reduce__(self):
            raise pickle.PicklingError(
                f"看到这个报错，意味着 {self.module}.{self.name} 类找不到，只能用 ClassNotFound 类来绕过 pickle load 的报错。"
                f"ClassNotFound 不可用于 pickle save"
            )

    class Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            try:
                return super().find_class(module, name)
            except (ImportError, AttributeError):
                return functools.partial(CustomPickleModule.ClassNotFound, module, name)


def class_name(obj):
    return f"{obj.__class__.__module__}.{obj.__class__.__qualname__}"


class Writable(typing.Protocol):
    def write(self, s: str, /) -> int:
        pass


def get_tensor_data_repr(obj):
    match = re.match(
        r".*(tensor|array)\(([\[\]\n 0-9.eE+-ainf]+).*\)", repr(obj), re.DOTALL
    )
    assert match, repr(obj)
    return match.group(2).rstrip(", ")


class Printer:
    def __init__(self, indent="  "):
        self.indent = indent

    _dispatch = {}

    def print(self, obj, stream: typing.Optional[Writable] = None):
        self.format_object(obj, stream or sys.stdout, 0)

    def format_object(self, obj, stream: Writable, level):
        for k, v in self._dispatch.items():
            if k(self, obj):
                v(self, obj, stream, level)
                break
        else:
            stream.write(f"{obj}")
        if level == 0:
            stream.write("\n")

    def is_dict(self, obj):
        return isinstance(obj, dict)

    def format_dict(self, obj, stream: Writable, level: int):
        class_name = obj.__class__.__name__
        if class_name == "dict":
            stream.write("{")
        else:
            stream.write(f"{class_name}({{")
        for k, v in obj.items():
            stream.write(f"\n{self.indent * (level + 1)}{k!r}: ")
            self.format_object(v, stream, level + 1)
            stream.write(",")
        if class_name == "dict":
            stream.write(f"\n{self.indent * level}}}")
        else:
            stream.write(f"\n{self.indent * level}}})")

    _dispatch[is_dict] = format_dict

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
            stream.write(
                f"{name}(size={list(obj.shape)}, dtype={obj.dtype}, {get_tensor_data_repr(obj)})"
            )
        else:
            stream.write(f"{name}(size={list(obj.shape)}, dtype={obj.dtype})")

    _dispatch[is_tensor] = format_tensor

    def is_ndarray(self, obj):
        return class_name(obj) == "numpy.ndarray"

    def format_ndarray(self, obj: "numpy.ndarray", stream: Writable, level: int):
        nele = obj.size
        if nele == 0 or nele <= 5 and nele == obj.shape[-1]:
            stream.write(
                f"array(size={list(obj.shape)}, dtype={obj.dtype}, {get_tensor_data_repr(obj)})"
            )
        else:
            stream.write(f"array(size={list(obj.shape)}, dtype={obj.dtype})")

    _dispatch[is_ndarray] = format_ndarray

    def is_simple_sequence(self, obj):
        return isinstance(obj, (list, tuple, set))

    def format_simple_sequence(self, obj, stream: Writable, level: int):
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

        class_name = obj.__class__.__name__
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
            len(obj) == 1
            or (
                len(obj) < max_render_len
                and sum(len(s) for _, s in zip(range(max_render_len), obj)) < 80
            )
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
                stream.write("}}")
        else:
            if isinstance(obj, list):
                stream.write("]")
            elif isinstance(obj, tuple):
                stream.write(")")
            else:  # set
                stream.write("}")

    _dispatch[is_simple_sequence] = format_simple_sequence

    def is_namespace(self, obj):
        return isinstance(
            obj, (argparse.Namespace, types.SimpleNamespace)
        ) or dataclasses.is_dataclass(obj)

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
        stream.write(repr(obj[:100])[:-1] + f" ...{len(obj) - 100} more'")

    _dispatch[is_long_str] = format_long_str


class FakeRichStream:
    def __init__(self, stderr=False):
        from rich.console import Console

        self.line = ""
        self.console = Console(soft_wrap=True, markup=False, stderr=stderr)

    def write(self, s: str, /) -> int:
        self.line += s
        if "\n" in s:
            self.console.print(self.line, end="")
            self.line = ""
        return len(s)


def pretty_print(model):
    Printer().print(model, FakeRichStream())


def load_torch(filepath):
    global torch
    import torch

    return torch.load(
        filepath,
        "cpu",
        weights_only=False,
        pickle_module=CustomPickleModule,
    )


def main():
    if os.getenv("__pretty_print_interactive_args__"):
        args = argparse.Namespace(
            **json.loads(os.environ.pop("__pretty_print_interactive_args__"))
        )
        interactive_mode = True
        setproctitle(os.environ.pop("__proctitle__"))
    else:
        parser = argparse.ArgumentParser("pretty_print")
        parser.add_argument("-i", action="store_true")
        parser.add_argument("files", nargs="*")
        args = parser.parse_args()
        interactive_mode = False
        if args.i:
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
                    "__pretty_print_interactive_args__": json.dumps(vars(args)),
                    "__proctitle__": getproctitle(),
                },
            )
    if interactive_mode:
        global paths, models
    paths = []
    models = []
    for file in args.files:
        paths.append(file)
        models.append(load_torch(file))
    if len(models) == 1:
        pretty_print(models[0])
    else:
        for file, model in zip(paths, models):
            print(file)
            pretty_print(model)


if __name__ == "__main__":
    main()
