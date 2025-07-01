import json
import os
import re
import select
import signal
import subprocess
import sys


def log(msg):
    # print(msg, flush=True)
    pass


def force_kill(child: subprocess.Popen, child_pgid):
    os.killpg(child_pgid, signal.SIGTERM)
    try:
        child.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    if child.poll() is None:
        child.kill()  # kill -9


REMOTE_HEAD_PROG_NAME = "ladyrick/multi-ssh/remote-head"


def remote_head():
    os.environ["PYTHONUNBUFFERED"] = "1"
    extra_envs = json.loads(sys.argv[2])
    os.environ.update(extra_envs)

    cmd = sys.argv[3:]
    try:
        from setproctitle import setproctitle

        setproctitle(" ".join([REMOTE_HEAD_PROG_NAME] + cmd))
    except ImportError:
        pass

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
            log(f"forward signal {sig} to {child.pid}")
            try:
                os.kill(child.pid, sig)
            except ProcessLookupError as e:
                log(str(e))

    for sig in [signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2]:
        signal.signal(sig, handle_signal)

    # main loop: watch child process and stdin
    while True:
        if child.poll() is not None:
            return child.returncode

        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
        if sys.stdin in rlist:
            cmd = sys.stdin.readline().strip()
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


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == REMOTE_HEAD_PROG_NAME:
    sys.exit(remote_head())


# ----- remote_head end ----- #
if True:
    import argparse
    import dataclasses
    import itertools
    import pathlib
    import random
    import shlex
    import time
    import uuid


@dataclasses.dataclass
class Host:
    HostName: str
    config_file: str | None = None
    User: str | None = None
    Port: int | None = None
    IdentityFile: str | None = None
    options: list[str] | None = None


class RemoteExecutor:
    def __init__(self, host: Host, command: list[str], envs: dict | None = None):
        self.host = host
        self.command = command
        self.envs = {}
        if envs:
            for k, v in envs.items():
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                    raise ValueError(f"invalid env name: {k!r}")
                self.envs[k] = v
        self.process = None

    @classmethod
    def make_ssh_cmd(cls, host: Host, cmd: str):
        opts = ["/usr/bin/env", "ssh", "-T", "-oStrictHostKeyChecking=no"]
        if host.config_file is not None:
            opts.append(f"-F{host.config_file}")
        if host.User is not None:
            opts.append(f"-l{host.User}")
        if host.Port is not None:
            opts.append(f"-p{host.Port}")
        if host.IdentityFile is not None:
            opts.append(f"-i{host.IdentityFile}")
        for o in host.options or []:
            opts.append(f"-o{o}")
        opts.append(host.HostName)
        opts.append(cmd)
        return opts

    def start(self):
        assert self.process is None
        code = pathlib.Path(__file__).read_text().split("# ----- remote_head end ----- #")[0].strip()
        remote_cmd = shlex.join(
            [
                "python3",
                "-uc",
                code,
                REMOTE_HEAD_PROG_NAME,
                json.dumps(self.envs, separators=(",", ":")),
                *self.command,
            ]
        )

        self.process = subprocess.Popen(
            self.make_ssh_cmd(self.host, remote_cmd),
            stdin=subprocess.PIPE,
            stdout=sys.stdout,
            stderr=sys.stderr,
            start_new_session=True,
        )

    @classmethod
    def set_envs(cls, executors: list["RemoteExecutor"]):
        assert executors
        envs = {}
        if len(executors) > 1:
            cmd = cls.make_ssh_cmd(executors[0].host, "hostname -I")
            master_ips = subprocess.check_output(cmd).decode().split()
            priority = {"172": 0, "192": 1, "10": 2}
            master_addr, cur_p = None, -1
            for ip in master_ips:
                prefix = ip.split(".", 1)[0]
                p = priority.get(prefix, 3)
                if p > cur_p:
                    master_addr, cur_p = ip, p
            assert master_addr is not None
            envs["MASTER_ADDR"] = master_addr
        else:
            envs["MASTER_ADDR"] = "127.0.0.1"
        envs["MASTER_PORT"] = str(random.randint(20000, 40000))
        envs["WORLD_SIZE"] = str(len(executors))

        envs["UNIQ_ID"] = str(uuid.uuid4())
        from ladyrick.utils import get_timestr

        envs["TIMESTAMP"] = get_timestr(1)

        for i, e in enumerate(executors):
            e.envs.update(envs)
            e.envs["RANK"] = str(i)

    def send_signal(self, sig):
        assert self.process is not None
        if self.process.poll() is None and self.process.stdin and not self.process.stdin.closed:
            sig_name = signal.Signals(sig).name
            log(f"writing to stdin: SIGNAL {sig_name}")
            try:
                self.process.stdin.write(f"SIGNAL {sig_name}\n".encode())
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                log(e)

    def terminate(self):
        if self.process is not None and self.process.poll() is None:
            log("terminate RemoteExecutor")
            self.process.terminate()

    def poll(self):
        assert self.process is not None
        return self.process.poll()


def signal_repeat_checker(sig_to_check, duration: float):
    last_int_signal_time = []

    def checker(sig: signal.Signals):
        nonlocal last_int_signal_time
        if sig == sig_to_check:
            cur_time = time.time()
            threadhold = cur_time - duration
            last_int_signal_time = [t for t in last_int_signal_time if t >= threadhold]
            last_int_signal_time.append(cur_time)
            return len(last_int_signal_time)
        return 0

    return checker


def main():
    parser = argparse.ArgumentParser(prog="multi-ssh", add_help=False)
    parser.add_argument("-h", type=str, action="append", help="hosts to connect. order is 1")
    parser.add_argument("-i", type=str, help="ssh IdentityFile")
    parser.add_argument("-p", type=int, help="ssh Port")
    parser.add_argument("-l", type=str, help="ssh login User")
    parser.add_argument("-o", type=str, action="append", help="ssh options")
    parser.add_argument("-F", type=str, help="ssh config file")
    parser.add_argument("-e", "--env", type=str, action="append", help="extra envs")
    parser.add_argument("--hosts-config", type=str, action="append", help="hosts config string. order is 2")
    parser.add_argument("--hosts-config-file", type=str, action="append", help="hosts config file. order is 3")
    parser.add_argument("--help", action="help", default=argparse.SUPPRESS, help="show this help message and exit")
    parser.add_argument("cmd", type=str, nargs=argparse.REMAINDER, help="cmd")

    args = parser.parse_args()

    if not args.cmd:
        print("cmd is required\n")
        parser.print_help()
        sys.exit(1)

    hosts = [
        Host(hn, args.F, args.l, args.p, args.i, args.o)
        for hn in itertools.chain.from_iterable(h.split(",") for h in args.h or [])
    ]

    config_based_hosts = []
    for hosts_config in args.hosts_config or []:
        config_based_hosts += json.loads(hosts_config)
    for hosts_config_file in args.hosts_config_file or []:
        with open(hosts_config_file) as f:
            config_based_hosts += json.load(f)
    for hn in config_based_hosts:
        hosts.append(
            Host(
                hn["HostName"],
                config_file=hn.get("config_file"),
                User=hn.get("User"),
                Port=hn.get("Port"),
                IdentityFile=hn.get("IdentityFile"),
                options=hn.get("options"),
            )
        )

    if not hosts:
        print("hosts is required. specify hosts by -h, --hosts-config or --hosts-config-file\n")
        parser.print_help()
        sys.exit(1)

    envs = {}
    if args.env:
        for e in args.env:
            p = e.split("=", 1)
            if len(p) == 1:
                p.append("")
            envs[p[0]] = p[1]

    executors = [RemoteExecutor(host, args.cmd, envs) for host in hosts]

    RemoteExecutor.set_envs(executors)

    for executor in executors:
        executor.start()

    import rich

    checker = signal_repeat_checker(signal.SIGINT, duration=1)

    def handle_signal(sig, frame):
        log(f"received signal {sig}")
        sig_count = checker(sig)
        if sig_count >= 3:
            sig = signal.SIGUSR2
            if sig_count == 3:
                rich.print("\n[bold magenta]Can't wait. Try to froce kill remote processes...[/bold magenta]")
        else:
            rich.print(
                f"\n[bold green]Received {signal.Signals(sig).name}, forwarding to remote processes...[/bold green]"
            )
        for executor in executors:
            executor.send_signal(sig)
        if sig_count >= 4:
            rich.print("\n[bold red]Really Can't wait!!! Froce kill local processes and exiting right now![/bold red]")
            for executor in executors:
                executor.terminate()

    for sig in [signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2]:
        signal.signal(sig, handle_signal)

    while any([e.poll() is None for e in executors if e.process]):
        time.sleep(0.5)
    log("finished")


if __name__ == "__main__":
    main()
