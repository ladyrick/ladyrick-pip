import builtins
import itertools

builtin_print = builtins.print
_stdout_console = _stderr_console = None


def parallel_print(
    *values: object,
    sep: str | None = " ",
    end: str | None = "\n",
    file=None,
    flush=False,
):
    sep = " " if sep is None else sep
    end = " " if end is None else end
    assert isinstance(sep, str) and isinstance(end, str)
    output_str = sep.join(str(v) for v in values) + end
    builtin_print(output_str, end="", file=file, flush=True)


def rich_print(
    *values: object,
    sep: str | None = " ",
    end: str | None = "\n",
    file=None,
    flush=False,
):
    sep = " " if sep is None else sep
    end = " " if end is None else end
    assert isinstance(sep, str) and isinstance(end, str)
    output_str = sep.join(str(v) for v in values) + end
    if "\x1b" in output_str or "\x00" in output_str:  # \e or \0
        builtin_print(output_str, end="", file=file, flush=True)
    else:
        import sys

        from rich.console import Console

        global _stdout_console, _stderr_console
        if file is not None and file is not sys.stdout and file is not sys.stderr:
            builtin_print(output_str, file=file, flush=True)
            return
        if file is None or file is sys.stdout:
            if _stdout_console is None:
                _stdout_console = Console(soft_wrap=True, markup=False)
            _console = _stdout_console
        else:
            if _stderr_console is None:
                _stderr_console = Console(soft_wrap=True, markup=False, stderr=True)
            _console = _stderr_console
        _console.print(output_str, end="")


def _print_col_helper(obj_lines: list[list[str]], col_width: list[int], sep: str):
    total_rows = max(len(lines) for lines in obj_lines)
    outputs = []
    for i in range(total_rows):
        line_output = ""
        for j in range(len(col_width)):
            if j > 0:
                line_output += sep
            if j < len(obj_lines) and i < len(obj_lines[j]):
                line_output += f"{obj_lines[j][i]:<{col_width[j]}}"
            else:
                line_output += " " * col_width[j]
        outputs.append(line_output)
    return outputs


def print_col(*values: object, sep=" ", file=None):
    obj_lines = [str(obj).splitlines() for obj in values]

    col_width = [max(len(line) for line in lines) for lines in obj_lines]
    outputs = _print_col_helper(obj_lines, col_width, sep)

    print("\n".join(outputs) + "\n", end="", file=file)


def print_table(table: list[list[object]], col_sep=" ", row_sep="-", file=None):
    table_lines = [[str(obj).splitlines() for obj in values] for values in table]
    col_width = [
        max(
            len(line)
            for line in itertools.chain.from_iterable([(row[i] if i < len(row) else []) for row in table_lines])
        )
        for i in range(max(len(row) for row in table_lines))
    ]

    outputs = []
    total_width = sum(col_width) + len(col_sep) * (len(col_width) - 1)

    def _repeat(s: str, n: int):
        return (s * ((n + len(s) - 1) // len(s)))[:n]

    row_sep_long = _repeat(row_sep, total_width) if row_sep else ""

    for row in table_lines:
        if row_sep_long and outputs:
            outputs.append(row_sep_long)
        outputs += _print_col_helper(row, col_width, col_sep)
    print("\n".join(outputs) + "\n", end="", flush=True)


if __name__ == "__main__":
    import torch

    print_table(
        [
            [torch.ones(2, 2), torch.zeros(3, 3), torch.zeros(4, 1)],
            [torch.ones(1, 3), torch.ones(3, 1)],
        ],
        col_sep="|",
        row_sep="=",
    )
