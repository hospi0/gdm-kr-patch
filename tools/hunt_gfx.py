# -*- coding: utf-8 -*-
"""압축 블록 안에서 «팔레트에 무관하게» 목표 그림을 찾는다.

## 왜 바이트 검색이 안 되나

몬스터 도감 화면의 예/아니오 상자는 설정자료집의 것과 **완전한 일대일 팔레트
사상**으로 이어진다(충돌 0/6144, `BC→7C` `C2→02` …). 같은 그림인데 저장된
인덱스 기준이 달라서 바이트가 5,444/6,144 다르다. 그래서 `bytes.find` 로는
절대 안 잡힌다.

## 대신 쓰는 지문

픽셀쌍의 **같다/다르다 관계**는 팔레트를 바꿔도 보존된다.
목표 그림에서 `같은 쌍` N개와 `다른 쌍` N개를 뽑아 두고, 후보 위치마다
그 관계가 모두 성립하는지만 본다. numpy 로 한 번에 돌리므로 블록당 수십 ms.

사용: python tools/hunt_gfx.py <목표bin…>      (결과는 work/hunt_gfx.log)
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, 'tools')
from find_sprites import blocks

LOG = 'work/hunt_gfx.log'
NPAIR = 48


def signature(t):
    """(같은 쌍, 다른 쌍) 인덱스 배열"""
    a = np.frombuffer(t, dtype=np.uint8)
    n = len(a)
    rs = np.random.RandomState(12345)
    same_i, same_j, diff_i, diff_j = [], [], [], []
    tries = 0
    while (len(same_i) < NPAIR or len(diff_i) < NPAIR) and tries < 200000:
        tries += 1
        i, j = rs.randint(0, n), rs.randint(0, n)
        if i == j:
            continue
        if a[i] == a[j]:
            if len(same_i) < NPAIR:
                same_i.append(i)
                same_j.append(j)
        else:
            if len(diff_i) < NPAIR:
                diff_i.append(i)
                diff_j.append(j)
    return (np.array(same_i), np.array(same_j),
            np.array(diff_i), np.array(diff_j), n)


def find(d, sig):
    si, sj, di, dj, n = sig
    a = np.frombuffer(d, dtype=np.uint8)
    m = len(a) - n
    if m <= 0:
        return []
    ok = np.ones(m, dtype=bool)
    for i, j in zip(si, sj):
        ok &= (a[i:i + m] == a[j:j + m])
        if not ok.any():
            return []
    for i, j in zip(di, dj):
        ok &= (a[i:i + m] != a[j:j + m])
        if not ok.any():
            return []
    return [int(o) for o in np.nonzero(ok)[0]]


def main():
    targets = []
    for p in sys.argv[1:]:
        t = open(p, 'rb').read()
        targets.append((os.path.basename(p), t, signature(t)))
    allf = [f for f in sorted(os.listdir('work/dm_all')) if not f.endswith('GM3.STZ')]

    def rank(f):
        return 3 if f.endswith('.BBG') else (2 if f.endswith(('.MDT', '.CPD', '.STB')) else 0)
    files = sorted(allf, key=lambda f: (rank(f), f))
    t0 = time.time()
    with open(LOG, 'w', encoding='utf-8') as lg:
        def say(s):
            lg.write(s + '\n')
            lg.flush()
        say('목표: %s' % ', '.join('%s(%dB)' % (n, len(t)) for n, t, _ in targets))
        for k, fn in enumerate(files):
            buf = open('work/dm_all/' + fn, 'rb').read()
            try:
                bs = blocks(buf)
            except Exception as e:
                say('  !! %s %s' % (fn, e))
                continue
            for off, d, mode, lut, rl in bs:
                for nm, t, sig in targets:
                    for o in find(d, sig):
                        say('★★ %s 블록0x%06X(%dB %s RLE=%d 표=%s) 안 0x%X 에 %s'
                            % (fn, off, len(d), mode, rl, lut.hex(), o, nm))
            say('[%3d/%d] %-22s 블록 %-3d  %.0fs' % (k + 1, len(files), fn, len(bs), time.time() - t0))
        say('완료')


if __name__ == '__main__':
    main()
