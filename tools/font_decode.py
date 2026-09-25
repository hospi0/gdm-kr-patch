# -*- coding: utf-8 -*-
"""GDM 폰트 디코더 — /BIN/FDATA.BIN (적재 0x00200000)

코덱은 `0x0601DC00`의 SH-2 루틴을 그대로 옮긴 것이다.

  베이스 = 폰트 시작 (전각 = FDATA+0xA00, 반각 = FDATA+0x000)
  오프셋 = BE16 @(베이스 + 코드*2)
  레코드 = [BE32 플래그워드][델타바이트 × popcount(플래그)]

  플래그워드는 MSB부터 32비트, 글리프 32바이트(16행 × 좌/우 8px)에 1비트씩 대응.
  비트가 1이면 델타를 하나 읽어 누산기에 XOR하고, 0이면 **이전 값 그대로**.
  누산기는 바이트 0과 16에서 0으로 리셋된다(= 좌열·우열 각각 세로 XOR 델타).

  바이트 0~15 = 왼쪽 8px 열의 16행, 16~31 = 오른쪽 8px 열의 16행.

이 세로 XOR 델타 때문에 평문 글리프 비트맵이 디스크·RAM 어디에도 없었다.
"""
import struct
import sys

FULL_BASE = 0xA00      # 전각 16x16
HALF_BASE = 0x000      # 반각 (코드 마스크 0xFFFE, 코드&1로 상/하 절반 선택)


def decode_glyph(d, base, code):
    """(왼쪽16바이트, 오른쪽16바이트) 또는 None"""
    p = base + code * 2
    if p + 2 > len(d):
        return None
    off = struct.unpack_from('>H', d, p)[0]
    rec = base + off
    if rec + 4 > len(d):
        return None
    flags = struct.unpack_from('>I', d, rec)[0]
    q = rec + 4
    acc, out = 0, []
    for i in range(32):
        if i % 16 == 0:
            acc = 0
        if flags & (0x80000000 >> i):
            if q >= len(d):
                return None
            acc ^= d[q]
            q += 1
        out.append(acc)
    return out[:16], out[16:]


def table_len(d, base):
    """첫 오프셋 = 표 크기(바이트) → 항목 수"""
    return struct.unpack_from('>H', d, base)[0] // 2


def render(d, base, codes, cols, path):
    import zlib
    GW, GH = 16, 16
    rowsn = (len(codes) + cols - 1) // cols
    W, H = cols * (GW + 1), rowsn * (GH + 1)
    img = [bytearray([48] * W) for _ in range(H)]
    for k, code in enumerate(codes):
        g = decode_glyph(d, base, code)
        if g is None:
            continue
        L, R = g
        gx, gy = (k % cols) * (GW + 1), (k // cols) * (GH + 1)
        for y in range(GH):
            for x in range(8):
                img[gy + y][gx + x] = 255 if (L[y] >> (7 - x)) & 1 else 0
                img[gy + y][gx + 8 + x] = 255 if (R[y] >> (7 - x)) & 1 else 0

    def chunk(t, b):
        return (struct.pack('>I', len(b)) + t + b
                + struct.pack('>I', zlib.crc32(t + b) & 0xFFFFFFFF))

    raw = b''.join(b'\x00' + bytes(r) for r in img)
    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    print('%s  %d글자  %dx%d' % (path, len(codes), W, H))


def main():
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    n = table_len(d, FULL_BASE)
    print('FDATA.BIN %d B' % len(d))
    print('전각 오프셋표 항목 %d개 (베이스 +0x%X)' % (n, FULL_BASE))
    first = struct.unpack_from('>H', d, FULL_BASE)[0]
    last = max(struct.unpack_from('>H', d, FULL_BASE + i * 2)[0] for i in range(n))
    print('  오프셋 범위 0x%X ~ 0x%X' % (first, last))
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cnt = int(sys.argv[2]) if len(sys.argv) > 2 else min(n, 256)
    render(d, FULL_BASE, range(start, min(start + cnt, n)), 32,
           'work/font_full_%d.png' % start)


if __name__ == '__main__':
    main()
