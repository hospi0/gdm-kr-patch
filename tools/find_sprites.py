# -*- coding: utf-8 -*-
"""전 파일에서 Grandia 압축 스프라이트 블록을 전수 수집한다 (numpy 고속판).

step=2 로 헤더를 하나씩 시험하면 수천만 회라 파이썬으로는 못 돈다.
그래서 **테이블부터 찾는다** — 9바이트 압축 테이블은 조건이 빡세서 오탐이 거의 없다:

  · 18니블 중 앞 17개가 값(비트수), 18번째는 0 패딩
  · 각 값 ≤ 8
  · Σ LUT_SEED[값] == 256  (전개 결과가 정확히 256엔트리)

테이블 위치 `P` 를 찾으면 헤더는 `off` 에 있고 `P == off + (head & 0x1FFF) + 2` 이므로
`off` 는 `[P-2-0x1FFF, P-2]` 안에서 역으로 확정된다.

사용: python tools/find_sprites.py [--find 패턴파일] [파일…]
      파일을 안 주면 work/dm_all 전부(GM3.STZ 제외).
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, 'tools')
import gsprite as G

SEED = np.array([0, 128, 64, 32, 16, 8, 4, 2, 1] + [999] * 7, dtype=np.int32)


def table_positions(buf):
    """유효 9바이트 테이블의 «바이트» 오프셋 목록"""
    a = np.frombuffer(buf, dtype=np.uint8)
    nib = np.empty(a.size * 2, dtype=np.uint8)
    nib[0::2] = a >> 4
    nib[1::2] = a & 0xF
    w = SEED[nib]                                  # 니블 → 전개 엔트리 수
    if w.size < 18:
        return []
    cs = np.concatenate(([0], np.cumsum(w, dtype=np.int64)))
    tot = cs[17:] - cs[:-17]                       # 17니블 창 합
    n = tot.size
    idx = np.arange(n)
    ok = (tot == 256) & (idx % 2 == 0)             # 바이트 정렬
    ok[:n - 1] &= (nib[17:17 + n - 1] == 0)        # 18번째 니블 = 0 패딩
    ok[n - 1] = False
    return (np.nonzero(ok)[0] // 2).tolist()


def blocks(buf, minlen=256):
    """★표 위치마다 8,190회 되짚으면 못 돈다. 모든 오프셋의 «함의 표위치»를
    numpy 로 한 번에 구해 유효표 집합과 대조한다(O(n))."""
    n = len(buf)
    tabs = set(table_positions(buf))
    if not tabs or n < 4:
        return []
    a = np.frombuffer(buf, dtype=np.uint8)
    head = (a[:-1].astype(np.int32) << 8) | a[1:]
    t = head & 0x1FFF
    cand = (head >> 14) != 0b11
    implied = np.arange(head.size, dtype=np.int64) + t + 2
    tarr = np.zeros(n + 4, dtype=bool)
    for P in tabs:
        tarr[P] = True
    ok = cand & (implied < n) & tarr[np.clip(implied, 0, n + 3)]
    out = []
    for off in np.nonzero(ok)[0]:
        try:
            d, mode, lut, rl = G.decompress(buf, int(off))
        except Exception:
            continue
        if len(d) >= minlen:
            out.append((int(off), d, mode, lut, rl))
    return out


def main():
    argv = sys.argv[1:]
    find = None
    if '--find' in argv:
        i = argv.index('--find')
        find = open(argv[i + 1], 'rb').read()
        del argv[i:i + 2]
    files = argv or [os.path.join('work/dm_all', f)
                     for f in sorted(os.listdir('work/dm_all'))
                     if not f.endswith('GM3.STZ')]
    tot = 0
    for p in files:
        buf = open(p, 'rb').read()
        bs = blocks(buf)
        if not bs:
            continue
        tot += len(bs)
        print('%-24s %d블록' % (os.path.basename(p), len(bs)))
        for off, d, mode, lut, rl in bs:
            tag = ''
            if find and find in d:
                tag = '  ★★찾는 패턴 @0x%X' % d.find(find)
            print('   0x%06X → %6dB %s RLE=%d 표=%s%s'
                  % (off, len(d), mode, rl, lut.hex(), tag))
    print('합계 %d블록' % tot)


if __name__ == '__main__':
    main()
