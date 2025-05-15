import os

import ladyrick.patch.rich_print  # noqa

if (startup_file := os.getenv("LADYRICK_PYTHON_STARTUP")) and os.path.isfile(startup_file):
    with open(startup_file) as f:
        code = f.read()
    exec(code)
