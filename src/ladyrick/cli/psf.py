import os
import subprocess
import sys


def main():
    if os.uname().sysname != "Linux":
        print("only support uname Linux")
        sys.exit(1)
    verbose = ""
    root_pid = 0
    for arg in sys.argv[1:]:
        if all(c == "w" for c in arg):
            verbose += arg
        elif arg.isdigit():
            root_pid = int(arg)
        else:
            print(f"invalid args: {arg}")
            sys.exit(1)
    if root_pid in (0, 1):
        cmd = ["ps", verbose + "afxopid,user,cmd"]
        os.execlp("ps", *cmd)
    else:
        cmd = ["ps", "axfo", "pid=,ppid="]
        out = subprocess.check_output(cmd).decode().strip().split("\n")
        out = [[int(p) for p in line.split()] for line in out]
        showed_pid = []
        for pid, ppid in out:
            if pid == root_pid or ppid in showed_pid:
                showed_pid.append(pid)
        if not showed_pid:
            print(f"root pid not found: root_pid={root_pid}")
            sys.exit(1)
        cmd = ["ps", verbose + "fopid,user,cmd", "--pid=" + ",".join(str(p) for p in showed_pid)]
        os.execlp("ps", *cmd)


if __name__ == "__main__":
    main()
