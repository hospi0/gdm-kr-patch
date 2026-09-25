# -*- coding: utf-8 -*-
"""4bpp 글리프 시트 탐색.

EDFNT.DAT(크레딧)가 4bpp였으므로 런타임 폰트도 4bpp일 수 있다.
4bpp에서는 'set bit 비율'이 아니라 **0이 아닌 니블의 비율**이 글자다움의 척도다.
(4bpp 글자는 보통 배경=0, 글자획=특정 색 인덱스)
"""
import sys
import numpy as np

# (설명, 폭, 높이) → 셀 바이트 = w*h/2
SHAPES = [('8x8', 8, 8), ('12x12', 12, 12), ('16x16', 16, 16),
          ('12x16', 12, 16), ('24x24', 24, 24), ('16x12', 16, 12)]


def scan(data, cell, minrun=48, lo=0.12, hi=0.65, uniq_min=0.8):
    n = len(data) // cell
    if n < minrun:
        return []
    a = np.frombuffer(data[:n * cell], dtype=np.uint8).reshape(n, cell)
    hi_nz = (a >> 4) != 0
    lo_nz = (a & 15) != 0
    dens = (hi_nz.sum(axis=1) + lo_nz.sum(axis=1)) / float(cell * 2)
    ok = (dens >= lo) & (dens <= hi)
    out = []
    i = 0
    while i < n:
        if ok[i]:
            j = i
            while j < n and ok[j]:
                j += 1
            if j - i >= minrun:
                blk = a[i:j]
                u = len(set(map(bytes, blk))) / float(j - i)
                if u >= uniq_min:
                    out.append((j - i, i * cell, u, float(dens[i:j].mean())))
            i = j
        else:
            i += 1
    return out


def main(paths):
    for p in paths:
        d = open(p, 'rb').read()
        for label, w, h in SHAPES:
            cell = w * h // 2
            rs = sorted(scan(d, cell), reverse=True)[:4]
            for cnt, off, u, dn in rs:
                print('%-28s %-6s(%3dB) 연속 %5d칸 off=0x%06X 고유율 %.2f 밀도 %.2f'
                      % (p.split('/')[-1], label, cell, cnt, off, u, dn))


if __name__ == '__main__':
    main(sys.argv[1:])
