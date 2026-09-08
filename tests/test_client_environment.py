import pytest
from test_location_hud import encoded, packet

from perfect_assassin.adapter.client_environment import (
    RETURN_KINDS,
    decode_environment_bits,
    environment_display,
)
from perfect_assassin.adapter.location_hud import (
    LocationStream,
    decode_location_packet,
    location_display,
)


@pytest.mark.parametrize("inside", range(8))
@pytest.mark.parametrize("outside", range(8))
def test_all_return_kinds_survive_crc_packet_without_inventing_a_floor(inside, outside):
    p = packet(version=2, environment=inside + 8 * outside, capabilities=3)
    decoded = decode_environment_bits(p.environment_bits, p.capabilities_bits)
    assert decoded["IsIndoors"] == RETURN_KINDS[inside]
    assert decoded["IsOutdoors"] == RETURN_KINDS[outside]
    assert (
        decoded["UnitPosition_available"]
        is decoded["GetPlayerFacing_available"]
        is True
    )
    assert decoded["confirmed_floor_id"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"version": 1, "environment": 1},
        {"version": 2, "environment": 64},
        {"version": 2, "capabilities": 4},
        {"version": 3},
    ],
)
def test_invalid_or_unknown_version_fields_are_rejected(kwargs):
    with pytest.raises(ValueError):
        decode_location_packet(encoded(**kwargs))


def test_legacy_packet_and_new_client_environment_share_freshness_gate():
    stream = LocationStream("client")
    assert stream.observe(packet(), 10) is None
    legacy = stream.observe(packet(millis=1200), 10.1)
    assert legacy["api_environment"] is None
    current = stream.observe(
        packet(version=2, environment=1 + 8 * 5, millis=1300), 10.2
    )
    assert current["api_environment"]["IsIndoors"] == "NIL"
    assert current["api_environment"]["IsOutdoors"] == "ONE"
    text = location_display(current, now_s=10.3, expected_binding="client")
    assert "interior=nil" in text and "exterior=1" in text
    assert "etaj neconfirmat" in text
    assert "Mediu client" not in location_display(
        current, now_s=15, expected_binding="client"
    )
    assert "Mediu client" not in location_display(
        current, now_s=10.3, expected_binding="other"
    )
    assert stream.observe(packet(version=2, environment=0, millis=1300), 99) is current
    assert (
        stream.observe(packet(version=2, environment=0, millis=1400, tag=44), 100)
        is None
    )


def test_failed_missing_and_nil_are_not_conflated():
    for bits, expected in ((0, "API absent"), (1, "nil"), (6, "eroare API")):
        assert expected in environment_display(decode_environment_bits(bits, 0))
    assert "neverificate" in environment_display({"source": "SERVER"})
