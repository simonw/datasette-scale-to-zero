import asyncio
from datasette import hookimpl
from functools import wraps
from time import monotonic
import sys


@hookimpl
def startup(datasette):
    # Verify that the config is valid
    get_config(datasette)


@hookimpl
def asgi_wrapper(datasette):
    duration = get_config(datasette)

    def wrap_with_scale_to_zero(app):
        if not duration:
            return app

        @wraps(app)
        async def record_last_request(scope, receive, send):
            if not hasattr(datasette, "_scale_to_zero_last_asgi"):
                start_that_loop(datasette)
            datasette._scale_to_zero_last_asgi = monotonic()
            await app(scope, receive, send)

        return record_last_request

    return wrap_with_scale_to_zero


def start_that_loop(datasette):
    duration = get_config(datasette)
    if duration is None:
        return

    async def exit_if_no_recent_activity():
        while True:
            await asyncio.sleep(1)
            last_asgi = getattr(datasette, "_scale_to_zero_last_asgi", None)
            if last_asgi is None:
                continue
            if monotonic() - last_asgi > duration:
                loop.call_soon(sys.exit, 0)

    loop = asyncio.get_running_loop()
    loop.create_task(exit_if_no_recent_activity())


def get_config(datasette):
    duration_s = (datasette.plugin_config("datasette-scale-to-zero") or {}).get(
        "duration"
    )
    if duration_s is None:
        return None
    invalid_duration_message = "duration must be a number followed by a unit (s, m, h)"
    if not isinstance(duration_s, str):
        raise ValueError(invalid_duration_message)
    unit = duration_s[-1]
    digits = duration_s[:-1]
    if not digits.isdigit():
        raise ValueError(invalid_duration_message)
    duration = int(digits)
    if unit == "s":
        return duration
    elif unit == "m":
        return duration * 60
    elif unit == "h":
        return duration * 60 * 60
    else:
        raise ValueError("Invalid duration")
