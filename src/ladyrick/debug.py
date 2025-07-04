import inspect
import os
import sys
import types
from subprocess import check_output
from typing import Callable, ParamSpec, TypeVar

import IPython
import rich

try:
    from debugpy.server.api import breakpoint as debugpy_breakpoint
except ImportError:

    def debugpy_breakpoint():
        return None


P = ParamSpec("P")
T = TypeVar("T")


def patch_func_code(func: Callable[P, T]) -> Callable[[Callable[[str], str]], Callable[P, T]]:
    def decorator(modify_code_func: Callable[[str], str]) -> Callable[P, T]:
        source = inspect.getsource(func)
        source_lines = source.split("\n")
        indent = min(len(line) - len(line.lstrip()) for line in source_lines if line.strip())
        if indent > 0:
            source = "\n".join(line[indent:] for line in source_lines)
        source = modify_code_func(source)
        namespace = func.__globals__.copy()
        exec(source, namespace)
        new_func = namespace[func.__name__]

        return new_func

    return decorator


@patch_func_code(debugpy_breakpoint)
def _patched_breakpoint(source: str) -> str:
    return source.replace("sys._getframe()", "sys._getframe(1)")


def debugpy(rank: int | None = None, port=5678):
    from ladyrick.torch import rank as get_rank

    if rank is None or rank == get_rank():
        import debugpy

        debugpy.listen(("0.0.0.0", int(port)))
        ips = check_output(["hostname", "-I"]).decode()
        rich.print(f"[green bold]debugpy: waiting for client to connect: ip is {ips}, port is {port}[/green bold]")
        debugpy.wait_for_client()
        _patched_breakpoint()


def render_current_line(frame: types.FrameType | None = None, lines_around=4):
    if frame is None:
        frame = sys._getframe(1)
    frame_info = inspect.getframeinfo(frame)
    line_no = frame_info.lineno
    filename = frame_info.filename

    str_lines: list[str] = []
    if not os.path.isfile(filename):
        return str_lines

    display_start_line = max(1, line_no - lines_around)
    display_end_line = line_no + lines_around
    display_lines = []
    with open(filename) as f:
        for i, line in enumerate(f, 1):
            if i < display_start_line:
                pass
            elif i <= display_end_line:
                display_lines.append(line)
            else:
                break
    display_end_line = display_start_line + len(display_lines) - 1

    line_no_width = len(str(display_end_line))
    for i, line in enumerate(display_lines, display_start_line):
        str_line = " >>> " if i == line_no else "     "
        str_line += f"{i:{line_no_width}d} | {line.rstrip()}"
        str_lines.append(str_line)
    return str_lines


@patch_func_code(IPython.embed)
def _patched_embed(source: str) -> str:
    source = source.replace("**kwargs):", "depth=0, **kwargs):")
    source = source.replace("frame = sys._getframe(1)", "frame = sys._getframe(depth + 1)")
    source = source.replace("stack_depth=2", "stack_depth=depth + 2")
    return source


def embed(depth=0):
    frame = sys._getframe(depth + 1)
    lines = "\n".join(render_current_line(frame))
    _patched_embed(depth=depth + 1, banner1=lines, confirm_exit=False, colors="Neutral")
