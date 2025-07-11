import argparse
import datetime
import enum
import socket


def class_name(obj: object):
    return f"{obj.__class__.__module__}.{obj.__class__.__qualname__}"


TZ_UTC_8 = datetime.timezone(datetime.timedelta(seconds=8 * 3600), name="Asia/Shanghai")


def utc_8_now():
    return datetime.datetime.now(tz=TZ_UTC_8)


def get_timestr(style=0):
    now = utc_8_now()
    if style == 0:
        # 1970-01-01 08:00:00,000
        return now.strftime(f"%Y-%m-%d %H:%M:%S,{now.microsecond // 1000:03d}")
    elif style == 1:
        # 1970.01.01-08.00.00
        return now.strftime("%Y.%m.%d-%H.%M.%S")
    else:
        raise ValueError("invalid style")


class EnumAction(argparse.Action):
    """
    Argparse action for handling Enums.
    Automatically generates choices from the enum and converts input strings to enum instances.
    """

    def __init__(self, **kwargs):
        enum_type = kwargs.pop("type", None)

        if enum_type is None:
            raise ValueError("'type' must be assigned an Enum when using EnumAction")
        if not issubclass(enum_type, enum.Enum):
            raise TypeError("'type' must be an Enum")

        # Generate choices from the enum
        kwargs.setdefault("choices", tuple(e.value for e in enum_type))

        super().__init__(**kwargs)

        self._enum = enum_type

    def __call__(self, parser, namespace, values, option_string=None):
        # Convert value back into an enum instance
        if isinstance(values, list):
            # Handle multiple values (for nargs='+' or '*')
            enum_values = [self._enum(v) for v in values]
        else:
            # Handle single value
            enum_values = self._enum(values)

        setattr(namespace, self.dest, enum_values)


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception:
        return "127.0.0.1"
