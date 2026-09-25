# -*- coding: utf-8 -*-
"""임의 메모리 구간을 4bpp 8x16 셀 격자로 렌더한다.

목적: 0x06020070의 4bpp 셀이 '한 줄짜리 스테이징 버퍼'인지
      '폰트 전체가 4bpp로 상주하는 글리프 캐시'인지 가른다.

사용: python tools/render_cells.py <bin> <시작오프셋hex> <길이hex> <출력png> [열수]
"""
import struct
import sys
import zlib


def png(path, w, h, rows):
    """rows = [bytearray(w)] 그레이 8bit"""
    raw = b''.join(b'\x00' + bytes(r) for r in rows)

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)

    hdr = struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', hdr)
                           + chunk(b'IDAT', zlib.compress(raw, 9))
                           + chunk(b'IEND', b''))


def main():
    src, start, ln, out = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16), sys.argv[4]
    cols = int(sys.argv[5]) if len(sys.argv) > 5 else 32
    d = open(src, 'rb').read()[start:start + ln]
    CW, CH, CB = 8, 16, 64            # 8px x 16행 4bpp = 64 B
    ncell = len(d) // CB
    rowsn = (ncell + cols - 1) // cols
    W, H = cols * (CW + 1), rowsn * (CH + 1)
    img = [bytearray([40] * W) for _ in range(H)]
    for c in range(ncell):
        cx, cy = (c % cols) * (CW + 1), (c // cols) * (CH + 1)
        for y in range(CH):
            for x in range(CW):
                b = d[c * CB + (y * CW + x) // 2]
                v = (b >> 4) if x % 2 == 0 else (b & 15)
                img[cy + y][cx + x] = v * 17
    png(out, W, H, img)
    print('%s  셀 %d개  %dx%d' % (out, ncell, W, H))


if __name__ == '__main__':
    main()
