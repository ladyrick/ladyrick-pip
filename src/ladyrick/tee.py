#!/usr/bin/env python3
import enum
import gzip
import sys

from ladyrick.print_utils import rich_print
from ladyrick.utils import get_timestr


def _patch_rich_for_tee_carriage_return():
    # 防止 rich 吞掉 '\r' 字符。
    import rich.control

    rich.control.STRIP_CONTROL_CODES.remove(13)
    rich.control._CONTROL_STRIP_TRANSLATE.pop(13)


def readlines(input_file=sys.stdin.buffer):
    buffer_size = 8192

    def reader() -> bytes:
        return input_file.read1(buffer_size) if hasattr(input_file, "read1") else input_file.read(buffer_size)

    def get_idx(data: bytes, start=0):
        ridx = data.find(b"\r", start)
        nidx = data.find(b"\n", start)
        if ridx == -1:
            return nidx
        if nidx == -1:
            return ridx
        return min(ridx, nidx)

    try:
        buffer = b""
        while data := reader():
            if buffer:
                data = buffer + data
            s = 0
            while (idx := get_idx(data, s)) != -1:
                yield data[s : idx + 1]
                s = idx + 1
            buffer = data[s:]
        if buffer:
            yield buffer
    except KeyboardInterrupt:
        yield buffer


class TIMESTAMP(enum.Enum):
    NO = "no"
    FILE = "file"
    TERMINAL = "terminal"
    ALL = "all"


def tee(
    input_file=sys.stdin.buffer,
    output_files: list[str] = [],
    append=False,
    timestamp: TIMESTAMP = TIMESTAMP.NO,
):
    opened_files = []
    for f in output_files:
        mode = "ab" if append else "wb"
        is_gzip = f.endswith(".gz")
        if is_gzip:
            opened_files.append((is_gzip, gzip.open(f, mode)))
        else:
            opened_files.append((is_gzip, open(f, mode)))
    try:
        gzip_data_len = 0
        gzip_flush_block_size = 1024 * 1024  # 1MB
        for line in readlines(input_file):
            timestr = ""
            if timestamp in {TIMESTAMP.FILE, TIMESTAMP.TERMINAL, TIMESTAMP.ALL}:
                timestr = f"[{get_timestr()}] "
            if timestamp in {TIMESTAMP.TERMINAL, TIMESTAMP.ALL}:
                rich_print(timestr + line.decode(), end="", flush=True)
            else:
                rich_print(line.decode(), end="", flush=True)
            if timestamp in {TIMESTAMP.FILE, TIMESTAMP.ALL}:
                line = timestr.encode() + line
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
    import argparse

    parser = argparse.ArgumentParser("ladyrick-tee")
    parser.add_argument("--append", "-a", action="store_true")
    parser.add_argument("output_files", nargs="*", help="output files. add '.gz' suffix to enable gzip")
    parser.add_argument(
        "--timestamp",
        "-t",
        choices=["no", "n", "file", "f", "terminal", "t", "all", "a"],
        help="control where to add timestamp",
        default="no",
    )

    args = parser.parse_args()
    timestamp = {"n": "no", "f": "file", "t": "terminal", "a": "all"}.get(args.timestamp, args.timestamp)

    _patch_rich_for_tee_carriage_return()
    tee(
        output_files=args.output_files,
        append=args.append,
        timestamp=TIMESTAMP(timestamp),
    )


if __name__ == "__main__":
    main()
