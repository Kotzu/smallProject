"""Raw addon API returns, not an inferred floor or a geometric ceiling."""

RETURN_KINDS = (
    "API_ABSENT",
    "NIL",
    "FALSE",
    "TRUE",
    "ZERO",
    "ONE",
    "CALL_ERROR",
    "UNSUPPORTED",
)


def decode_environment_bits(environment, capabilities):
    if (
        type(environment) is not int
        or not 0 <= environment <= 63
        or type(capabilities) is not int
        or not 0 <= capabilities <= 3
    ):
        raise ValueError("invalid environment bits")
    return {
        "schema_version": 1,
        "source": "CLIENT_ADDON_API",
        "IsIndoors": RETURN_KINDS[environment & 7],
        "IsOutdoors": RETURN_KINDS[(environment >> 3) & 7],
        "UnitPosition_available": bool(capabilities & 1),
        "GetPlayerFacing_available": bool(capabilities & 2),
        "confirmed_floor_id": None,
    }


def environment_display(record):
    unknown = "Mediu client: API-uri încă neverificate · etaj neconfirmat"
    if not isinstance(record, dict):
        return unknown
    if (
        record.get("schema_version") != 1
        or record.get("source") != "CLIENT_ADDON_API"
        or record.get("confirmed_floor_id") is not None
    ):
        return unknown
    values = {
        "API_ABSENT": "API absent",
        "NIL": "nil",
        "FALSE": "false",
        "TRUE": "true",
        "ZERO": "0",
        "ONE": "1",
        "CALL_ERROR": "eroare API",
        "UNSUPPORTED": "valoare neacceptată",
    }
    indoor, outdoor = record.get("IsIndoors"), record.get("IsOutdoors")
    if not isinstance(indoor, str) or not isinstance(outdoor, str):
        return unknown
    if indoor not in values or outdoor not in values:
        return unknown
    return f"Mediu client (valori API): interior={values[indoor]} · exterior={values[outdoor]} · etaj neconfirmat"
