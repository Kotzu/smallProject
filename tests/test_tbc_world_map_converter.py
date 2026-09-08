from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from scripts.convert_tbc_world_map import _decode_dxt1, _decode_dxt3, write_png


class TbcWorldMapConverterTests(unittest.TestCase):
    def test_dxt1_decodes_four_color_block(self) -> None:
        block = struct.pack("<HHI", 0xF800, 0x001F, 0b11_10_01_00)
        rgba = _decode_dxt1(block, 4, 4)
        self.assertEqual(rgba[0:4], bytes((255, 0, 0, 255)))
        self.assertEqual(rgba[4:8], bytes((0, 0, 255, 255)))
        self.assertEqual(rgba[8:12], bytes((170, 0, 85, 255)))
        self.assertEqual(rgba[12:16], bytes((85, 0, 170, 255)))

    def test_png_writer_emits_valid_rgba_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.png"
            write_png(destination, 1, 1, bytes((1, 2, 3, 255)))
            payload = destination.read_bytes()
            self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
            idat_start = payload.index(b"IDAT")
            idat_size = struct.unpack(">I", payload[idat_start - 4:idat_start])[0]
            decompressed = zlib.decompress(payload[idat_start + 4:idat_start + 4 + idat_size])
            self.assertEqual(decompressed, bytes((0, 1, 2, 3, 255)))

    def test_dxt3_decodes_explicit_alpha(self) -> None:
        alpha = sum(index << (index * 4) for index in range(16))
        block = struct.pack("<QHHI", alpha, 0xF800, 0x001F, 0)
        rgba = _decode_dxt3(block, 4, 4)
        self.assertEqual(rgba[0:4], bytes((255, 0, 0, 0)))
        self.assertEqual(rgba[-4:], bytes((255, 0, 0, 255)))


if __name__ == "__main__":
    unittest.main()
