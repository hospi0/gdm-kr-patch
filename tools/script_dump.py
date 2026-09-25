# -*- coding: utf-8 -*-
"""대사 스크립트를 폰트 코드로 디코드해 보여준다.

규칙(실측): **스크립트 바이트 = 폰트 코드 + 0x20**
  → 0x20~0xFF 가 폰트 코드 0x00~0xDF (224자)
  → 0x00~0x1F 는 제어코드 자리

폰트 코드에 대응하는 '읽을 수 있는 글자'가 아직 없으므로,
코드 → 글리프를 그려서 PNG로 내보내고 동시에 코드열을 텍스트로 찍는다.
"""
import struct
import sys
import zlib

sys.path.insert(0, 'tools')
import font_codec as C

SHIFT = 0x20


def decode(buf, i, n):
    """바이트열 → [(종류, 값)] 종류 = 'c'(제어) / 'g'(글리프코드)"""
    out = []
    for b in buf[i:i + n]:
        if b < SHIFT:
            out.append(('c', b))
        else:
            out.append(('g', b - SHIFT))
    return out


def sheet(items, path, cols=48):
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    rn = (len(items) + cols - 1) // cols
    W, H = cols * 17, rn * 17
    img = [bytearray([48] * W) for _ in range(H)]
    for k, (t, v) in enumerate(items):
        gx, gy = (k % cols) * 17, (k // cols) * 17
        if t == 'c':
            for y in range(16):
                for x in range(16):
                    img[gy + y][gx + x] = 100 if (x + y) % 4 == 0 else 20
            continue
        try:
            rows = C.raw_to_rows(C.glyph_full(d, v))
        except Exception:
            continue
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
    print('%s (%d항목)' % (path, len(items)))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'work/state_b/WorkRAML_sw.bin'
    off = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x081400
    n = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x180
    buf = open(src, 'rb').read()
    items = decode(buf, off, n)
    # 코드열 텍스트
    line = []
    for t, v in items:
        line.append('<%02X>' % v if t == 'c' else '%02X' % v)
    print(' '.join(line))
    sheet(items, 'work/script_%X.png' % off)


if __name__ == '__main__':
    main()
