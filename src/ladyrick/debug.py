import inspect
import os
import sys
import types

import IPython
import rich


def debugpy(rank=None, port=5678):
    from ladyrick.dump import try_get_rank

    if rank is None or rank == try_get_rank():
        import debugpy

        debugpy.listen(("0.0.0.0", int(port)))
        rich.print(f"[green bold]debugpy: waiting for client to connect: port is {port}[/green bold]")
        debugpy.wait_for_client()
        return debugpy.breakpoint
    else:
        return lambda: None


def _get_patched_ipython_embed():
    if hasattr(_get_patched_ipython_embed, "embed"):
        return _get_patched_ipython_embed.embed
    source = inspect.getsource(IPython.embed)
    source = source.replace("**kwargs):", "depth=0, **kwargs):")
    source = source.replace("frame = sys._getframe(1)", "frame = sys._getframe(depth + 1)")
    source = source.replace("stack_depth=2", "stack_depth=depth + 2")

    namespace = IPython.embed.__globals__.copy()

    exec(source, namespace)

    new_embed = namespace["embed"]
    _get_patched_ipython_embed.embed = new_embed
    return new_embed


def render_current_line(frame: types.FrameType, lines_around=4):
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
    embed_func = _get_patched_ipython_embed()
    embed_func(depth=depth + 1, banner1=lines, confirm_exit=False, colors="Neutral")
