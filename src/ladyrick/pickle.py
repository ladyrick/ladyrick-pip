"用于 load 那些无法 import 类的对象"

import pickle
import sys
import types

_created_modules = {}


class _Meta(type):
    def __getattr__(cls, subclass_name: str):
        if subclass_name.startswith("__"):
            super().__getattr__(subclass_name)
        kw = {
            "__module__": cls.__module__,
            "__qualname__": f"{cls.__qualname__}.{subclass_name}",
        }
        subclass = type(subclass_name, (_Base,), kw)
        setattr(cls, subclass_name, subclass)
        return subclass


def _custom_reduce(self):
    return (self.__class__, self._args, self._kwargs)


class _Base(metaclass=_Meta):
    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        self.__class__.__reduce__ = _custom_reduce

    def __repr__(self):
        if getattr(self.__class__, "__reduce__", None) is _custom_reduce:
            args = self._args
            kwargs = self._kwargs
        else:
            args = ()
            kwargs = vars(self)
        comps = []
        if args:
            comps += [repr(a) for a in args]
        if kwargs:
            comps += [f"{k}={v!r}" for k, v in kwargs.items()]
        return f"{self.__class__.__module__}.{self.__class__.__qualname__}({', '.join(comps)})"


def _create_class(modulename: str, qualname: str):
    if modulename not in _created_modules:
        if modulename in sys.modules:
            raise ImportError("cannot overwrite exist module")
        module = types.ModuleType(modulename, "created by ladyrick")
        _created_modules[modulename] = sys.modules[modulename] = module

    module = _created_modules[modulename]
    m_kw = {"__module__": modulename}
    top_name = qualname.split(".")[0]
    assert top_name, f"invalid qualname: {qualname}"
    top_cls = type(top_name, (_Base,), {**m_kw, "__qualname__": top_name})
    setattr(module, top_name, top_cls)
    return top_cls


class PickleAnything:
    class Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            try:
                return super().find_class(module, name)
            except (ImportError, AttributeError):
                return _create_class(module, name)


Unpickler = PickleAnything.Unpickler
