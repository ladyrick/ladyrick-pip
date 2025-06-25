import os
import sys


def initialize(interactive_mode: bool):
    imports = {}
    exec("import ladyrick.patch.rich_print")
    exec("import math; from math import *", locals=imports)
    exec("import itertools; from itertools import *", locals=imports)
    exec("import functools; from functools import cache, lru_cache, partial, reduce", locals=imports)
    exec("import os, sys, time, re, random", locals=imports)
    exec("from pathlib import Path", locals=imports)
    exec("from time import sleep", locals=imports)
    exec("from subprocess import check_output", locals=imports)
    exec("from random import randint, choice, random as rand", locals=imports)
    exec("import ladyrick", locals=imports)
    if interactive_mode:
        imports["ladyrick"].pprint.reg_ipython_cmd()
    globals().update(imports)


def main():
    if len(sys.argv) == 1 and not os.getenv("__ladyrick_calc__"):
        import setproctitle

        os.environ["__ladyrick_calc__"] = setproctitle.getproctitle()
        os.execl(sys.executable, sys.executable, "-m", "IPython", "-i", "--no-banner", "--no-confirm-exit", __file__)
    else:
        if len(sys.argv) == 1:
            import setproctitle

            setproctitle.setproctitle(os.environ["__ladyrick_calc__"])
            del setproctitle

        initialize(len(sys.argv) == 1)

        if len(sys.argv) > 1:
            print(eval(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    main()
