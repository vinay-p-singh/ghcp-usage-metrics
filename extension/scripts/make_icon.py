"""Generate media/icon.png (128x128) for the VS Code extension.

Stdlib-only PNG writer. Renders a mini bar-chart motif in the dashboard's
palette (dark #0d1117 background, blue #58a6ff bars) so the Marketplace icon
matches the product. Re-run after palette changes:  python scripts/make_icon.py
"""
import os
import struct
import zlib

SIZE = 128
BG = (13, 17, 23)        # #0d1117
BAR = (88, 166, 255)     # #58a6ff
BAR_DIM = (56, 105, 168)  # darker blue base

# (x_start_frac, width_frac, height_frac) for each bar, left->right
BARS = [
    (0.14, 0.14, 0.35),
    (0.32, 0.14, 0.60),
    (0.50, 0.14, 0.45),
    (0.68, 0.14, 0.80),
]
PAD_BOTTOM = 0.16  # baseline from the bottom


def _blend(base, top, a):
    return tuple(round(base[i] * (1 - a) + top[i] * a) for i in range(3))


def build_pixels():
    px = [[BG for _ in range(SIZE)] for _ in range(SIZE)]
    base_y = int(SIZE * (1 - PAD_BOTTOM))
    for xf, wf, hf in BARS:
        x0 = int(SIZE * xf)
        x1 = int(SIZE * (xf + wf))
        h = int(SIZE * hf)
        y0 = base_y - h
        for y in range(max(0, y0), base_y):
            # subtle vertical gradient from dim base to bright top
            t = (y - y0) / max(1, base_y - y0)
            col = _blend(BAR, BAR_DIM, t)
            for x in range(x0, x1):
                if 0 <= x < SIZE and 0 <= y < SIZE:
                    px[y][x] = col
    # baseline axis line
    for x in range(int(SIZE * 0.12), int(SIZE * 0.86)):
        if 0 <= base_y < SIZE:
            px[base_y][x] = BAR_DIM
    return px


def write_png(path, px):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = bytearray()
    for row in px:
        raw.append(0)  # filter type 0
        for r, g, b in row:
            raw += bytes((r, g, b))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(bytes(raw), 9)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "media", "icon.png")
    write_png(os.path.abspath(out), build_pixels())
    print(f"icon -> {os.path.abspath(out)}")
