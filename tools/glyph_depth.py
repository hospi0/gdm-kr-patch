# -*- coding: utf-8 -*-
"""블릿된 글자 셀이 실제로 몇 색을 쓰는지 센다.

2색(0/N)이면 원본은 1bpp이고 렌더러가 색을 입힌 것 → 1bpp 폰트를 찾아야 한다.
여러 값이 고르게 나오면 원본이 4bpp(안티앨리어스) 폰트다.
"""
import collections

VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, NCELL = 0x8000, 64, 32

d = open(VRAM, 'rb').read()
cnt = collections.Counter()
for c in range(NCELL):
    for b in d[BLIT + c * CB: BLIT + (c + 1) * CB]:
        cnt[b >> 4] += 1
        cnt[b & 15] += 1
tot = sum(cnt.values())
print('셀 %d개, 픽셀 %d개' % (NCELL, tot))
for v, n in sorted(cnt.items()):
    print('  값 %2d : %6d  (%5.2f%%)' % (v, n, 100.0 * n / tot))
print('사용된 값 %d종' % len(cnt))
