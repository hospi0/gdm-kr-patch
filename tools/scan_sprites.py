# -*- coding: utf-8 -*-
"""파일 안에서 «Grandia 압축 스프라이트 블록»을 전수 탐색한다.

판별은 헤더 추측이 아니라 **테이블 생성 성공 여부**로 한다 —
9바이트 압축 테이블이 정확히 256엔트리로 전개돼야 하므로 오탐이 거의 없다
([[reference_custom_codec_playbook]] 의 「오라클을 먼저 만든다」).

사용:  python tools/scan_sprites.py <파일…> [--find <hex패턴파일>]
"""
import os
import struct
import sys

sys.path.insert(0, 'tools')
import gsprite as G


def scan(buf, step=2, minlen=256):
    """(오프셋, 길이, 모드, 표) 목록"""
    out = []
    n = len(buf)
    for off in range(0, n - 16, step):
        head = struct.unpack_from('>H', buf, off)[0]
        if (head >> 14) == 0b11:
            continue
        t = head & 0x1FFF
        if t < 2 or off + t + 11 > n:
            continue
        if G.generate_lut(buf[off + t + 2:off + t + 11]) is None:
            continue
        try:
            d, mode, lut, rl = G.decompress(buf, off)
        except Exception:
            continue
        if len(d) >= minlen:
            out.append((off, len(d), mode, lut.hex(), rl, d))
    return out


def main():
    argv = sys.argv[1:]
    find = None
    if '--find' in argv:
        i = argv.index('--find')
        find = open(argv[i + 1], 'rb').read()
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith('--')]
    for p in args:
        buf = open(p, 'rb').read()
        hits = scan(buf)
        print('%-24s %d블록' % (os.path.basename(p), len(hits)))
        for off, L, mode, lut, rl, d in hits:
            tag = ''
            if find and find in d:
                tag = '  ★찾는 패턴 포함 @0x%X' % d.find(find)
            print('   0x%06X → %6dB %s RLE=%d 표=%s%s' % (off, L, mode, rl, lut, tag))


if __name__ == '__main__':
    main()
