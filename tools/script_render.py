# -*- coding: utf-8 -*-
"""메시지 블록을 폰트 글리프로 렌더한다 (2바이트 이스케이프 가설 검증용).

가설: 스크립트 바이트 b
  b >= 0x20            → 폰트 코드 b - 0x20          (1바이트, 코드 0x00~0xDF)
  b in 0x10..0x14      → 다음 바이트 a와 함께 2바이트
                          폰트 코드 = 0xE0 + (b-0x10)*256 + a
  그 외 (< 0x10, 0x15~0x1F) → 제어코드

근거: 전각 슬롯 1504 = 224 + 5*256 으로 정확히 나뉜다.
검증: 렌더 결과가 말이 되는 일본어로 읽히면 가설이 맞다.
"""
import struct
import sys
import zlib

sys.path.insert(0, 'tools')
import font_codec as C

ESC_LO, ESC_HI = 0x10, 0x14


def parse(blk, esc=True):
    """블록 바이트열 → [('g', 코드) | ('c', 바이트)]"""
    out, i = [], 0
    while i < len(blk):
        b = blk[i]
        if b >= 0x20:
            out.append(('g', b - 0x20))
            i += 1
        elif esc and ESC_LO <= b <= ESC_HI and i + 1 < len(blk):
            out.append(('g', 0xE0 + (b - ESC_LO) * 256 + blk[i + 1]))
            i += 2
        else:
            out.append(('c', b))
            i += 1
    return out


def render(items, path, cols=40):
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    n = C.table_count(d, C.FULL_BASE)
    rn = (len(items) + cols - 1) // cols
    W, H = cols * 17, rn * 17
    img = [bytearray([40] * W) for _ in range(H)]
    for k, (t, v) in enumerate(items):
        gx, gy = (k % cols) * 17, (k // cols) * 17
        if t == 'c' or v >= n:
            for y in range(16):
                for x in range(16):
                    img[gy + y][gx + x] = 90 if (x + y) % 4 == 0 else 15
            continue
        rows = C.raw_to_rows(C.glyph_full(d, v))
        for y in range(16):
            for x in range(16):
                img[gy + y][gx + x] = 255 if (rows[y] >> (15 - x)) & 1 else 0

    def ch(t, b):
        return (struct.pack('>I', len(b)) + t + b
                + struct.pack('>I', zlib.crc32(t + b) & 0xFFFFFFFF))

    raw = b''.join(b'\x00' + bytes(r) for r in img)
    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + ch(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 0, 0, 0, 0))
        + ch(b'IDAT', zlib.compress(raw, 9)) + ch(b'IEND', b''))
    print('%s (%d칸)' % (path, len(items)))


def messages(s):
    ln = len(s)
    out, p = [], 0
    while p < ln - 4:
        if s[p] == 0x20 and p % 2 == 0:
            L = s[p + 1]
            if (L >= 6 and L % 2 == 0 and p + 2 + L <= ln
                    and s[p + 2] < 0x20 and s[p + 2 + L - 1] == 0x07):
                out.append((p, s[p + 2:p + 2 + L]))
                p += 2 + L
                continue
        p += 2
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'work/dm/FIELD_E800.MDT'
    off = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x1348
    ln = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x1D60
    esc = (len(sys.argv) <= 4) or sys.argv[4] != 'noesc'
    s = open(path, 'rb').read()[off:off + ln]
    msgs = messages(s)
    items = []
    for p, blk in msgs:
        items += parse(blk, esc)
        items += [('c', 0xFF)] * (len(items) % 40 and 40 - len(items) % 40 or 0)
    render(items, 'work/msgs_%s.png' % ('esc' if esc else 'noesc'))


if __name__ == '__main__':
    main()
