# -*- coding: utf-8 -*-
"""빌드된 폰트·스크립트 **바이트 그대로** 렌더해 실제 화면 모습을 미리 본다.

사용: python tools/preview_msgs.py <MDT파일명> <오프셋hex> [출력png]
"""
import struct
import sys
import zlib

sys.path.insert(0, 'tools')
import font_codec as C
from script_budget import script_section
from script_parse import CTRL, TEXT, parse

FD = 'work/build/BIN_FDATA.BIN'


def png(path, w, h, rows):
    def chunk(t, d):
        return (struct.pack('>I', len(d)) + t + d
                + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF))

    raw = b''.join(b'\x00' + bytes(r) for r in rows)
    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    name = sys.argv[1]
    off = int(sys.argv[2], 16)
    out = sys.argv[3] if len(sys.argv) > 3 else 'work/preview.png'
    Z = 3

    fd = open(FD, 'rb').read()
    d = open('work/build/FIELD_' + name, 'rb').read()
    o, ln, _ = script_section(d)
    s = d[o:o + ln]
    assert s[off] == 0x20, '메시지 시작이 아님'
    blk = s[off + 2:off + 2 + s[off + 1]]

    lines, cur = [], []
    for t, v in parse(blk):
        if t == TEXT:
            cur.append(v)
        elif v in (b'\x01', b'\x02', b'\x07'):
            lines.append(cur)
            cur = []
    lines.append(cur)
    lines = [l for l in lines if l]

    cols = max(len(l) for l in lines)
    W, H = cols * 17 * Z, len(lines) * 18 * Z
    img = [bytearray([25] * W) for _ in range(H)]
    for r, line in enumerate(lines):
        gy = r * 18 * Z
        for k, c in enumerate(line):
            rows = C.raw_to_rows(C.glyph_full(fd, c))
            gx = k * 17 * Z
            for y in range(16):
                for x in range(16):
                    val = 255 if (rows[y] >> (15 - x)) & 1 else 0
                    for yy in range(Z):
                        for xx in range(Z):
                            img[gy + y * Z + yy][gx + x * Z + xx] = val
    png(out, W, H, img)
    print('%s  (%d줄)' % (out, len(lines)))


if __name__ == '__main__':
    main()
