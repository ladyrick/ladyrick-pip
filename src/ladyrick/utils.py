import datetime


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
