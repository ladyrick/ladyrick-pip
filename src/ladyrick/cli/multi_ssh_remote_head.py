import json
import os
import select
import signal
import subprocess
import sys


def log(msg):
    if os.getenv("MULTI_SSH_DEBUG"):
        print(msg, flush=True)
    pass


REMOTE_HEAD_PROG_NAME = "ladyrick/multi-ssh/remote-head"


def force_kill(child: subprocess.Popen, child_pgid):
    os.killpg(child_pgid, signal.SIGTERM)
    try:
        child.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    if child.poll() is None:
        child.kill()  # kill -9


def remote_head():
    os.environ["PYTHONUNBUFFERED"] = "1"
    extra_envs = json.loads(sys.argv[1])
    os.environ.update(extra_envs)

    cmd = sys.argv[2:]

    # start child process
    child = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=sys.stdout,
        stderr=sys.stderr,
        start_new_session=True,
    )

    child_pgid = os.getpgid(child.pid)

    def handle_signal(sig, frame=None):
        if sig == signal.SIGUSR2:
            # SIGUSR2 trigger force_kill manually
            log("SIGUSR2 received. force kill")
            force_kill(child, child_pgid)
        else:
            log(f"forward signal {signal.Signals(sig).name}:{sig} to {child.pid}")
            try:
                os.kill(child.pid, sig)
            except ProcessLookupError as e:
                log(str(e))

    for sig in [signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2]:
        signal.signal(sig, handle_signal)

    # main loop: watch child process and stdin
    control_fd = os.fdopen(9)
    while True:
        if child.poll() is not None:
            return child.returncode

        rlist, _, _ = select.select([control_fd], [], [], 0.1)
        if control_fd in rlist:
            cmd = control_fd.readline().strip()
            log(f"remote header receive command: {cmd}")
            if cmd.startswith("SIGNAL "):
                sig_name = cmd[7:]
                try:
                    sig = getattr(signal, sig_name)
                except AttributeError:
                    log(f"unknown signal {sig_name}")
                else:
                    handle_signal(sig)
            else:
                log(f"unknown cmd {cmd!r}")


if __name__ == "__main__":
    remote_head()
