import argparse
import base64
import dataclasses
import functools
import gzip
import itertools
import json
import os
import pathlib
import random
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid

from ladyrick.cli.tee import TIMESTAMP, tee
from ladyrick.print_utils import rich_print
from ladyrick.utils import EnumAction, get_timestr

MULTI_SSH_DEBUG = False


def log(msg):
    if MULTI_SSH_DEBUG:
        print(msg, flush=True)
    pass


REMOTE_HEAD_PROG_NAME = "ladyrick/multi-ssh/remote-head"


@dataclasses.dataclass
class Host:
    HostName: str
    config_file: str | None = None
    User: str | None = None
    Port: int | None = None
    IdentityFile: str | None = None
    options: list[str] | None = None


class RemoteExecutor:
    def __init__(self, host: Host, command: list[str], envs: dict | None = None, log_handler=None):
        self.process = None
        self.host = host
        self.command = command
        self.envs = {}
        self.log_handler = log_handler
        self.log_thread = None
        self.write_fd = None
        if envs:
            for k, v in envs.items():
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                    raise ValueError(f"invalid env name: {k!r}")
                self.envs[k] = v

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
        remote_proc_title = " ".join([REMOTE_HEAD_PROG_NAME] + self.command)
        argv_patched_code = "import sys;sys.argv[:]=[{!r},{!r},*{!r}];{}".format(
            REMOTE_HEAD_PROG_NAME,
            json.dumps(self.envs, separators=(",", ":"), ensure_ascii=True),
            self.command,
            (pathlib.Path(__file__).parent / "multi_ssh_remote_head.py").read_text(),
        )
        b85_code = base64.b85encode(gzip.compress(argv_patched_code.encode())).decode()
        code = f'c=b"{b85_code}";import base64,gzip,json,os,sys;os.dup2(0,9);read_fd,write_fd=os.pipe();os.write(write_fd,gzip.decompress(base64.b85decode(c)));os.close(write_fd);os.dup2(read_fd,0);os.close(read_fd);os.execvp(sys.executable,[{json.dumps(remote_proc_title)}])'
        remote_cmd = shlex.join(["python3", "-uc", code])

        if self.log_handler is not None:

            def wrapper(handler, read_fd):
                handler(read_fd)
                os.close(read_fd)

            read_fd, write_fd = os.pipe()
            self.write_fd = write_fd  # for later close it

            # 有时候子进程结束了，log 还没输出完，所以不能用 daemon=True，会丢 log
            self.log_thread = threading.Thread(target=wrapper, args=(self.log_handler, read_fd))
            self.log_thread.start()
        else:
            write_fd = sys.stdout
        self.process = subprocess.Popen(
            self.make_ssh_cmd(self.host, remote_cmd),
            stdin=subprocess.PIPE,
            stdout=write_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    @classmethod
    def set_envs(cls, executors: list["RemoteExecutor"], timestr: str):
        assert executors
        envs = {}
        if len(executors) > 1:
            cmd = cls.make_ssh_cmd(executors[0].host, "hostname -I 2>/dev/null")
            master_ips = subprocess.check_output(cmd).decode().split()
            priority = {"172": 0, "192": 1, "10": 2}
            master_addr, cur_p = None, -1
            for ip in master_ips:
                prefix = ip.split(".", 1)[0]
                p = priority.get(prefix, 3)
                if p > cur_p:
                    master_addr, cur_p = ip, p
            if master_addr is not None:
                envs["MASTER_ADDR"] = master_addr
            else:
                print("WARNING: cannot get MASTER_ADDR. use 127.0.0.1")
                envs["MASTER_ADDR"] = "127.0.0.1"
        else:
            envs["MASTER_ADDR"] = "127.0.0.1"
        envs["MASTER_PORT"] = str(random.randint(20000, 40000))
        envs["WORLD_SIZE"] = str(len(executors))

        envs["UNIQ_ID"] = str(uuid.uuid4())

        envs["TIMESTAMP"] = timestr
        if MULTI_SSH_DEBUG:
            envs["MULTI_SSH_DEBUG"] = "1"

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
        assert self.process is not None
        if self.process.poll() is None:
            log("terminate RemoteExecutor")
            self.process.terminate()

    def poll(self):
        assert self.process is not None
        poll = self.process.poll()
        if poll is not None and self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None
        return poll

    def join_log_thread(self):
        assert self.process is not None
        if self.log_thread is not None:
            assert self.poll() is not None
            self.log_thread.join()


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
    parser.add_argument("--log-dir", "-d", type=str, help="save outputs to a log dir")
    parser.add_argument("--rank-prefix", "-r", action="store_true", help="print a prefix to identity different rank")
    parser.add_argument("--help", action="help", default=argparse.SUPPRESS, help="show this help message and exit")
    parser.add_argument(
        "--timestamp",
        "-t",
        action=EnumAction,
        type=TIMESTAMP,
        help="control where to add timestamp",
        default=TIMESTAMP.NO,
    )
    parser.add_argument("--no-rich", "-n", action="store_false", help="disable rich output", dest="rich")
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

    timestr = get_timestr(1)
    if args.log_dir:
        pathlib.Path(args.log_dir, timestr).mkdir(parents=True, exist_ok=True)

    width = len(str(len(hosts)))

    def get_log_handler(i):
        log_file = args.log_dir and os.path.join(args.log_dir, timestr, f"rank-{i}.log")
        return functools.partial(
            tee,
            output_files=log_file,
            timestamp=args.timestamp,
            rich=args.rich,
            prefix=args.rank_prefix and f"rank-{i:<{width}}",
        )

    executors = [RemoteExecutor(host, args.cmd, envs, get_log_handler(i)) for i, host in enumerate(hosts)]

    RemoteExecutor.set_envs(executors, timestr)

    for executor in executors:
        executor.start()

    checker = signal_repeat_checker(signal.SIGINT, duration=1)

    def handle_signal(sig, frame):
        log(f"received signal {sig}")
        sig_count = checker(sig)
        if sig_count >= 3:
            sig = signal.SIGUSR2
            if sig_count == 3:
                rich_print(
                    "\n[bold magenta]Can't wait. Try to froce kill remote processes...[/bold magenta]",
                    markup=True,
                )
        else:
            rich_print(
                f"\n[bold green]Received {signal.Signals(sig).name}, forwarding to remote processes...[/bold green]",
                markup=True,
            )
        for executor in executors:
            executor.send_signal(sig)
        if sig_count >= 4:
            rich_print(
                "\n[bold red]Really Can't wait!!! Froce kill local processes and exiting right now![/bold red]",
                markup=True,
            )
            for executor in executors:
                executor.terminate()

    for sig in [signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2]:
        signal.signal(sig, handle_signal)

    while any([e.poll() is None for e in executors]):
        time.sleep(0.5)

    for e in executors:
        e.join_log_thread()

    log("finished")


if __name__ == "__main__":
    main()
