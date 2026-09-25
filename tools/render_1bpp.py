# -*- coding: utf-8 -*-
"""1bpp 글리프 격자를 PNG로 렌더한다.

사용: python tools/render_1bpp.py <bin> <오프셋hex> <글자수> <폭px> <높이px> <출력> [열수]
"""
import struct
import sys
import zlib


def png(path, w, h, rows):
    raw = b''.join(b'\x00' + bytes(r) for r in rows)

    def chunk(t, d):
        return (struct.pack('>I', len(d)) + t + d
                + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF))

    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    src, off, n = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3])
    GW, GH = int(sys.argv[4]), int(sys.argv[5])
    out = sys.argv[6]
    cols = int(sys.argv[7]) if len(sys.argv) > 7 else 32
    W = (GW + 7) // 8
    S = W * GH
    d = open(src, 'rb').read()[off:off + n * S]
    n = min(n, len(d) // S)
    rowsn = (n + cols - 1) // cols
    IW, IH = cols * (GW + 1), rowsn * (GH + 1)
    img = [bytearray([48] * IW) for _ in range(IH)]
    for g in range(n):
        gx, gy = (g % cols) * (GW + 1), (g // cols) * (GH + 1)
        for y in range(GH):
            for x in range(GW):
                b = d[g * S + y * W + x // 8]
                img[gy + y][gx + x] = 255 if (b >> (7 - x % 8)) & 1 else 0
    png(out, IW, IH, img)
    print('%s  글자 %d개  %dx%d' % (out, n, IW, IH))


if __name__ == '__main__':
    main()
