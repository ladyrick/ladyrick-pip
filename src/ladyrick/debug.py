import inspect
import os
import sys
import types
from typing import Callable, ParamSpec, TypeVar

from ladyrick.print_utils import rich_print

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


def debugpy(rank: int | None = None, port=5678):
    from ladyrick.torch import rank as get_rank

    if rank is None or rank == get_rank():
        import debugpy as debugpy_module
        from debugpy.server.api import breakpoint as debugpy_breakpoint

        from ladyrick.utils import get_local_ip

        if not hasattr(debugpy, "_patched_breakpoint"):

            @patch_func_code(debugpy_breakpoint)
            def _patched_breakpoint(source: str) -> str:
                return source.replace("sys._getframe()", "sys._getframe(1)")

            debugpy._patched_breakpoint = _patched_breakpoint

        debugpy_module.listen(("0.0.0.0", int(port)))

        rich_print(
            f"[green bold][debugpy] waiting for client to connect: ip is {get_local_ip()}, port is {port}[/green bold]",
            markup=True,
        )
        debugpy_module.wait_for_client()
        debugpy._patched_breakpoint()


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


def embed(depth=0):
    frame = sys._getframe(depth + 1)
    lines = "\n".join(render_current_line(frame))
    if not hasattr(embed, "_patched_embed"):
        import IPython

        @patch_func_code(IPython.embed)
        def _patched_embed(source: str) -> str:
            source = source.replace("**kwargs):", "depth=0, **kwargs):")
            source = source.replace("frame = sys._getframe(1)", "frame = sys._getframe(depth + 1)")
            source = source.replace("stack_depth=2", "stack_depth=depth + 2")
            return source

        embed._patched_embed = _patched_embed
    embed._patched_embed(depth=depth + 1, banner1=lines, confirm_exit=False, colors="Neutral")


def pdb(frame: types.FrameType | None = None):
    from IPython.terminal.debugger import TerminalPdb

    TerminalPdb().set_trace(frame or sys._getframe().f_back)


def remote_pdb(frame: types.FrameType | None = None, port=9963):
    from ladyrick.terminal import forward_terminal

    ft = forward_terminal(port=port)
    ft.start()

    # 必须在 ft.start() 之后 import
    # 不要在外面 import IPython，会提前初始化全局变量，误以为 stdout 不是 tty
    from IPython.terminal.debugger import TerminalPdb

    pdb = TerminalPdb()
    old_do_continue = pdb.do_continue

    def new_do_continue(*a, **k):
        ft.stop()
        return old_do_continue(*a, **k)

    pdb.do_c = pdb.do_cont = pdb.do_continue = new_do_continue

    pdb.set_trace(frame or sys._getframe().f_back)
