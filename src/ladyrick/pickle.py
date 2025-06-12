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
    __load_method__ = "__dict__"

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        cls.__load_method__ = "__new__"
        setattr(instance, "__args", args)
        setattr(instance, "__kwargs", kwargs)
        return instance

    def __repr__(self):
        if self.__class__.__load_method__ == "__new__":
            args = getattr(self, "__args")
            kwargs = getattr(self, "__kwargs")
        elif self.__class__.__load_method__ == "__dict__":
            args = ()
            kwargs = vars(self)
        else:
            args = ()
            kwargs = {"state": self.state}
        comps = []
        if args:
            comps += [repr(a) for a in args]
        if kwargs:
            comps += [f"{k}={v!r}" for k, v in kwargs.items()]
        return f"{class_name(self)}({', '.join(comps)})"

    def __setstate__(self, state):
        self.__class__.__load_method__ = "__setstate__"
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
