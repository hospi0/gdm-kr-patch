# -*- coding: utf-8 -*-
"""VDP1 프레임버퍼(RGB555 512x256)를 PNG로 낸다. 스테이트가 어떤 화면인지 확인용."""
import struct
import sys
import zlib


def png_rgb(path, w, h, rows):
    raw = b''.join(b'\x00' + bytes(r) for r in rows)

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b''))


def main(src, out, w=512, h=256, be=True):
    d = open(src, 'rb').read()
    rows = []
    fmt = '>H' if be else '<H'
    for y in range(h):
        line = bytearray()
        for x in range(w):
            i = (y * w + x) * 2
            v = struct.unpack_from(fmt, d, i)[0] if i + 2 <= len(d) else 0
            r = (v & 0x1F) << 3
            g = ((v >> 5) & 0x1F) << 3
            b = ((v >> 10) & 0x1F) << 3
            line += bytes((r, g, b))
        rows.append(line)
    png_rgb(out, w, h, rows)
    print('%s (%dx%d, %s)' % (out, w, h, 'BE' if be else 'LE'))


if __name__ == '__main__':
    a = sys.argv
    main(a[1], a[2], int(a[3]) if len(a) > 3 else 512,
         int(a[4]) if len(a) > 4 else 256,
         (a[5] != 'le') if len(a) > 5 else True)
