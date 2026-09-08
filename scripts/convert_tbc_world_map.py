from __future__ import annotations

import argparse
from pathlib import Path
import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TBC_WORLD_MAP_WIDTH = 1002
TBC_WORLD_MAP_HEIGHT = 668


def _rgb565(value: int) -> tuple[int, int, int, int]:
    red = ((value >> 11) & 31) * 255 // 31
    green = ((value >> 5) & 63) * 255 // 63
    blue = (value & 31) * 255 // 31
    return red, green, blue, 255


def _decode_dxt1(payload: bytes, width: int, height: int) -> bytes:
    expected = ((width + 3) // 4) * ((height + 3) // 4) * 8
    if len(payload) < expected:
        raise ValueError("BLP mip is shorter than its DXT1 dimensions")
    rgba = bytearray(width * height * 4)
    offset = 0
    for block_y in range(0, height, 4):
        for block_x in range(0, width, 4):
            color0, color1, selectors = struct.unpack_from("<HHI", payload, offset)
            offset += 8
            first = _rgb565(color0)
            second = _rgb565(color1)
            if color0 > color1:
                palette = (
                    first,
                    second,
                    tuple((2 * first[i] + second[i]) // 3 for i in range(3)) + (255,),
                    tuple((first[i] + 2 * second[i]) // 3 for i in range(3)) + (255,),
                )
            else:
                palette = (
                    first,
                    second,
                    tuple((first[i] + second[i]) // 2 for i in range(3)) + (255,),
                    (0, 0, 0, 0),
                )
            for local_y in range(4):
                for local_x in range(4):
                    x = block_x + local_x
                    y = block_y + local_y
                    selector = selectors & 3
                    selectors >>= 2
                    if x >= width or y >= height:
                        continue
                    destination = (y * width + x) * 4
                    rgba[destination:destination + 4] = bytes(palette[selector])
    return bytes(rgba)


def _decode_dxt3(payload: bytes, width: int, height: int) -> bytes:
    expected = ((width + 3) // 4) * ((height + 3) // 4) * 16
    if len(payload) < expected:
        raise ValueError("BLP mip is shorter than its DXT3 dimensions")
    rgba = bytearray(width * height * 4)
    offset = 0
    for block_y in range(0, height, 4):
        for block_x in range(0, width, 4):
            alpha_bits = struct.unpack_from("<Q", payload, offset)[0]
            color0, color1, selectors = struct.unpack_from("<HHI", payload, offset + 8)
            offset += 16
            first = _rgb565(color0)
            second = _rgb565(color1)
            palette = (
                first,
                second,
                tuple((2 * first[i] + second[i]) // 3 for i in range(3)) + (255,),
                tuple((first[i] + 2 * second[i]) // 3 for i in range(3)) + (255,),
            )
            for local_y in range(4):
                for local_x in range(4):
                    x = block_x + local_x
                    y = block_y + local_y
                    selector = selectors & 3
                    selectors >>= 2
                    alpha = (alpha_bits & 15) * 17
                    alpha_bits >>= 4
                    if x >= width or y >= height:
                        continue
                    destination = (y * width + x) * 4
                    color = palette[selector]
                    rgba[destination:destination + 4] = bytes((*color[:3], alpha))
    return bytes(rgba)


def decode_blp2(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if len(data) < 148 or data[:4] != b"BLP2":
        raise ValueError(f"{path.name} is not a BLP2 texture")
    compression = struct.unpack_from("<I", data, 4)[0]
    encoding, alpha_depth, alpha_encoding, has_mips = struct.unpack_from("<BBBB", data, 8)
    width, height = struct.unpack_from("<II", data, 12)
    mip_offset = struct.unpack_from("<I", data, 20)[0]
    mip_size = struct.unpack_from("<I", data, 84)[0]
    if (compression, encoding) != (1, 2) or has_mips not in {0, 1}:
        raise ValueError(f"unsupported BLP2 encoding in {path.name}")
    end = mip_offset + mip_size
    if width <= 0 or height <= 0 or end > len(data):
        raise ValueError(f"invalid BLP2 mip envelope in {path.name}")
    if alpha_encoding == 0 and alpha_depth in {0, 1}:
        rgba = _decode_dxt1(data[mip_offset:end], width, height)
    elif alpha_encoding == 1 and alpha_depth == 8:
        rgba = _decode_dxt3(data[mip_offset:end], width, height)
    else:
        raise ValueError(f"unsupported BLP2 alpha encoding in {path.name}")
    return width, height, rgba


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload)) + kind + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA payload does not match PNG dimensions")
    scanlines = b"".join(
        b"\x00" + rgba[row * width * 4:(row + 1) * width * 4]
        for row in range(height)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        PNG_SIGNATURE + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(scanlines, 9)) + _chunk(b"IEND", b"")
    )


def _world_map_overlays(path: Path, *, map_area_id: int) -> tuple[tuple[str, int, int, int, int], ...]:
    payload = path.read_bytes()
    if len(payload) < 20 or payload[:4] != b"WDBC":
        raise ValueError("WorldMapOverlay.dbc has an invalid envelope")
    count, fields, record_size, string_size = struct.unpack_from("<4I", payload, 4)
    if fields != 17 or record_size != 68 or 20 + count * record_size + string_size != len(payload):
        raise ValueError("WorldMapOverlay.dbc does not match the TBC 2.4.3 layout")
    strings = payload[20 + count * record_size:]
    overlays = []
    for index in range(count):
        record = struct.unpack_from("<17I", payload, 20 + index * record_size)
        if record[1] != map_area_id:
            continue
        string_offset = record[8]
        if string_offset >= len(strings):
            raise ValueError("WorldMapOverlay.dbc contains an invalid string offset")
        name = strings[string_offset:].split(b"\x00", 1)[0].decode("ascii")
        width, height, offset_x, offset_y = record[9:13]
        overlays.append((name, width, height, offset_x, offset_y))
    if not overlays:
        raise ValueError("WorldMapOverlay.dbc has no overlays for the selected map")
    return tuple(overlays)


def _alpha_composite(
    destination: bytearray,
    destination_width: int,
    source: bytes,
    source_width: int,
    source_height: int,
    offset_x: int,
    offset_y: int,
) -> None:
    for source_y in range(source_height):
        for source_x in range(source_width):
            source_index = (source_y * source_width + source_x) * 4
            alpha = source[source_index + 3]
            if alpha == 0:
                continue
            destination_index = (
                (offset_y + source_y) * destination_width + offset_x + source_x
            ) * 4
            inverse = 255 - alpha
            for channel in range(3):
                destination[destination_index + channel] = (
                    source[source_index + channel] * alpha
                    + destination[destination_index + channel] * inverse
                ) // 255
            destination[destination_index + 3] = 255


def build_atlas(source: Path, destination: Path, overlay_dbc: Path | None = None) -> None:
    decoded = [decode_blp2(source / f"Tirisfal{index}.blp") for index in range(1, 13)]
    dimensions = {(width, height) for width, height, _ in decoded}
    if len(dimensions) != 1:
        raise ValueError("world map tiles do not share dimensions")
    tile_width, tile_height = next(iter(dimensions))
    atlas_width = tile_width * 4
    atlas_height = tile_height * 3
    atlas = bytearray(atlas_width * atlas_height * 4)
    for tile_index, (_, _, rgba) in enumerate(decoded):
        column = tile_index % 4
        row = tile_index // 4
        for tile_y in range(tile_height):
            source_start = tile_y * tile_width * 4
            destination_start = (
                (row * tile_height + tile_y) * atlas_width + column * tile_width
            ) * 4
            atlas[destination_start:destination_start + tile_width * 4] = rgba[
                source_start:source_start + tile_width * 4
            ]
    if overlay_dbc is not None:
        by_name = {path.name.lower(): path for path in source.glob("*.blp")}
        for name, width, height, offset_x, offset_y in _world_map_overlays(
            overlay_dbc, map_area_id=20
        ):
            columns = (width + 255) // 256
            rows = (height + 255) // 256
            for row in range(rows):
                for column in range(columns):
                    tile_index = row * columns + column + 1
                    tile_path = by_name.get(f"{name}{tile_index}.blp".lower())
                    if tile_path is None:
                        raise ValueError(f"missing exploration overlay: {name}{tile_index}.blp")
                    overlay_width, overlay_height, overlay = decode_blp2(tile_path)
                    _alpha_composite(
                        atlas, atlas_width, overlay, overlay_width, overlay_height,
                        offset_x + column * 256, offset_y + row * 256,
                    )
    visible = bytearray(TBC_WORLD_MAP_WIDTH * TBC_WORLD_MAP_HEIGHT * 4)
    for row in range(TBC_WORLD_MAP_HEIGHT):
        source_start = row * atlas_width * 4
        destination_start = row * TBC_WORLD_MAP_WIDTH * 4
        visible[destination_start:destination_start + TBC_WORLD_MAP_WIDTH * 4] = atlas[
            source_start:source_start + TBC_WORLD_MAP_WIDTH * 4
        ]
    write_png(
        destination, TBC_WORLD_MAP_WIDTH, TBC_WORLD_MAP_HEIGHT, bytes(visible)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert exact TBC 2.4.3 Tirisfal BLP tiles to one PNG atlas.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--overlay-dbc", type=Path)
    arguments = parser.parse_args()
    build_atlas(arguments.source, arguments.destination, arguments.overlay_dbc)
    print(arguments.destination.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
