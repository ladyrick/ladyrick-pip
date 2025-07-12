import argparse
import atexit
import os
import pty
import secrets
import select
import socket
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


class forward_terminal:
    def __init__(self, port=8765, secret: str | None = None):
        self.port = port
        self.secret = secrets.token_hex(16) if secret is None else secret
        self.stopped = False

    default_heartbeat = b'#`L|A:\xc1\n\xe2gV\xbcD\xe7\x8c\x82\xd18}\xe9\xdc\x13\x1e\x8c"\x0ej1\x1cb\xe4)'

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

        secret_compare = f"<secret>{self.secret}</secret>\n".encode()
        heart_beat_bytes = b"<heart_beat>" + (self.secret.encode() or self.default_heartbeat) + b"</heart_beat>\n"

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

        self.master_fd, self.slave_fd = pty.openpty()

        def forward_data():
            last_alive_check = time.time()
            try:
                while not self.stopped and time.time() < (last_alive_check + 3):
                    rlist, _, _ = select.select([self.master_fd, self.conn], [], [], 0.1)
                    for fd in rlist:
                        if fd == self.master_fd:
                            data = os.read(fd, 1024)
                            self.conn.send(data)
                        else:
                            data = self.conn.recv(1024)
                            if not data:
                                break
                            orig_data_len = len(data)
                            data_no_hb = data.replace(heart_beat_bytes, b"")
                            if len(data_no_hb) < orig_data_len:
                                last_alive_check = time.time()
                            if data_no_hb:
                                os.write(self.master_fd, data_no_hb)
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
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.send(f"<secret>{secret}</secret>\n".encode())

        heart_beat_bytes = b"<heart_beat>" + (secret.encode() or cls.default_heartbeat) + b"</heart_beat>\n"
        result = sock.recv(11)
        if result == b"<wrong/>\n":
            print("secret is wrong. exit")
            return

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
