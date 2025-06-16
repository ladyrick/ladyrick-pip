import json
from os import PathLike
from pathlib import Path
from typing import Literal, Final

import ladyrick.pickle as pickle_anything


FORMATS: Final = (
    "auto",
    "pt",
    "torch",
    "st",
    "safetensors",
    "pkl",
    "pickle",
    "json",
    "jsonl",
    "yml",
    "yaml",
)


def auto_load(
    filepath: str | PathLike[str],
    format: Literal[
        "auto", "pt", "torch", "st", "safetensors", "pkl", "pickle", "json", "jsonl", "yml", "yaml"
    ] = "auto",
    ignore_errors=False,
    raw=True,
):
    suffix = Path(filepath).suffix

    def _check(suffix_in: tuple[str, ...], fmt_in: tuple[str, ...]):
        return format == "auto" and suffix in suffix_in or format in fmt_in

    if _check((".pt",), ("pt", "torch")):
        return load_torch(filepath, ignore_errors, raw)
    if _check((".safetensors",), ("st", "safetensors")):
        return load_safetensors(filepath)
    if _check((".pkl", ".pickle"), ("pkl", "pickle")):
        return load_pickle(filepath, ignore_errors)
    if _check((".json",), ("json",)):
        with open(filepath) as f:
            return json.load(f)
    if _check((".jsonl",), ("jsonl",)):
        with open(filepath) as f:
            return [json.loads(line) for line in f]
    if _check((".yml", ".yaml"), ("yml", "yaml")):
        try:
            import yaml
        except ImportError:
            raise RuntimeError("please 'pip install pyyaml' to load yaml file")
        with open(filepath) as f:
            docs = list(yaml.safe_load_all(f))
            return docs[0] if len(docs) == 1 else docs
    raise RuntimeError(f"load failed! cannot decide filetype of {filepath}")


def load_torch(filepath, ignore_errors=False, raw=True):
    import torch

    return torch.load(
        filepath,
        map_location=None if raw else "cpu",
        weights_only=False,
        pickle_module=pickle_anything if ignore_errors else None,
    )


def load_safetensors(filepath):
    from safetensors.torch import load_file

    return load_file(filepath)


def load_pickle(filepath, ignore_errors=False):
    if ignore_errors:
        from ladyrick.pickle import Unpickler
    else:
        from pickle import Unpickler
    with open(filepath, "rb") as f:
        return Unpickler(f).load()
