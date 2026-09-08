from __future__ import annotations

import unittest

from perfect_assassin.movement.client_world_adapter import (
    ClientWorldAdapterError,
    available_client_world_adapters,
    resolve_client_world_adapter,
)


class ClientWorldAdapterTests(unittest.TestCase):
    def test_mpq_wdbc_adapter_has_no_runtime_process_dependencies(self) -> None:
        adapter = resolve_client_world_adapter(
            asset_container="mpq",
            world_catalog_parser_profile="wow-wdbc-map-v1",
        )

        self.assertEqual(adapter.adapter_id, "wow-mpq-wdbc-v1")
        self.assertFalse(adapter.runtime_client_required)
        self.assertFalse(adapter.runtime_server_required)
        self.assertFalse(adapter.runtime_emulator_required)
        self.assertEqual(available_client_world_adapters(), (adapter,))

    def test_unimplemented_casc_parser_pair_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            ClientWorldAdapterError,
            "no exact standalone client-world adapter",
        ):
            resolve_client_world_adapter(
                asset_container="casc",
                world_catalog_parser_profile="wow-wdc5-map-v1",
            )
