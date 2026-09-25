#!/usr/bin/env python3
"""mg_gfx.py — minimal Sega Saturn tile/bitmap -> PNG viewer for minigame assets.

No heavy deps (writes PNG by hand via zlib). Treats a blob as a grid of tiles
and emits a PNG so the agent can eyeball it for the UI font / logos.

Saturn graphics basics handled here:
  * 4bpp (16-color) and 8bpp (256-color) indexed pixels, packed linear (row-major
    within each tile). Saturn cell data is "linear within tile" for character
    patterns; we also support a raw bitmap mode (--bitmap, no tiling).
  * Palette: 256 (or 16) BGR555 little-endian or big-endian 16-bit entries.
    Saturn VDP stores BGR555 as 0bbbbbgggggrrrrr. Use --pal-be / --pal-le.

Usage:
  mg_gfx.py FILE OUT.png [opts]
    --bpp 4|8            (default 8)
    --tile N            tile size NxN (default 8; use 16 for 16x16)
    --cols N            tiles per row (default 32)
    --offset HEX        byte offset into FILE to start pixels (default 0)
    --count N           number of tiles to draw (default: all remaining)
    --pal FILE          palette file (BGR555). If omitted: grayscale ramp.
    --pal-offset HEX    byte offset into pal file (default 0)
    --pal-be            palette entries big-endian (default little-endian)
    --bitmap W H        raw bitmap WxH (no tiling); overrides tile/cols
    --zoom N            integer upscale (default 2)
"""
import struct
import sys
import zlib


def write_png(path, w, h, rgb):
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgb[y * w * 3:(y + 1) * w * 3]
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    open(path, "wb").write(png)


def bgr555(v):
    r = (v & 0x1F) << 3
    g = ((v >> 5) & 0x1F) << 3
    b = ((v >> 10) & 0x1F) << 3
    return (r | r >> 5, g | g >> 5, b | b >> 5)


def load_pal(path, off, be, n=256):
    data = open(path, "rb").read()[off:]
    pal = []
    fmt = ">H" if be else "<H"
    for i in range(n):
        if (i + 1) * 2 > len(data):
            pal.append((0, 0, 0))
            continue
        v = struct.unpack(fmt, data[i * 2:i * 2 + 2])[0]
        pal.append(bgr555(v))
    return pal


def gray_pal(n):
    if n <= 16:
        return [(i * 17, i * 17, i * 17) for i in range(16)]
    return [(i, i, i) for i in range(256)]


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("out")
    ap.add_argument("--bpp", type=int, default=8)
    ap.add_argument("--tile", type=int, default=8)
    ap.add_argument("--cols", type=int, default=32)
    ap.add_argument("--offset", default="0")
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--pal", default=None)
    ap.add_argument("--pal-offset", default="0")
    ap.add_argument("--pal-be", action="store_true")
    ap.add_argument("--bitmap", nargs=2, type=int, default=None)
    ap.add_argument("--zoom", type=int, default=2)
    a = ap.parse_args(argv)

    data = open(a.file, "rb").read()
    off = int(a.offset, 16) if a.offset.lower().startswith("0x") or any(c in a.offset.lower() for c in "abcdef") else int(a.offset, 16)
    data = data[off:]
    ncol = 16 if a.bpp == 4 else 256
    pal = load_pal(a.pal, int(a.pal_offset, 16), a.pal_be, ncol) if a.pal else gray_pal(ncol)

    def px_at(idx):
        if a.bpp == 8:
            return data[idx] if idx < len(data) else 0
        else:
            byte = data[idx // 2] if idx // 2 < len(data) else 0
            return (byte >> 4) if idx % 2 == 0 else (byte & 0xF)

    if a.bitmap:
        W, H = a.bitmap
        rgb = bytearray(W * H * 3)
        for y in range(H):
            for x in range(W):
                c = pal[px_at(y * W + x)]
                p = (y * W + x) * 3
                rgb[p:p + 3] = bytes(c)
        out_w, out_h = W, H
    else:
        T = a.tile
        tile_px = T * T
        total_px = len(data) * (1 if a.bpp == 8 else 2)
        ntiles = total_px // tile_px
        if a.count:
            ntiles = min(ntiles, a.count)
        cols = a.cols
        rows = (ntiles + cols - 1) // cols
        out_w, out_h = cols * T, rows * T
        rgb = bytearray(out_w * out_h * 3)
        for t in range(ntiles):
            tx = (t % cols) * T
            ty = (t // cols) * T
            base = t * tile_px
            for py in range(T):
                for px in range(T):
                    c = pal[px_at(base + py * T + px)]
                    X, Y = tx + px, ty + py
                    p = (Y * out_w + X) * 3
                    rgb[p:p + 3] = bytes(c)

    if a.zoom > 1:
        z = a.zoom
        zw, zh = out_w * z, out_h * z
        zrgb = bytearray(zw * zh * 3)
        for y in range(zh):
            sy = y // z
            for x in range(zw):
                sx = x // z
                sp = (sy * out_w + sx) * 3
                dp = (y * zw + x) * 3
                zrgb[dp:dp + 3] = rgb[sp:sp + 3]
        write_png(a.out, zw, zh, zrgb)
    else:
        write_png(a.out, out_w, out_h, rgb)
    print(f"wrote {a.out} ({out_w}x{out_h}, zoom {a.zoom})")


if __name__ == "__main__":
    main(sys.argv[1:])
