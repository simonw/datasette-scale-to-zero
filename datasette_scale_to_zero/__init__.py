import asyncio
from re import S
from datasette import hookimpl
from functools import wraps
import httpx
from time import monotonic
import logging
import sys


@hookimpl
def startup(datasette):
    # Verify that the config is valid
    get_config(datasette)


@hookimpl
def asgi_wrapper(datasette):
    config = get_config(datasette)

    def wrap_with_scale_to_zero(app):
        if config["duration"] is None and config["max_age"] is None:
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
    config = get_config(datasette)
    duration = config["duration"]
    max_age = config["max_age"]

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
                loop.call_soon(do_exit, datasette)

    loop = asyncio.get_running_loop()
    loop.create_task(check_if_server_should_exit())


def do_exit(datasette):
    config = get_config(datasette)
    try:
        if "shutdown_url" in config:
            # Send a request to the shutdown URL first
            shutdown_url = config["shutdown_url"]
            shutdown_method = config.get("shutdown_method", "GET")
            shutdown_headers = config.get("shutdown_headers", {})
            shutdown_body = config.get("shutdown_body", "")
            method = getattr(httpx, shutdown_method.lower())
            kwargs = {}
            if shutdown_headers:
                kwargs["headers"] = shutdown_headers
            if shutdown_body:
                kwargs["data"] = shutdown_body
            response = method(shutdown_url, **kwargs)
            response.raise_for_status()
    except Exception as e:
        print("Error sending shutdown request:", e, file=sys.stderr)
    finally:
        sys.exit(0)


def get_config(datasette):
    "Parse config, normalize durations to seconds, raises ValueError if invalid"
    raw_config = datasette.plugin_config("datasette-scale-to-zero") or {}
    config = {}
    if "max-age" in raw_config:
        # This key was renamed, but we still support the old name
        raw_config["max_age"] = raw_config.pop("max-age")

    valid_keys = (
        "duration",
        "max_age",
        "shutdown_url",
        "shutdown_headers",
        "shutdown_method",
        "shutdown_body",
    )
    invalid_keys = set(raw_config) - set(valid_keys)
    if invalid_keys:
        raise ValueError(
            "Invalid datasette-scale-to-zero configuration keys: {}".format(
                ", ".join(sorted(invalid_keys))
            )
        )

    # Resolve 10s/10m/10h to seconds for duration and max_age
    for key in ("duration", "max_age"):
        duration_s = raw_config.get(key)
        if duration_s is None:
            config[key] = None
            continue
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
            pass
        elif unit == "m":
            duration = duration * 60
        elif unit == "h":
            duration = duration * 60 * 60
        else:
            raise ValueError("Invalid {}".format(key))
        config[key] = duration

    # Validate the shutdown_x options
    if "shutdown_url" in raw_config:
        shutdown_url = raw_config["shutdown_url"] or ""
        if shutdown_url and not isinstance(shutdown_url, str):
            raise ValueError("shutdown_url must be a string")
        if shutdown_url and not shutdown_url.startswith("http"):
            raise ValueError("shutdown_url must start with http")

    if "shutdown_headers" in raw_config:
        shutdown_headers = raw_config["shutdown_headers"]
        if not isinstance(shutdown_headers, dict):
            raise ValueError("shutdown_headers must be a dictionary")

    if "shutdown_method" in raw_config:
        shutdown_method = raw_config["shutdown_method"]
        if not isinstance(shutdown_method, str):
            raise ValueError("shutdown_method must be a string")
        if shutdown_method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
            raise ValueError(
                "shutdown_method must be one of GET, POST, PUT, DELETE, PATCH"
            )

    if "shutdown_body" in raw_config:
        shutdown_body = raw_config["shutdown_body"]
        if not isinstance(shutdown_body, str):
            raise ValueError("shutdown_body must be a string")

    for key in raw_config:
        if key.startswith("shutdown_"):
            config[key] = raw_config[key]

    return config
