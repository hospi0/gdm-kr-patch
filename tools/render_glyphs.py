# -*- coding: utf-8 -*-
"""1bpp 글리프 배열을 격자로 배치해 PNG로 낸다(글자인지 눈으로 확인용)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_png import png_gray


def render(data, off, gw, gh, cols, rows_n, out, scale=2, gap=1):
    stride = (gw + 7) // 8
    cell = stride * gh
    W = cols * (gw + gap)
    H = rows_n * (gh + gap)
    img = [bytearray(W) for _ in range(H)]
    for g in range(cols * rows_n):
        gy, gx = divmod(g, cols)
        base = off + g * cell
        for y in range(gh):
            for xb in range(stride):
                i = base + y * stride + xb
                b = data[i] if i < len(data) else 0
                for k in range(8):
                    x = xb * 8 + k
                    if x < gw:
                        img[gy * (gh + gap) + y][gx * (gw + gap) + x] = \
                            255 if (b >> (7 - k)) & 1 else 0
    big = []
    for r in img:
        line = bytearray(v for v in r for _ in range(scale))
        for _ in range(scale):
            big.append(bytearray(line))
    png_gray(out, W * scale, H * scale, big)
    print('%s  off=0x%X %dx%d %dx%d칸' % (out, off, gw, gh, cols, rows_n))


if __name__ == '__main__':
    a = sys.argv
    d = open(a[1], 'rb').read()
    render(d, int(a[2], 0), int(a[3]), int(a[4]), int(a[5]), int(a[6]), a[7],
           int(a[8]) if len(a) > 8 else 2)
