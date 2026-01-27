"用于 load 那些无法 import 类的对象"

import pickle

from ladyrick.utils import class_name


class FakeClassMeta(type):
    def __getattr__(cls, subclass_name: str):
        if subclass_name.startswith("__"):
            return getattr(super(), subclass_name)
        kw = {
            "__module__": cls.__module__,
            "__qualname__": f"{cls.__qualname__}.{subclass_name}",
        }
        subclass = type(subclass_name, (FakeClass,), kw)
        setattr(cls, subclass_name, subclass)
        return subclass


class FakeClass(metaclass=FakeClassMeta):
    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance.args = args
        instance.kwargs = kwargs
        instance.state = None
        return instance

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.state = None

    def __repr__(self):
        comps = []
        if self.args:
            comps += [repr(a) for a in self.args]
        if self.kwargs:
            comps += [f"{k}={v!r}" for k, v in self.kwargs.items()]
        if self.state is not None:
            comps.append(f"state={self.state!r}")
        return f"{class_name(self)}({', '.join(comps)})"

    def __setstate__(self, state):
        self.state = state

    def __reduce__(self):
        raise pickle.PickleError("cannot pickle a fake class")


def _create_class(modulename: str, qualname: str):
    m_kw = {"__module__": modulename}
    top_name = qualname.split(".")[0]
    assert top_name, f"invalid qualname: {qualname}"
    top_cls = type(top_name, (FakeClass,), {**m_kw, "__qualname__": top_name})
    return top_cls


class Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except (ImportError, AttributeError):
            return _create_class(module, name)
