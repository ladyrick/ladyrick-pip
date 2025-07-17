import argparse
import atexit
import fcntl
import hashlib
import importlib.metadata
import os
import pty
import secrets
import select
import signal
import socket
import struct
import sys
import termios
import threading
import time
import tty

from ladyrick.print_utils import rich_print


def no_exc(f, *args, **kwargs):
    try:
        f(*args, **kwargs)
    except Exception:
        pass


def get_terminal_size() -> tuple[int, int]:
    try:
        TIOCGWINSZ = getattr(termios, "TIOCGWINSZ", 0x5413)
        winsize = struct.pack("HHHH", 0, 0, 0, 0)
        winsize = fcntl.ioctl(sys.stdout.fileno(), TIOCGWINSZ, winsize)
        return struct.unpack("HHHH", winsize)[:2]
    except (IOError, OSError):
        return 24, 80


def set_terminal_size(fd: int, row: int, col: int, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


class forward_terminal:
    salt = b'#`L|A:\xc1\n\xe2gV\xbcD\xe7\x8c\x82\xd18}\xe9\xdc\x13\x1e\x8c"\x0ej1\x1cb\xe4)'
    salt += importlib.metadata.version("ladyrick").encode()

    def __init__(self, port=8765, secret: str | None = None):
        self.port = port
        self.secret = secrets.token_hex(16) if secret is None else secret
        self.secret_hash = hashlib.md5(self.secret.encode() + self.salt).digest()
        self.stopped = False

    def start(self):
        assert not self.stopped
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.listen(1)

        from ladyrick.utils import get_local_ip

        connect_cmd = f"python -m ladyrick.terminal --host {get_local_ip()} --port {self.port}"
        if self.secret:
            connect_cmd += f" --secret {self.secret}"
        rich_print(f"Connect to this terminal by [magenta bold italic]{connect_cmd}[/magenta bold italic]", markup=True)

        secret_compare = b"<secret>" + self.secret_hash + b"</secret>\n"
        heart_beat_bytes = b"<heart_beat>" + self.secret_hash + b"</heart_beat>\n"
        winsize_begin, winsize_end = b"<winsize " + self.secret_hash + b">", b"</winsize>\n"

        while True:
            self.conn, _ = self.sock.accept()
            recv_secret = self.conn.recv(len(secret_compare))
            time.sleep(0.5)
            if secret_compare == recv_secret:
                self.conn.send(b"<correct/>\n")
                break
            else:
                self.conn.send(b"<wrong/>\n")
                self.conn.close()

        # get initial window size
        data = self.conn.recv(4)
        rows, cols = struct.unpack("!HH", data)

        self.master_fd, self.slave_fd = pty.openpty()

        def forward_data():
            last_alive_check = time.time()

            def handle_control(data: bytes):
                nonlocal last_alive_check
                prev_data_len = len(data)
                data = data.replace(heart_beat_bytes, b"")
                if len(data) < prev_data_len:
                    last_alive_check = time.time()

                # handle winsize change event
                begin_pos = 0
                while (left := data.find(winsize_begin, begin_pos)) != -1:
                    middle = left + len(winsize_begin)
                    end_mark = middle + 4
                    right = end_mark + len(winsize_end)
                    assert data[end_mark:right] == winsize_end, "invalid control command"
                    set_terminal_size(self.master_fd, *struct.unpack("!HH", data[middle:end_mark]))
                    os.kill(os.getpid(), signal.SIGWINCH)  # 通知 pty 的前台进程，也就是自己
                    begin_pos = right
                    data = data[:left] + data[right:]
                return data

            try:
                buffer = b""
                while not self.stopped and time.time() < (last_alive_check + 3):
                    rlist, _, _ = select.select([self.master_fd, self.conn], [], [], 0.1)
                    for fd in rlist:
                        if fd == self.master_fd:
                            data = os.read(fd, 1024)
                            self.conn.send(data)
                        else:
                            data = self.conn.recv(1024)
                            if not data:
                                if buffer:
                                    os.write(self.master_fd, buffer)
                                break
                            maybe_not_finish = len(data) == 1024
                            if buffer:
                                data = buffer + data
                            data = handle_control(data)
                            if maybe_not_finish:
                                buffer = data[-100:]
                                data = data[:-100]
                            if data:
                                os.write(self.master_fd, data)
            except OSError:
                pass
            finally:
                self.stop(join=False)

        self.forward_thread = threading.Thread(target=forward_data, daemon=True)

        self.original_stdin = os.dup(0)
        self.original_stdout = os.dup(1)
        self.original_stderr = os.dup(2)

        os.dup2(self.slave_fd, 0)
        os.dup2(self.slave_fd, 1)
        os.dup2(self.slave_fd, 2)

        set_terminal_size(self.master_fd, rows, cols)
        self.forward_thread.start()
        atexit.register(self.stop)

    def stop(self, join=True):
        if self.stopped:
            return
        self.stopped = True
        if join:
            self.forward_thread.join()

        no_exc(os.dup2, self.original_stdin, 0)
        no_exc(os.dup2, self.original_stdout, 1)
        no_exc(os.dup2, self.original_stderr, 2)

        no_exc(self.conn.close)
        no_exc(self.sock.close)

        no_exc(os.close, self.slave_fd)
        no_exc(os.close, self.master_fd)
        no_exc(os.close, self.original_stdin)
        no_exc(os.close, self.original_stdout)
        no_exc(os.close, self.original_stderr)
        no_exc(atexit.unregister, self.stop)

    __enter__ = start

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    @classmethod
    def connect(cls, host="127.0.0.1", port=8765, secret=""):
        secret_hash = hashlib.md5(secret.encode() + cls.salt).digest()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.send(b"<secret>" + secret_hash + b"</secret>\n")

        heart_beat_bytes = b"<heart_beat>" + secret_hash + b"</heart_beat>\n"
        winsize_begin, winsize_end = b"<winsize " + secret_hash + b">", b"</winsize>\n"

        result = sock.recv(11)
        if result == b"<wrong/>\n":
            print("secret is wrong or version mismatch.")
            return

        sock.send(struct.pack("!HH", *get_terminal_size()))

        def sigwinch_handler(signum, frame):
            try:
                sock.send(winsize_begin + struct.pack("!HH", *get_terminal_size()) + winsize_end)
            except OSError:
                pass

        signal.signal(signal.SIGWINCH, sigwinch_handler)

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(0)
            while True:
                rlist, _, _ = select.select([0, sock], [], [], 1)
                for fd in rlist:
                    if fd == 0:
                        data = os.read(0, 1024)
                        sock.send(data)
                    else:
                        data = sock.recv(1024)
                        if not data:
                            return
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                sock.send(heart_beat_bytes)
        except OSError:
            pass
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def client_main():
    import setproctitle

    setproctitle.setproctitle("python -m ladyrick.terminal client")

    parser = argparse.ArgumentParser(prog="terminal", add_help=False)
    parser.add_argument("--host", "-h", type=str, help="host", default="127.0.0.1")
    parser.add_argument("--port", "-p", type=int, help="port", default=8765)
    parser.add_argument("--secret", "-s", type=str, help="secret (will not show in `ps`)", default="")
    parser.add_argument("--help", action="help", default=argparse.SUPPRESS, help="show this help message and exit")

    args = parser.parse_args()

    forward_terminal.connect(args.host, args.port, args.secret)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        with forward_terminal():
            import ladyrick

            ladyrick.embed()
    else:
        client_main()
