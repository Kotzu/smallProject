import struct
import unittest

from perfect_assassin.adapter.adt_road import (
    AdtRoadSemantic,
    ROAD_SIDECAR_DIMENSION,
    _decode_alpha,
    parse_adt_road_semantic,
)


def _chunk(kind: str, payload: bytes) -> bytes:
    return kind[::-1].encode("ascii") + struct.pack("<I", len(payload)) + payload


def _textured_adt(
    *,
    texture_names: tuple[str, ...],
    texture_ids: tuple[int, ...],
    upper_alphas: tuple[bytes, ...],
    compressed_upper: bool = False,
) -> bytes:
    if len(texture_ids) != len(upper_alphas) + 1:
        raise ValueError("one alpha map is required for every non-base layer")
    header = bytearray(0x80)
    struct.pack_into("<III", header, 4, 0, 0, len(texture_ids))
    struct.pack_into("<I", header, 28, 0x80)
    layer_bytes = b"".join(
        struct.pack(
            "<4I",
            texture_id,
            0 if index == 0 else (0x100 | (0x200 if compressed_upper else 0)),
            0 if index == 0 else (index - 1) * 4096,
            0,
        )
        for index, texture_id in enumerate(texture_ids)
    )
    def encode_alpha(alpha: bytes) -> bytes:
        if not compressed_upper:
            return alpha
        if len(alpha) != 4096:
            raise ValueError("compressed fixture alpha must be 64x64")
        return b"".join(bytes((0xC0, value)) for value in alpha[::64])

    alpha_bytes = b"".join(encode_alpha(alpha) for alpha in upper_alphas)
    struct.pack_into("<I", header, 36, 0x80 + len(layer_bytes))
    struct.pack_into("<I", header, 40, len(alpha_bytes) + 8)
    populated = bytes(header) + layer_bytes + alpha_bytes
    empty = bytes(0x80)
    return b"".join((
        _chunk("MVER", struct.pack("<I", 18)),
        _chunk("MTEX", b"\x00".join(name.encode() for name in texture_names) + b"\x00"),
        _chunk("MCNK", populated),
        *(_chunk("MCNK", empty) for _index in range(255)),
    ))


def _first_chunk_values(semantic: AdtRoadSemantic) -> set[int]:
    return {
        semantic.affinity[row * ROAD_SIDECAR_DIMENSION + column]
        for row in range(64)
        for column in range(64)
    }


class AdtRoadSemanticTests(unittest.TestCase):
    def test_sidecar_round_trip(self) -> None:
        affinity = bytes([0]) * (ROAD_SIDECAR_DIMENSION**2 - 1) + bytes([255])
        semantic = AdtRoadSemantic(
            29, 28, ROAD_SIDECAR_DIMENSION, ROAD_SIDECAR_DIMENSION,
            affinity, ("Tileset\\TirisFall\\TirisFallStoneRoad01.blp",),
        )
        restored = AdtRoadSemantic.from_bytes(semantic.to_bytes())
        self.assertEqual((restored.adt_x, restored.adt_y), (29, 28))
        self.assertEqual(restored.affinity[-1], 255)

    def test_sidecar_rejects_wrong_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "size"):
            AdtRoadSemantic(29, 28, 1024, 1024, b"bad", ("road",))

    def test_textureless_zero_layer_adt_produces_neutral_semantics(self) -> None:
        mcnk = bytes(0x80)
        payload = b"".join((
            _chunk("MVER", struct.pack("<I", 18)),
            _chunk("MTEX", b""),
            *(_chunk("MCNK", mcnk) for _index in range(256)),
        ))

        semantic = parse_adt_road_semantic(payload, adt_x=29, adt_y=30)

        self.assertEqual(semantic.texture_names, ())
        self.assertFalse(any(semantic.affinity))

    def test_textureless_adt_with_layers_is_rejected(self) -> None:
        header = bytearray(0x80)
        struct.pack_into("<I", header, 12, 1)
        payload = b"".join((
            _chunk("MVER", struct.pack("<I", 18)),
            _chunk("MTEX", b""),
            _chunk("MCNK", bytes(header)),
            *(_chunk("MCNK", bytes(0x80)) for _index in range(255)),
        ))

        with self.assertRaisesRegex(ValueError, "layers but no texture"):
            parse_adt_road_semantic(payload, adt_x=29, adt_y=30)

    def test_textured_instance_border_allows_zero_layer_chunks(self) -> None:
        empty = bytearray(0x80)
        populated = bytearray(0x80)
        struct.pack_into("<III", populated, 4, 1, 0, 1)
        struct.pack_into("<I", populated, 28, 0x80)
        layer = struct.pack("<4I", 0, 0, 0, 0)
        payload = b"".join((
            _chunk("MVER", struct.pack("<I", 18)),
            _chunk("MTEX", b"InstanceStone.blp\x00"),
            _chunk("MCNK", bytes(populated) + layer),
            *(_chunk("MCNK", bytes(empty)) for _index in range(255)),
        ))

        semantic = parse_adt_road_semantic(payload, adt_x=29, adt_y=27)

        self.assertEqual(semantic.texture_names, ("InstanceStone.blp",))
        self.assertFalse(any(semantic.affinity))

    def test_non_road_upper_layer_removes_covered_road_base(self) -> None:
        semantic = parse_adt_road_semantic(
            _textured_adt(
                texture_names=("StoneRoad.blp", "Grass.blp"),
                texture_ids=(0, 1),
                upper_alphas=(bytes([255]) * 4096,),
            ),
            adt_x=29,
            adt_y=27,
        )

        self.assertEqual(_first_chunk_values(semantic), {0})

    def test_road_base_keeps_only_its_uncovered_weight(self) -> None:
        semantic = parse_adt_road_semantic(
            _textured_adt(
                texture_names=("StoneRoad.blp", "Grass.blp"),
                texture_ids=(0, 1),
                upper_alphas=(bytes([128]) * 4096,),
            ),
            adt_x=29,
            adt_y=27,
        )

        self.assertEqual(_first_chunk_values(semantic), {127})

    def test_upper_road_layer_contributes_its_independent_alpha(self) -> None:
        semantic = parse_adt_road_semantic(
            _textured_adt(
                texture_names=("Grass.blp", "DirtPath.blp", "Mud.blp"),
                texture_ids=(0, 1, 2),
                upper_alphas=(bytes([96]) * 4096, bytes([80]) * 4096),
            ),
            adt_x=29,
            adt_y=27,
        )

        self.assertEqual(_first_chunk_values(semantic), {96})

    def test_compressed_alpha_map_decodes_bounded_rle(self) -> None:
        semantic = parse_adt_road_semantic(
            _textured_adt(
                texture_names=("StoneRoad.blp", "Grass.blp"),
                texture_ids=(0, 1),
                upper_alphas=(bytes([255]) * 4096,),
                compressed_upper=True,
            ),
            adt_x=29,
            adt_y=27,
        )

        self.assertEqual(_first_chunk_values(semantic), {0})

    def test_compressed_alpha_map_rejects_output_overflow(self) -> None:
        payload = b"".join(bytes((0xFF, 255)) for _ in range(33))

        with self.assertRaisesRegex(ValueError, "64x64"):
            _decode_alpha(payload, compressed=True)


if __name__ == "__main__":
    unittest.main()
