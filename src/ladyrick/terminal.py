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

import rich


class forward_terminal:
    def __init__(self, port=8765, secret: str | None = None):
        self.port = port
        self.secret = secrets.token_hex(16) if secret is None else secret

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.listen(1)

        from ladyrick.utils import get_local_ip

        rich.print(
            f"Connect to this terminal by "
            f"[magenta bold italic]python -m ladyrick.terminal --host {get_local_ip()} --port {self.port} --secret {self.secret}[/magenta bold italic]",
            flush=True,
        )

        secret_compare = f"<secret>{self.secret}</secret>\n".encode()
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

        self.exit_thread = False

        def forward_data():
            while not self.exit_thread:
                rlist, _, _ = select.select([self.master_fd, self.conn], [], [], 0.1)
                for fd in rlist:
                    if fd == self.master_fd:
                        data = os.read(fd, 1024)
                        self.conn.send(data)
                    else:
                        data = self.conn.recv(1024)
                        if not data:
                            break
                        os.write(self.master_fd, data)

        self.forward_thread = threading.Thread(target=forward_data, daemon=True)
        self.forward_thread.start()

        self.original_stdin = os.dup(0)
        self.original_stdout = os.dup(1)
        self.original_stderr = os.dup(2)

        os.dup2(self.slave_fd, 0)
        os.dup2(self.slave_fd, 1)
        os.dup2(self.slave_fd, 2)

        atexit.register(self.stop)

    def stop(self):
        if self.exit_thread:
            return
        self.exit_thread = True
        self.forward_thread.join()

        self.conn.close()
        self.sock.close()

        os.dup2(self.original_stdin, 0)
        os.dup2(self.original_stdout, 1)
        os.dup2(self.original_stderr, 2)

        os.close(self.slave_fd)
        os.close(self.master_fd)
        os.close(self.original_stdin)
        os.close(self.original_stdout)
        os.close(self.original_stderr)
        atexit.unregister(self.stop)

    __enter__ = start

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    @staticmethod
    def connect(host="127.0.0.1", port=8765, secret: str = ""):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.send(f"<secret>{secret}</secret>\n".encode())
        result = sock.recv(11)
        if result == b"<wrong/>\n":
            print("secret is wrong. exit")
            return

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(0)
            while True:
                rlist, _, _ = select.select([0, sock], [], [])
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
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def client_main():
    import setproctitle

    setproctitle.setproctitle("python -m ladyrick.terminal")

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
