# -*- coding: utf-8 -*-
"""VDP2 8bpp 셀(8x8, 64 B/타일)을 시트로 렌더한다.

4bpp로 읽으면 폭이 반으로 접혀 '세로 줄무늬'로 보인다. 그 증상이 나오면 8bpp를 의심한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_png import png_gray

TILE = 64   # 8x8 8bpp


def sheet(data, off, tiles_w, tiles_h, scale=1):
    W, H = tiles_w * 8, tiles_h * 8
    px = [[0] * W for _ in range(H)]
    for t in range(tiles_w * tiles_h):
        ty, tx = divmod(t, tiles_w)
        base = off + t * TILE
        for y in range(8):
            for x in range(8):
                i = base + y * 8 + x
                px[ty * 8 + y][tx * 8 + x] = data[i] if i < len(data) else 0
    rows = []
    for r in px:
        line = bytearray(v for v in r for _ in range(scale))
        for _ in range(scale):
            rows.append(bytearray(line))
    return W * scale, H * scale, rows


if __name__ == '__main__':
    a = sys.argv
    d = open(a[1], 'rb').read()
    w, h, rows = sheet(d, int(a[2], 0), int(a[3]), int(a[4]),
                       int(a[6]) if len(a) > 6 else 1)
    png_gray(a[5], w, h, rows)
    print('%s (%dx%d)' % (a[5], w, h))
