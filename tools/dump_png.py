# -*- coding: utf-8 -*-
"""4bpp 선형 비트맵 구간을 PNG(그레이스케일)로 내보낸다. 외부 라이브러리 없음.

메모리 교훈 [[feedback_terra_verify_by_render_not_scan.md]]:
비트맵 판정은 스캔이 아니라 렌더로 한다.
"""
import struct
import zlib


def png_gray(path, w, h, rows):
    """rows: [bytearray(w)] 0-255 그레이"""
    raw = b''.join(b'\x00' + bytes(r) for r in rows)

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 9))
           + chunk(b'IEND', b''))
    open(path, 'wb').write(png)


def bitmap_4bpp(data, off, width_px, height, scale=1):
    stride = width_px // 2
    rows = []
    for y in range(height):
        line = bytearray()
        for x in range(stride):
            i = off + y * stride + x
            b = data[i] if i < len(data) else 0
            line.append((b >> 4) * 17)
            line.append((b & 15) * 17)
        for _ in range(scale):
            rows.append(bytearray(v for v in line for _ in range(scale)))
    return rows


if __name__ == '__main__':
    import sys
    src, off, w, h, out = (sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3]),
                           int(sys.argv[4]), sys.argv[5])
    scale = int(sys.argv[6]) if len(sys.argv) > 6 else 1
    d = open(src, 'rb').read()
    rows = bitmap_4bpp(d, off, w, h, scale)
    png_gray(out, w * scale, h * scale, rows)
    print('wrote %s (%dx%d)' % (out, w * scale, h * scale))
