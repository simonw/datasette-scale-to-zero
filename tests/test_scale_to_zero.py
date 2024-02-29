import asyncio
from time import monotonic
from datasette_test import Datasette
from datasette_scale_to_zero import get_config
import pytest
from unittest.mock import MagicMock
import json
import subprocess
import sys


@pytest.fixture
def non_mocked_hosts():
    # This ensures httpx-mock will not affect Datasette's own
    # httpx calls made in the tests by datasette.client:
    return ["localhost"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_duration", [1, "2", "3min", "dog"])
@pytest.mark.parametrize("key", ("duration", "max_age", "max-age"))
async def test_plugin_configuration(invalid_duration, key):
    with pytest.raises(ValueError) as ex:
        ds = Datasette(
            memory=True,
            plugin_config={"datasette-scale-to-zero": {key: invalid_duration}},
        )
        await ds.invoke_startup()
    message = ex.value.args[0]
    assert message == "{} must be a number followed by a unit (s, m, h)".format(
        key.replace("-", "_")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config,expected_error",
    (
        ({"shutdown_url": 1}, "shutdown_url must be a string"),
        ({"shutdown_url": "foo"}, "shutdown_url must start with http"),
        ({"shutdown_headers": 1}, "shutdown_headers must be a dictionary"),
        (
            {"shutdown_headers": {"foo": 1}},
            "shutdown_headers must be a dictionary of strings",
        ),
        ({"shutdown_method": 1}, "shutdown_method must be a string"),
        (
            {"shutdown_method": "foo"},
            "shutdown_method must be one of GET, POST, PUT, DELETE, PATCH",
        ),
        ({"shutdown_body": 1}, "shutdown_body must be a string"),
        (
            {"bad": "1", "keys": "2"},
            "Invalid datasette-scale-to-zero configuration keys: bad, keys",
        ),
    ),
)
async def test_invalid_configurations(config, expected_error):
    with pytest.raises(ValueError) as ex:
        ds = Datasette(
            memory=True,
            plugin_config={"datasette-scale-to-zero": config},
        )
        await ds.invoke_startup()
    message = ex.value.args[0]
    assert message == expected_error


@pytest.mark.parametrize(
    "duration,expected",
    (
        (None, None),
        ("1s", 1),
        ("1m", 60),
        ("1h", 60 * 60),
        ("10m", 10 * 60),
    ),
)
@pytest.mark.parametrize("key", ("duration", "max_age"))
def test_get_config(key, duration, expected):
    datasette = Datasette(
        memory=True,
        metadata={
            "plugins": {
                "datasette-scale-to-zero": {"duration": duration, "max_age": duration}
            }
        },
    )
    actual = get_config(datasette)[key]
    assert actual == expected


@pytest.mark.asyncio
async def test_records_last_asgi():
    datasette = Datasette(
        memory=True,
        plugin_config={"datasette-scale-to-zero": {"duration": "1s"}},
    )
    assert not hasattr(datasette, "_scale_to_zero_last_asgi")
    await datasette.invoke_startup()
    await datasette.client.get("/")
    assert datasette._scale_to_zero_last_asgi is not None


@pytest.mark.parametrize("key", ("duration", "max_age"))
def test_server_quits(tmpdir, key):
    metadata = tmpdir / "metadata.json"
    metadata.write_text(
        json.dumps({"plugins": {"datasette-scale-to-zero": {key: "1s"}}}), "utf-8"
    )
    start = monotonic()
    subprocess.run(
        [sys.executable, "-m", "datasette", "-p", "9014", "-m", str(metadata)],
        timeout=3,
        check=True,
        capture_output=True,
    )
    end = monotonic()
    assert end - start < 3


@pytest.fixture
def mock_sys_exit(monkeypatch):
    exit_mock = MagicMock()
    monkeypatch.setattr(sys, "exit", exit_mock)
    return exit_mock


@pytest.mark.asyncio
async def test_shutdown_pings_shutdown_url(mock_sys_exit, httpx_mock):
    httpx_mock.add_response(url="https://example.com/shutdown")
    datasette = Datasette(
        memory=True,
        plugin_config={
            "datasette-scale-to-zero": {
                "duration": "1s",
                "shutdown_url": "https://example.com/shutdown",
                "shutdown_method": "POST",
                "shutdown_headers": {"Authorization": "Bearer secret"},
                "shutdown_body": '{"message": "shutting down"}',
            }
        },
    )
    await datasette.invoke_startup()
    await datasette.client.get("/")
    await asyncio.sleep(1.2)
    assert mock_sys_exit.called
    request = httpx_mock.get_request()
    assert request.method == "POST"
    assert request.url == "https://example.com/shutdown"
    assert request.headers["Authorization"] == "Bearer secret"
    assert request.content == b'{"message": "shutting down"}'
