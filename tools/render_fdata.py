# -*- coding: utf-8 -*-
"""FDATA.BIN의 BE16 오프셋표를 따라 글리프를 렌더한다.

가설: [BE16 오프셋 128개] + [가변 크기 1bpp 글리프].
행 바이트수(1 또는 2)를 바꿔가며 그려 사람이 글자인지 판정한다.
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_png import png_gray


def table(d, n=128):
    return [struct.unpack_from('>H', d, i * 2)[0] for i in range(n)]


def render(d, offs, bpr, cols, out, cellw=None, scale=3, gap=1):
    """bpr = 행당 바이트수. 글리프 높이는 (다음오프셋-현재)/bpr."""
    cellw = cellw or bpr * 8
    cellh = 24
    rows_n = (len(offs) - 1 + cols - 1) // cols
    W = cols * (cellw + gap)
    H = rows_n * (cellh + gap)
    img = [bytearray(W) for _ in range(H)]
    for g in range(len(offs) - 1):
        s, e = offs[g], offs[g + 1]
        h = (e - s) // bpr
        gy, gx = divmod(g, cols)
        for y in range(min(h, cellh)):
            for b in range(bpr):
                i = s + y * bpr + b
                if i >= len(d):
                    break
                v = d[i]
                for k in range(8):
                    x = b * 8 + k
                    if x < cellw:
                        img[gy * (cellh + gap) + y][gx * (cellw + gap) + x] = \
                            255 if (v >> (7 - k)) & 1 else 0
    big = []
    for r in img:
        line = bytearray(v for v in r for _ in range(scale))
        for _ in range(scale):
            big.append(bytearray(line))
    png_gray(out, W * scale, H * scale, big)
    print('%s bpr=%d %d글리프' % (out, bpr, len(offs) - 1))


if __name__ == '__main__':
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    offs = table(d)
    print('오프셋 0..7:', [hex(x) for x in offs[:8]])
    print('오프셋 120..127:', [hex(x) for x in offs[120:]])
    render(d, offs, 1, 16, 'work/fd_bpr1.png')
    render(d, offs, 2, 16, 'work/fd_bpr2.png')
