"""Read the optional six-byte strip relative to verified coordinate HUD markers."""

from __future__ import annotations

from perfect_assassin.adapter.afk_hud import decode_afk_packet


def detect_afk_strip(frame, markers):
    if markers is None:
        return None
    cyan, magenta, yellow, _ = markers
    scale_x = (magenta[0] - cyan[0]) / 92.0
    scale_y = (yellow[1] - cyan[1]) / 34.0
    if not 0.5 <= scale_x <= 4 or abs(scale_x - scale_y) > 0.1:
        return None
    raw = bytearray(6)
    for index in range(48):
        # Lua: 2x2 cells at (14 + i*3, 22); cyan marker centre (9,35).
        x = round(cyan[0] + (6 + index * 3) * scale_x)
        y = round(cyan[1] - 12 * scale_y)
        if not 0 <= y < frame.shape[0] or not 0 <= x < frame.shape[1]:
            return None
        value = float(frame[y, x, :3].mean())
        if 80 < value < 175:
            return None
        raw[index // 8] |= int(value >= 175) << (7 - index % 8)
    try:
        return decode_afk_packet(bytes(raw))
    except ValueError:
        return None
