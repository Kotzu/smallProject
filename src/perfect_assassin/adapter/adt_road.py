from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Iterator

import numpy as np


ROAD_SIDECAR_MAGIC = b"PAROAD1\x00"
ROAD_SIDECAR_DIMENSION = 1024
MCLY_USE_ALPHA_MAP = 0x100
MCLY_ALPHA_COMPRESSED = 0x200


@dataclass(frozen=True, slots=True)
class AdtRoadSemantic:
    adt_x: int
    adt_y: int
    width: int
    height: int
    affinity: bytes
    texture_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.adt_x < 64 or not 0 <= self.adt_y < 64:
            raise ValueError("ADT coordinates are invalid")
        if self.width != ROAD_SIDECAR_DIMENSION or self.height != ROAD_SIDECAR_DIMENSION:
            raise ValueError("road semantic dimensions are invalid")
        if len(self.affinity) != self.width * self.height:
            raise ValueError("road semantic affinity size is invalid")
        if not self.texture_names and any(self.affinity):
            raise ValueError("textureless ADT cannot contain road affinity")

    def to_bytes(self) -> bytes:
        return (
            ROAD_SIDECAR_MAGIC
            + struct.pack("<5I", 1, self.adt_x, self.adt_y, self.width, self.height)
            + self.affinity
        )

    @classmethod
    def from_bytes(cls, payload: bytes, *, texture_names: tuple[str, ...] = ("sidecar",)) -> "AdtRoadSemantic":
        if len(payload) < 28 or payload[:8] != ROAD_SIDECAR_MAGIC:
            raise ValueError("road sidecar envelope is invalid")
        version, adt_x, adt_y, width, height = struct.unpack_from("<5I", payload, 8)
        if version != 1:
            raise ValueError("road sidecar version is unsupported")
        return cls(adt_x, adt_y, width, height, payload[28:], texture_names)


def _chunks(payload: bytes) -> Iterator[tuple[str, int, int]]:
    offset = 0
    while offset + 8 <= len(payload):
        kind = payload[offset:offset + 4][::-1].decode("ascii", "replace")
        size = struct.unpack_from("<I", payload, offset + 4)[0]
        end = offset + 8 + size
        if end > len(payload):
            raise ValueError("ADT chunk extends beyond the file")
        yield kind, offset, size
        offset = end
    if offset != len(payload):
        raise ValueError("ADT has trailing bytes outside a chunk")


def _decode_alpha(payload: bytes, *, compressed: bool = False) -> bytes:
    if compressed:
        # TBC MCAL compressed alpha uses bounded RLE blocks. A control byte
        # with bit 7 set repeats the following byte; otherwise it copies the
        # next control-byte literal bytes. Never allow malformed data to grow
        # beyond one 64x64 alpha map.
        output = bytearray()
        cursor = 0
        while cursor < len(payload):
            control = payload[cursor]
            cursor += 1
            count = control & 0x7F
            if count == 0:
                raise ValueError("compressed ADT alpha map contains a zero-length block")
            if control & 0x80:
                if cursor >= len(payload):
                    raise ValueError("compressed ADT alpha map repeat block is truncated")
                if len(output) + count > 4096:
                    raise ValueError("compressed ADT alpha map exceeds 64x64")
                output.extend([payload[cursor]] * count)
                cursor += 1
            else:
                if cursor + count > len(payload):
                    raise ValueError("compressed ADT alpha map literal block is truncated")
                if len(output) + count > 4096:
                    raise ValueError("compressed ADT alpha map exceeds 64x64")
                output.extend(payload[cursor:cursor + count])
                cursor += count
        if len(output) != 4096:
            raise ValueError("compressed ADT alpha map is not 64x64")
        return bytes(output)
    if len(payload) >= 4096:
        return payload[:4096]
    if len(payload) >= 2048:
        output = bytearray(4096)
        for index, value in enumerate(payload[:2048]):
            output[index * 2] = (value & 15) * 17
            output[index * 2 + 1] = (value >> 4) * 17
        return bytes(output)
    raise ValueError("ADT alpha layer is shorter than 64x64")


def parse_adt_road_semantic(payload: bytes, *, adt_x: int, adt_y: int) -> AdtRoadSemantic:
    chunks = tuple(_chunks(payload))
    if not chunks or chunks[0][0] != "MVER":
        raise ValueError("ADT does not begin with MVER")
    texture_names: tuple[str, ...] = ()
    mcnks: list[tuple[int, int]] = []
    for kind, offset, size in chunks:
        if kind == "MTEX":
            raw = payload[offset + 8:offset + 8 + size]
            texture_names = tuple(
                value.decode("utf-8", "replace")
                for value in raw.rstrip(b"\x00").split(b"\x00") if value
            )
        elif kind == "MCNK":
            mcnks.append((offset, size))
    if len(mcnks) != 256:
        raise ValueError("ADT is missing its 256 terrain chunks")
    if not texture_names:
        for offset, size in mcnks:
            if size < 0x80:
                raise ValueError("textureless ADT has a truncated terrain chunk")
            layer_count = struct.unpack_from("<13I", payload, offset + 8)[3]
            if layer_count != 0:
                raise ValueError("ADT has terrain layers but no texture table")
        return AdtRoadSemantic(
            adt_x,
            adt_y,
            ROAD_SIDECAR_DIMENSION,
            ROAD_SIDECAR_DIMENSION,
            bytes(ROAD_SIDECAR_DIMENSION * ROAD_SIDECAR_DIMENSION),
            (),
        )
    road_texture_ids = {
        index for index, name in enumerate(texture_names)
        if "road" in name.casefold() or "path" in name.casefold()
    }
    affinity = bytearray(ROAD_SIDECAR_DIMENSION * ROAD_SIDECAR_DIMENSION)
    affinity_view = np.frombuffer(affinity, dtype=np.uint8).reshape(
        ROAD_SIDECAR_DIMENSION,
        ROAD_SIDECAR_DIMENSION,
    )
    for offset, size in mcnks:
        if size < 0x80:
            continue
        header = struct.unpack_from("<13I", payload, offset + 8)
        chunk_x, chunk_y, layer_count = header[1], header[2], header[3]
        if chunk_x >= 16 or chunk_y >= 16 or layer_count > 4:
            raise ValueError("ADT MCNK terrain layer header is invalid")
        # Interior/instance border ADTs can retain a structurally valid MCNK
        # with zero texture layers. It contributes neutral affinity; treating
        # it as corrupt prevents complete client coverage.
        if layer_count == 0:
            continue
        layer_payload = offset + header[7] + 8
        alpha_payload = offset + header[9] + 8
        alpha_size = max(0, header[10] - 8)
        if layer_payload + layer_count * 16 > offset + 8 + size:
            raise ValueError("ADT MCLY is outside MCNK")
        layers = [struct.unpack_from("<4I", payload, layer_payload + index * 16)
                  for index in range(layer_count)]
        alpha_offsets = [layer[2] for layer in layers[1:]]
        upper_alphas: list[np.ndarray] = []
        for layer_index, (_texture_id, flags, alpha_offset, _effect_id) in enumerate(layers):
            if layer_index == 0:
                continue
            if not flags & MCLY_USE_ALPHA_MAP:
                raise ValueError("non-base ADT terrain layer has no alpha map")
            following = [value for value in alpha_offsets if value > alpha_offset]
            end_offset = min(following) if following else alpha_size
            if end_offset <= alpha_offset:
                raise ValueError("ADT alpha layer offsets are invalid")
            upper_alphas.append(np.frombuffer(
                _decode_alpha(
                    payload[alpha_payload + alpha_offset:alpha_payload + end_offset],
                    compressed=bool(flags & MCLY_ALPHA_COMPRESSED),
                ),
                dtype=np.uint8,
            ).astype(np.uint16))

        # The base layer has no alpha channel. Its visible contribution is the
        # residual after the independent MCAL weights of layers 1..3; every
        # upper road layer contributes its own alpha. Taking max(), as the old
        # extractor did, falsely left a road base at 255 even where grass or
        # dirt covered it completely.
        upper_total = np.zeros(4096, dtype=np.uint16)
        road_weight = np.zeros(4096, dtype=np.uint16)
        for layer, layer_alpha in zip(layers[1:], upper_alphas, strict=True):
            upper_total += layer_alpha
            if layer[0] in road_texture_ids:
                road_weight += layer_alpha
        if layers[0][0] in road_texture_ids:
            road_weight += np.maximum(255 - np.minimum(upper_total, 255), 0)
        road_block = np.minimum(road_weight, 255).astype(np.uint8).reshape(64, 64)
        affinity_view[
            chunk_y * 64:(chunk_y + 1) * 64,
            chunk_x * 64:(chunk_x + 1) * 64,
        ] = road_block
    return AdtRoadSemantic(
        adt_x, adt_y, ROAD_SIDECAR_DIMENSION, ROAD_SIDECAR_DIMENSION,
        bytes(affinity), texture_names,
    )


def build_road_sidecar(source: Path, destination: Path, *, adt_x: int, adt_y: int) -> AdtRoadSemantic:
    semantic = parse_adt_road_semantic(source.read_bytes(), adt_x=adt_x, adt_y=adt_y)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(semantic.to_bytes())
    return semantic
