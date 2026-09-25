# -*- coding: utf-8 -*-
"""8bpp 인덱스 버퍼를 «인덱스 그대로 색으로» 펼쳐 그린다(구조 확인용 대조표).

팔레트를 모를 때 쓴다. 인덱스 값마다 잘 갈라지는 색을 주므로
글자·배경·투명(0x00)이 한눈에 갈린다.

사용: python tools/sheet.py <bin> <out.png> <width> [시작 [길이]] [--scale N]
"""
import struct
import sys
import zlib


def palette():
    """0=검정(투명), 나머지는 값이 조금만 달라도 크게 벌어지는 색"""
    p = [(0, 0, 0)]
    for i in range(1, 256):
        r = (i * 97) & 0xFF
        g = (i * 57) & 0xFF
        b = (i * 149) & 0xFF
        p.append((64 + r // 2, 64 + g // 2, 64 + b // 2))
    return p


def write_png(path, rgb_rows, w, h):
    raw = b''.join(b'\x00' + r for r in rgb_rows)

    def ck(t, b):
        c = t + b
        return struct.pack('>I', len(b)) + c + struct.pack('>I', zlib.crc32(c))
    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + ck(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        + ck(b'IDAT', zlib.compress(raw, 9)) + ck(b'IEND', b''))


def render(data, w, scale=1, pal=None):
    pal = pal or palette()
    h = len(data) // w
    rows = []
    for y in range(h):
        r = bytearray()
        for x in range(w):
            r += bytes(pal[data[y * w + x]]) * scale
        for _ in range(scale):
            rows.append(bytes(r))
    return rows, w * scale, h * scale


def main():
    a = sys.argv[1:]
    scale = 1
    if '--scale' in a:
        i = a.index('--scale')
        scale = int(a[i + 1])
        del a[i:i + 2]
    src, out, w = a[0], a[1], int(a[2])
    start = int(a[3], 0) if len(a) > 3 else 0
    ln = int(a[4], 0) if len(a) > 4 else None
    d = open(src, 'rb').read()
    d = d[start:start + ln] if ln else d[start:]
    d = d[:len(d) // w * w]
    rows, W, H = render(d, w, scale)
    write_png(out, rows, W, H)
    print('%s  %d×%d  (0x%X부터 %d B)' % (out, W, H, start, len(d)))


if __name__ == '__main__':
    main()
