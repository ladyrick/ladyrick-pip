import functools
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, Optional, TypeVar, cast, overload

T = TypeVar("T")
Func = TypeVar("Func", bound=Callable)

logger = logging.getLogger(__name__)


class Dump:
    _TS_LEN = len(str(int(time.time())))

    def __init__(self, dump_dir: str | Path):
        self.set_dump_dir(dump_dir)

    def set_dump_dir(self, dump_dir: str | Path):
        self.dump_dir = Path(dump_dir)

    def __call__(self, obj: object, name: str, log=True, enabled=True):
        if not enabled:
            return
        # assert "/" not in name  # 通过允许传入绝对路径，来支持临时忽略 dump 目录
        from ladyrick.torch import rank as get_rank

        rank = get_rank(True)
        if rank is None:
            rank = "null"
        ts = str(time.time_ns())
        ts = f"{ts[:self._TS_LEN]}.{ts[self._TS_LEN:]}"
        filename = self.dump_dir / f"{name}-rank-{rank}-{ts}.pt"
        filename.parent.mkdir(parents=True, exist_ok=True)
        import torch

        if log:
            logger.info(f"saving to {filename}")
        with open(filename, "wb") as f:
            torch.save(obj, f)
        if log:
            logger.info(f"saved to {filename}")

    def func(self, name: str, log=True, enabled=True) -> Callable[[Func], Func]:
        if not enabled:
            return lambda func: func

        def dump_wrapper(func: Func):
            @functools.wraps(func)
            def func_wrapper(*args, **kwargs):
                for i, a in enumerate(args):
                    self(a, f"{name}-input.{i}", log)
                for k, v in kwargs.items():
                    self(v, f"{name}-input.{k}", log)
                r_value = func(*args, **kwargs)
                if r_value.__class__ is tuple:
                    for i, r in enumerate(r_value):
                        self(r, f"{name}-output.{i}", log)
                else:
                    self(r_value, f"{name}-output.0", log)
                return r_value

            return cast(Func, func_wrapper)

        return dump_wrapper


dump = Dump(".")


class Vars:
    def __init__(self, data: Optional[dict[str, Any]] = None):
        data = dict() if data is None else dict(data)
        super().__setattr__("_data", data)
        self._data: dict[str, Any]

    def __setitem__(self, k: str | tuple[str, Any], v: Any):
        if isinstance(k, tuple):
            assert len(k) == 2
            k = k[0]
        assert not k.startswith("_") and k not in {"get", "ctx"}
        self._data[k] = v

    @overload
    def __getitem__(self, k: str) -> Any:
        pass

    @overload
    def __getitem__(self, k: tuple[str, T]) -> T:
        pass

    def __getitem__(self, k: str | tuple[str, Any]):
        if isinstance(k, tuple):
            assert len(k) == 2
            self._data.setdefault(k[0], k[1])
            k = k[0]
        return self._data[k]

    def __delitem__(self, k: str | tuple[str, Any]):
        if isinstance(k, tuple):
            assert len(k) == 2
            k = k[0]
        del self._data[k]

    def __contains__(self, k: str):
        return k in self._data

    def get(self, k: str, default: Any):
        return self._data.get(k, default)

    def __getattr__(self, k: str):
        if k in self._data:
            return self._data[k]
        raise AttributeError(k)

    __setattr__ = __setitem__
    __delattr__ = __delitem__

    @contextmanager
    def ctx(self, k: str, v: T) -> Generator[T, None, None]:
        assert k not in self._data, f"key {k} already exists"
        assert not k.startswith("_") and k not in {"get", "ctx"}
        self[k] = v
        yield v
        del self[k]


V = Vars()
