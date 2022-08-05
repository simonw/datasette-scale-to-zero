from time import monotonic
from datasette.app import Datasette
from datasette_scale_to_zero import get_config
import pytest
import json
import subprocess
import sys


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_duration", [1, "2", "3min", "dog"])
@pytest.mark.parametrize("key", ("duration", "max-age"))
async def test_plugin_configuration(invalid_duration, key):
    with pytest.raises(ValueError) as ex:
        ds = Datasette(
            memory=True,
            metadata={"plugins": {"datasette-scale-to-zero": {key: invalid_duration}}},
        )
        await ds.invoke_startup()
    message = ex.value.args[0]
    assert message == "{} must be a number followed by a unit (s, m, h)".format(key)


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
@pytest.mark.parametrize("key", ("duration", "max-age"))
def test_get_config(key, duration, expected):
    datasette = Datasette(
        memory=True,
        metadata={
            "plugins": {
                "datasette-scale-to-zero": {"duration": duration, "max-age": duration}
            }
        },
    )
    actual = get_config(datasette, key)
    assert actual == expected


@pytest.mark.asyncio
async def test_records_last_asgi():
    datasette = Datasette(
        memory=True,
        metadata={"plugins": {"datasette-scale-to-zero": {"duration": "1s"}}},
    )
    assert not hasattr(datasette, "_scale_to_zero_last_asgi")
    await datasette.invoke_startup()
    await datasette.client.get("/")
    assert datasette._scale_to_zero_last_asgi is not None


@pytest.mark.parametrize("key", ("duration", "max-age"))
def test_server_quits(tmpdir, key):
    metadata = tmpdir / "metadata.json"
    metadata.write_text(
        json.dumps({"plugins": {"datasette-scale-to-zero": {key: "1s"}}}), "utf-8"
    )
    start = monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "datasette", "-p", "9014", "-m", str(metadata)],
        timeout=3,
        check=True,
        capture_output=True,
    )
    end = monotonic()
    assert end - start < 2
