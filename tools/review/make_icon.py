"""Draws the Video Review icon (teal tile, play triangle, frame-corner marks) as icon.ico + ui/icon.svg.

Stdlib only: rasterised with 4x supersampling, stored as PNG frames inside the .ico. Re-run after changing it.
"""
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAL, WHITE = (0, 180, 180), (255, 255, 255)
SIZES = [16, 24, 32, 48, 64, 256]


def inside(x: float, y: float) -> tuple | None:
    """Colour at a point in the 0..1 unit square (None = transparent)."""
    r = 0.22  # corner radius of the tile
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return None
    # Play triangle.
    ax, ay, bx, by, px = 0.40, 0.30, 0.40, 0.70, 0.70
    if x >= ax and abs(y - 0.5) <= (px - x) / (px - ax) * (by - ay) / 2:
        return WHITE
    # Corner brackets (frame marks).
    t, l, m = 0.045, 0.16, 0.17
    for ox, oy, sx, sy in [(m, m, 1, 1), (1 - m, m, -1, 1), (m, 1 - m, 1, -1), (1 - m, 1 - m, -1, -1)]:
        dx, dy = (x - ox) * sx, (y - oy) * sy
        if (0 <= dx <= l and 0 <= dy <= t) or (0 <= dy <= l and 0 <= dx <= t):
            return WHITE
    return TEAL


def render(size: int, ss: int = 4) -> bytes:
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc, hits = [0, 0, 0], 0
            for j in range(ss):
                for i in range(ss):
                    c = inside((px + (i + 0.5) / ss) / size, (py + (j + 0.5) / ss) / size)
                    if c:
                        hits += 1
                        acc = [a + v for a, v in zip(acc, c)]
            if hits:
                row += bytes([round(a / hits) for a in acc] + [round(255 * hits / ss / ss)])
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def write_ico(path: Path) -> None:
    pngs = [render(s) for s in SIZES]
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries = b""
    for s, png in zip(SIZES, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    path.write_bytes(head + entries + b"".join(pngs))


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect width="100" height="100" rx="22" fill="#00b4b4"/>
<path d="M40 30 L70 50 L40 70 Z" fill="#fff"/>
<g fill="#fff"><path d="M17 17h16v4.5H21.5V33H17z"/><path d="M83 17H67v4.5h11.5V33H83z"/>
<path d="M17 83h16v-4.5H21.5V67H17z"/><path d="M83 83H67v-4.5h11.5V67H83z"/></g>
</svg>
"""

if __name__ == "__main__":
    write_ico(HERE / "icon.ico")
    (HERE / "ui" / "icon.svg").write_text(SVG, encoding="utf-8")
    print("wrote icon.ico and ui/icon.svg")
