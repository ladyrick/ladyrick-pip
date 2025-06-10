from typing import Any, Callable, TypeVar, cast

T = TypeVar("T")


def type_like(typed_obj: T) -> Callable[[Any], T]:
    def decorator(obj: Any) -> T:
        return cast(T, obj)

    return decorator
