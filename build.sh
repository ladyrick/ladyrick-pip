#!/bin/bash -x

cd "$(dirname "$0")"

pip install -U build twine

rm -rf dist
python -m build

twine upload dist/*
