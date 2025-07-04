#!/usr/bin/env python3
import argparse
import enum
import gzip
import os
import sys
from functools import partial
from typing import BinaryIO, TypeAlias

from ladyrick.print_utils import rich_print
from ladyrick.utils import EnumAction, get_timestr


def _patch_rich_for_tee_carriage_return():
    # 防止 rich 吞掉 '\r' 字符。
    import rich.control

    rich.control.STRIP_CONTROL_CODES.remove(13)
    rich.control._CONTROL_STRIP_TRANSLATE.pop(13)


FileDescriptor: TypeAlias = int


def readlines(input_file: BinaryIO | FileDescriptor = sys.stdin.buffer):
    buffer_size = 8192

    if isinstance(input_file, FileDescriptor):
        # 跟 read1 表现有点类似，性能也差不多
        reader = partial(os.read, input_file, buffer_size)
    elif hasattr(input_file, "read1"):
        # stdin 走的这个分支。
        # 会自动按 \r 和 \n 切分，除非时间间隔非常短。
        reader = partial(getattr(input_file, "read1"), buffer_size)
    else:
        # readline 相比 read，会自动按 \n 切分，除非时间间隔非常短。
        # 但无法按 \r 切分。
        # 但总比 read 啥都不切好。
        reader = partial(input_file.readline, buffer_size)

    def get_next_start(data: bytes, start=0):
        ridx = data.find(b"\r", start)
        nidx = data.find(b"\n", start)
        if -1 < ridx < nidx and ridx + 1 == nidx:
            return ridx + 2  # \r\n
        if ridx == -1:
            if nidx == -1:
                return -1
            return nidx + 1
        if nidx == -1:
            return ridx + 1
        return min(ridx, nidx) + 1

    buffer = b""
    try:
        while data := reader():
            if buffer:
                data = buffer + data
            s = 0
            while (next_s := get_next_start(data, s)) != -1:
                yield data[s:next_s]
                s = next_s
            buffer = data[s:]
    except KeyboardInterrupt:
        pass
    finally:
        if buffer:
            yield buffer


class TIMESTAMP(enum.Enum):
    NO = "no"
    FILE = "file"
    TERMINAL = "terminal"
    ALL = "all"


def tee(
    input_file: BinaryIO | FileDescriptor = sys.stdin.buffer,
    output_files: None | str | list[str] = None,
    append=False,
    timestamp: TIMESTAMP = TIMESTAMP.NO,
    rich=True,
    prefix: None | str = None,
):
    def _print(line: bytes):
        if rich:
            rich_print(line.decode(), end="")
        else:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    opened_files = []
    if isinstance(output_files, str):
        output_files = [output_files]
    output_files = output_files or []

    for f in output_files:
        mode = "ab" if append else "wb"
        is_gzip = f.endswith(".gz")
        if is_gzip:
            opened_files.append((is_gzip, gzip.open(f, mode)))
        else:
            opened_files.append((is_gzip, open(f, mode)))

    prefix_bytes = f"[{prefix}] ".encode() if prefix else b""

    try:
        gzip_data_len = 0
        gzip_flush_block_size = 1024 * 1024  # 1MB
        for line in readlines(input_file):
            timebytes = b""
            if timestamp in {TIMESTAMP.FILE, TIMESTAMP.TERMINAL, TIMESTAMP.ALL}:
                timebytes = f"[{get_timestr()}] ".encode()
            if timestamp in {TIMESTAMP.TERMINAL, TIMESTAMP.ALL}:
                if prefix_bytes:
                    _print(timebytes + prefix_bytes + line)
                else:
                    _print(timebytes + line)
            else:
                if prefix_bytes:
                    _print(prefix_bytes + line)
                else:
                    _print(line)
            if timestamp in {TIMESTAMP.FILE, TIMESTAMP.ALL}:
                line = timebytes + line
            gzip_data_len += len(line)
            # 写入所有输出文件
            for is_gzip, f in opened_files:
                f.write(line)
                if not is_gzip:
                    f.flush()
                elif gzip_data_len >= gzip_flush_block_size:
                    f.flush()
                    gzip_data_len = 0
    finally:
        # 确保所有文件都被关闭
        for _, f in opened_files:
            f.close()


def main():
    parser = argparse.ArgumentParser("ladyrick-tee")
    parser.add_argument("--append", "-a", action="store_true")
    parser.add_argument("output_files", nargs="*", help="output files. add '.gz' suffix to enable gzip")
    parser.add_argument(
        "--timestamp",
        "-t",
        action=EnumAction,
        type=TIMESTAMP,
        help="control where to add timestamp",
        default=TIMESTAMP.NO,
    )
    parser.add_argument(
        "--prefix",
        "-p",
        type=str,
        help="print prefix for each line",
    )
    parser.add_argument("--no-rich", action="store_false", help="disable rich output", dest="rich")

    args = parser.parse_args()

    _patch_rich_for_tee_carriage_return()
    tee(
        output_files=args.output_files,
        append=args.append,
        timestamp=args.timestamp,
        rich=args.rich,
        prefix=args.prefix,
    )


if __name__ == "__main__":
    main()
