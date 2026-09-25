# -*- coding: utf-8 -*-
"""대사만 다른 두 세이브스테이트의 메모리를 차분해 '글자 픽셀'을 격리한다.

배경·UI는 그대로이고 글자만 바뀌므로, 바뀐 구간 = 글리프가 그려진 자리다.
이것으로 폰트의 셀 크기·비트depth·상주 위치를 추측 없이 확정한다.
"""
import os
import sys


def runs(a, b, gap=16, minlen=8):
    n = min(len(a), len(b))
    raw = []
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            raw.append((i, j))
            i = j
        else:
            i += 1
    out = []
    for s, e in raw:
        if out and s - out[-1][1] <= gap:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return [(s, e) for s, e in out if e - s >= minlen]


def main():
    for name in ('VRAM', 'VRAM_1', 'WorkRAMH', 'WorkRAML'):
        pa = 'work/state_a/%s.bin' % name
        pb = 'work/state_b/%s.bin' % name
        if not (os.path.exists(pa) and os.path.exists(pb)):
            continue
        a = open(pa, 'rb').read()
        b = open(pb, 'rb').read()
        rs = runs(a, b)
        tot = sum(e - s for s, e in rs)
        print('== %-9s 변경 구간 %d개, 합계 %d B' % (name, len(rs), tot))
        for s, e in rs[:24]:
            print('   0x%06X-0x%06X  %5d B' % (s, e, e - s))
        if len(rs) > 24:
            print('   … 외 %d개' % (len(rs) - 24))
        print()


if __name__ == '__main__':
    main()
