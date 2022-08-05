import asyncio
from re import S
from datasette import hookimpl
from functools import wraps
from time import monotonic
import logging
import sys


@hookimpl
def startup(datasette):
    # Verify that the config is valid
    get_config(datasette, "duration")
    get_config(datasette, "max-age")


@hookimpl
def asgi_wrapper(datasette):
    duration = get_config(datasette, "duration")
    max_age = get_config(datasette, "max-age")

    def wrap_with_scale_to_zero(app):
        if duration is None and max_age is None:
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
    duration = get_config(datasette, "duration")
    max_age = get_config(datasette, "max-age")

    if duration is None and max_age is None:
        return

    async def check_if_server_should_exit():
        server_start = monotonic()
        while True:
            await asyncio.sleep(1)
            last_asgi = getattr(datasette, "_scale_to_zero_last_asgi", None)
            should_exit = False
            if duration is not None and last_asgi is not None:
                # Have there been no reuests for longer than duration?
                if monotonic() - last_asgi > duration:
                    should_exit = True

            if max_age is not None:
                # Has server been running for longer than max_age?
                if monotonic() - server_start > max_age:
                    should_exit = True

            if should_exit:
                # Avoid logging a traceback when the server exits
                # https://github.com/simonw/datasette-scale-to-zero/issues/2
                logger = logging.getLogger("uvicorn.error")
                logger.disabled = True
                loop.call_soon(sys.exit, 0)

    loop = asyncio.get_running_loop()
    loop.create_task(check_if_server_should_exit())


def get_config(datasette, key):
    duration_s = (datasette.plugin_config("datasette-scale-to-zero") or {}).get(key)
    if duration_s is None:
        return None
    invalid_duration_message = (
        "{} must be a number followed by a unit (s, m, h)".format(key)
    )
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
        raise ValueError("Invalid {}".format(key))
