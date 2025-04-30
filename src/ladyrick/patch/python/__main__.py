import os
import sys

cur_dir = os.path.dirname(os.path.realpath(__file__))
pop_ids = [i for i, p in enumerate(sys.path) if os.path.realpath(p) == cur_dir]
for idx in reversed(pop_ids):
    sys.path.pop(idx)

try:
    import usercustomize  # type: ignore
except ImportError:
    pass
else:
    n = "\n"
    sys.stderr.write(
        f"""usercustomize already exists in {usercustomize.__file__}
current sys.path is
{n.join("  " + repr(p) for p in sys.path)}
"""
    )
    sys.exit(1)

environ = os.environ.copy()
environ["PYTHONPATH"] = environ.get("PYTHONPATH", "") + f":{cur_dir}"


os.execlpe(sys.executable, sys.executable, *sys.argv[1:], environ)
