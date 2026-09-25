# -*- coding: utf-8 -*-
"""8x8 셀(타일) 인터리브 4bpp 시트를 PNG로 내보낸다.

새턴 VDP는 4bpp 그래픽을 8x8 타일 단위로 저장한다. 선형 렌더에서
'빗살 무늬'가 나오면 타일 인터리브의 신호다.
"""
import sys
from dump_png import png_gray

TILE = 32   # 8x8 4bpp = 32 B


def sheet(data, off, tiles_w, tiles_h, scale=1):
    W, H = tiles_w * 8, tiles_h * 8
    px = [[0] * W for _ in range(H)]
    for t in range(tiles_w * tiles_h):
        ty, tx = divmod(t, tiles_w)
        base = off + t * TILE
        for y in range(8):
            for x in range(0, 8, 2):
                i = base + (y * 8 + x) // 2
                b = data[i] if i < len(data) else 0
                px[ty * 8 + y][tx * 8 + x] = (b >> 4) * 17
                px[ty * 8 + y][tx * 8 + x + 1] = (b & 15) * 17
    rows = []
    for r in px:
        line = bytearray(v for v in r for _ in range(scale))
        for _ in range(scale):
            rows.append(bytearray(line))
    return W * scale, H * scale, rows


if __name__ == '__main__':
    src, off, tw, th, out = (sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3]),
                             int(sys.argv[4]), sys.argv[5])
    scale = int(sys.argv[6]) if len(sys.argv) > 6 else 1
    d = open(src, 'rb').read()
    w, h, rows = sheet(d, off, tw, th, scale)
    png_gray(out, w, h, rows)
    print('wrote %s (%dx%d)' % (out, w, h))
