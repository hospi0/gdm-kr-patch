# -*- coding: utf-8 -*-
"""세이브스테이트(푼 것) 전체에서 글리프 시트를 찾는다.

세이브스테이트는 '화면에 글자가 떠 있는 순간의 RAM'이므로 폰트가 반드시 상주한다.
디스크 파일에서 못 찾은 폰트를 여기서 찾고, 그 바이트열을 다시 디스크에서
역추적하면 원본 위치가 나온다.

메모리 교훈: 세이브스테이트 RAM은 16비트 스왑돼 저장되기도 하므로 두 방향 모두 본다.
"""
import sys
import numpy as np

POP = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)


def swap16(b):
    a = np.frombuffer(b, dtype=np.uint8).copy()
    n = (len(a) // 2) * 2
    a[:n] = a[:n].reshape(-1, 2)[:, ::-1].reshape(-1)
    return a.tobytes()


def runs(data, cell, minrun=64, lo=0.10, hi=0.60, uniq_min=0.75):
    n = len(data) // cell
    if n < minrun:
        return []
    a = np.frombuffer(data[:n * cell], dtype=np.uint8).reshape(n, cell)
    dens = POP[a].sum(axis=1) / float(cell * 8)
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


def main(path):
    raw = open(path, 'rb').read()
    for tag, data in (('normal', raw), ('swap16', swap16(raw))):
        for label, cell in [('8x8 1bpp', 8), ('8x12 1bpp', 12), ('8x16 1bpp', 16),
                            ('12x12 1bpp', 24), ('16x16 1bpp', 32)]:
            rs = sorted(runs(data, cell), reverse=True)[:6]
            for cnt, off, u, dn in rs:
                print('%-7s %-11s 연속 %5d칸 off=0x%06X 고유율 %.2f 밀도 %.2f'
                      % (tag, label, cnt, off, u, dn))


if __name__ == '__main__':
    main(sys.argv[1])
