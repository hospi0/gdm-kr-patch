# -*- coding: utf-8 -*-
"""스테이징 버퍼(0x06020070 = 「！」 4bpp 2셀이 실제로 놓인 곳) 주소를
32비트 값으로 들고 있는 자리를 RAM·디스크 모듈에서 전부 찾는다.

캐시(0x060…)·비캐시(0x260…)·SH-2 DMA용(0x200…) 별칭을 모두 본다.
버퍼 시작이 0x06020070인지 그보다 앞(0x06020000·0x0602004x)인지 모르므로
0x06020000~0x060200FF 범위의 값이면 전부 보고한다.
"""
import os
import struct

RAMDIR = 'work/state_b'
DMDIR = 'work/dm'
LO, HI = 0x06020000, 0x060200FF
ALIASES = (0x06000000, 0x26000000, 0x20000000, 0x00000000)


def scan(d, name):
    out = []
    n = len(d) - 3
    for base in ALIASES:
        lo = LO - 0x06000000 + base
        hi = HI - 0x06000000 + base
        pat_hi = struct.pack('>H', lo >> 16)
        i = d.find(pat_hi)
        while i >= 0 and i < n:
            if i % 2 == 0:
                v = struct.unpack_from('>I', d, i)[0]
                if lo <= v <= hi:
                    out.append((i, v, name))
            i = d.find(pat_hi, i + 1)
    return out


def main():
    hits = []
    for dirn in (RAMDIR, DMDIR):
        if not os.path.isdir(dirn):
            continue
        for f in sorted(os.listdir(dirn)):
            p = os.path.join(dirn, f)
            if not os.path.isfile(p) or os.path.getsize(p) < 64:
                continue
            hits += scan(open(p, 'rb').read(), '%s/%s' % (dirn.split('/')[-1], f))
    for off, v, name in hits:
        print('%-34s +0x%06X = 0x%08X' % (name, off, v))
    print('총 %d건' % len(hits))


if __name__ == '__main__':
    main()
