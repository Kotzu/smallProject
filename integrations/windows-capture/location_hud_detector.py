"""Read 96 RGB-nibble cells, without OCR or modifying coordinate markers."""

from perfect_assassin.adapter.location_hud import decode_location_packet


def detect_location_strip(frame, markers, expected_sequence):
    if markers is None:
        return None
    cyan, magenta, yellow, _ = markers
    sx, sy = (magenta[0] - cyan[0]) / 92.0, (yellow[1] - cyan[1]) / 34.0
    if not 0.5 <= sx <= 4 or abs(sx - sy) > 0.1:
        return None
    nibbles = []
    for index in range(96):
        x = round(cyan[0] + (6 + index % 48 * 3) * sx)
        y = round(cyan[1] + (-8 + index // 48 * 3) * sy)
        if not 0 <= y < frame.shape[0] or not 0 <= x < frame.shape[1]:
            return None
        for value in frame[y, x, :3][::-1]:  # BGRA -> RGB
            nibble = round((int(value) - 8) / 16)
            if not 0 <= nibble <= 15 or abs(int(value) - (8 + 16 * nibble)) > 5:
                return None
            nibbles.append(nibble)
    raw = bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, 288, 2))
    try:
        packet = decode_location_packet(raw)
    except ValueError:
        return None
    return packet if packet.sequence == expected_sequence else None
