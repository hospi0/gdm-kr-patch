# -*- coding: utf-8 -*-
"""GM3.IDX로 GM3.STZ의 369개 청크를 나누고, 각 청크의 머리를 훑어 종류를 분류한다.

GM3.IDX = [BE16 A][BE16 섹터오프셋] × 1024, FFFFFFFF 패딩.
섹터오프셋은 16비트라 한 번 랩한다(0~120885, STZ는 121184섹터).
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peek_lba import read

STZ_LBA, STZ_SIZE = 39128, 248184832
IDX = 'work/dm/FIELD_GM3.IDX'


def chunks():
    d = open(IDX, 'rb').read()
    recs = [struct.unpack_from('>HH', d, i * 4) for i in range(len(d) // 4)]
    valid = [r for r in recs if r != (0xFFFF, 0xFFFF)]
    off, w = [], 0
    for i, (_, v) in enumerate(valid):
        if i and v < valid[i - 1][1]:
            w += 1
        off.append(v + 65536 * w)
    end = STZ_SIZE // 2048
    out = []
    for i, o in enumerate(off):
        nxt = off[i + 1] if i + 1 < len(off) else end
        out.append((i, valid[i][0], o, nxt - o))
    return out


def main():
    print('%-4s %-6s %-8s %-7s %-9s %s' % ('#', 'A', '섹터', '섹터수', '크기', '머리 32B'))
    for i, a, o, n in chunks():
        d = read(STZ_LBA + o, 32)
        txt = ''.join(chr(b) if 32 <= b < 127 else '.' for b in d[:16])
        print('%-4d %04X   %-8d %-7d %-9d %s  %s'
              % (i, a, o, n, n * 2048, d[:16].hex(), txt))


if __name__ == '__main__':
    main()
