from __future__ import annotations

from dataclasses import dataclass


class ClientWorldAdapterError(ValueError):
    """Raised when no exact offline client-asset adapter is installed."""


@dataclass(frozen=True, slots=True)
class ClientWorldAssetAdapter:
    adapter_id: str
    asset_container: str
    world_catalog_parser_profile: str
    inventory_protocol: str
    map_extraction_protocol: str
    runtime_client_required: bool = False
    runtime_server_required: bool = False
    runtime_emulator_required: bool = False


_ADAPTERS = (
    ClientWorldAssetAdapter(
        adapter_id="wow-mpq-wdbc-v1",
        asset_container="mpq",
        world_catalog_parser_profile="wow-wdbc-map-v1",
        inventory_protocol="pa-client-world-inventory-v1",
        map_extraction_protocol="pa-client-map-extraction-v1",
    ),
)


def available_client_world_adapters() -> tuple[ClientWorldAssetAdapter, ...]:
    return _ADAPTERS


def resolve_client_world_adapter(
    *, asset_container: str, world_catalog_parser_profile: str,
) -> ClientWorldAssetAdapter:
    matches = tuple(
        adapter for adapter in _ADAPTERS
        if adapter.asset_container == asset_container
        and adapter.world_catalog_parser_profile == world_catalog_parser_profile
    )
    if len(matches) != 1:
        raise ClientWorldAdapterError(
            "no exact standalone client-world adapter is installed for "
            f"{asset_container!r} + {world_catalog_parser_profile!r}"
        )
    return matches[0]
