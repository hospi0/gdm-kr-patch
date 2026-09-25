# -*- coding: utf-8 -*-
"""한글 렌더 후보들을 한 장에 세로로 쌓아 비교한다. 맨 위는 원본 일본어 폰트."""
import struct
import sys
import zlib

sys.path.insert(0, 'tools')
import font_codec as C
from hangul_glyph import BOLD, FONT, render

TEXT = '검은고양이가담장위를조용히걸어간다무엇을찾고있었지왕국의비밀'
VARIANTS = [
    ('원본 일본어 폰트', None, None, None),
    ('명조 14 / 160', FONT, 14, 160),
    ('명조 14 / 128', FONT, 14, 128),
    ('명조Bold 14 / 160', BOLD, 14, 160),
    ('명조Bold 14 / 96', BOLD, 14, 96),
]


def jp_rows(d, n):
    """원본 폰트에서 대사에 쓰일 법한 글자 n개(한자 구간)"""
    out = []
    for code in range(0x200, 0x200 + n):
        out.append(C.raw_to_rows(C.glyph_full(d, code)))
    return out


def main():
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    n = len(TEXT)
    bands = []
    for name, font, size, thr in VARIANTS:
        if font is None:
            rows = jp_rows(d, n)
            note = ''
        else:
            rows = [render(ch, font, size, thr) for ch in TEXT]
            enc = [len(C.encode_record(C.rows_to_raw(r))) for r in rows]
            note = '  평균 %.1fB' % (sum(enc) / len(enc))
        bands.append((name + note, rows))

    cols = n
    W, H = cols * 17 + 4, len(bands) * 21
    img = [bytearray([32] * W) for _ in range(H)]
    for bi, (name, rows) in enumerate(bands):
        gy = bi * 21 + 3
        for k, r in enumerate(rows):
            gx = k * 17 + 2
            for y in range(16):
                for x in range(16):
                    img[gy + y][gx + x] = 255 if (r[y] >> (15 - x)) & 1 else 0
        print('%d행: %s' % (bi, name))

    def chunk(t, b):
        return (struct.pack('>I', len(b)) + t + b
                + struct.pack('>I', zlib.crc32(t + b) & 0xFFFFFFFF))

    raw = b''.join(b'\x00' + bytes(r) for r in img)
    open('work/hangul_compare.png', 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    print('work/hangul_compare.png  %dx%d' % (W, H))


if __name__ == '__main__':
    main()
