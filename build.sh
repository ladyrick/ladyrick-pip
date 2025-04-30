#!/bin/bash -x

cd "$(dirname "$0")"

pip install -U build twine --break-system-packages

rm -rf dist
python -m build

twine upload dist/*
