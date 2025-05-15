def patch_print():
    import builtins
    from functools import wraps

    from ladyrick.print_utils import builtin_print
    from ladyrick.print_utils import parallel_print as new_print

    builtins.print = wraps(builtin_print)(new_print)

    import sys
    import traceback

    def custom_excepthook(exc_type, exc_value, exc_traceback):
        new_print("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))

    sys.excepthook = custom_excepthook

    import threading

    def custom_thread_excepthook(args):
        exc_list = traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        new_print(f"Exception in thread {args.thread.name}:\n" + "".join(exc_list))

    threading.excepthook = custom_thread_excepthook

    return builtin_print


builtin_print = patch_print()
del patch_print
