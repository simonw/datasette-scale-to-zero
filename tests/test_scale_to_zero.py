from datasette.app import Datasette
from datasette_scale_to_zero import get_config
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_duration", [1, "2", "3min", "dog"])
async def test_plugin_configuration(invalid_duration):
    with pytest.raises(ValueError) as ex:
        ds = Datasette(
            memory=True,
            metadata={
                "plugins": {"datasette-scale-to-zero": {"duration": invalid_duration}}
            },
        )
        await ds.invoke_startup()
        assert (
            ex.value.args[0] == "duration must be a number followed by a unit (s, m, h)"
        )


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
def test_get_config(duration, expected):
    datasette = Datasette(
        memory=True,
        metadata={"plugins": {"datasette-scale-to-zero": {"duration": duration}}},
    )
    actual = get_config(datasette)
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
