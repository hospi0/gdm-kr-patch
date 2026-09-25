# -*- coding: utf-8 -*-
"""제어코드별 인수 길이표를 자동으로 확정한다.

제약(강함):
  파싱이 메시지 블록 LL바이트를 **정확히** 소비하고, **마지막 토큰이 0x07**이며,
  0x07이 중간에 나오면 안 된다. (0x07은 282개 메시지에 281회 = 사실상 종결자 전용)

파싱 규칙:
  b >= 0x20        → 글자 1바이트
  0x10 <= b <= 0x14 → 2바이트 이스케이프(한자)
  그 외            → L[b] 바이트

L을 언덕오르기로 찾는다. 목표 = 통과한 메시지 수 최대.
"""
import os
import random
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from script_render import messages

CTRL = [b for b in range(0x20) if not (0x10 <= b <= 0x14)]
FIX = {0x07: 1}                      # 종결자는 1바이트로 고정


def blocks():
    out = []
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        out += [blk for p, blk in messages(d[o:o + b])]
    return out


def ok(blk, L):
    n = len(blk)
    i = 0
    while i < n:
        b = blk[i]
        if b >= 0x20:
            i += 1
        elif 0x10 <= b <= 0x14:
            i += 2
        elif b == 0x07:
            return i == n - 1        # 종결자는 마지막에만
        else:
            i += L[b]
    return False


def score(blks, L):
    return sum(1 for b in blks if ok(b, L))


def main():
    blks = blocks()
    print('메시지 %d개' % len(blks))
    best = {b: 2 for b in CTRL}
    best.update(FIX)
    bs = score(blks, best)
    print('초기(전부 2바이트) 통과 %d/%d' % (bs, len(blks)))

    rnd = random.Random(12345)
    for restart in range(40):
        cur = dict(best) if restart == 0 else \
            {b: (FIX[b] if b in FIX else rnd.choice([1, 2, 3, 4])) for b in CTRL}
        cur.update(FIX)
        cs = score(blks, cur)
        improved = True
        while improved:
            improved = False
            for b in CTRL:
                if b in FIX:
                    continue
                for v in (1, 2, 3, 4, 5):
                    if v == cur[b]:
                        continue
                    old = cur[b]
                    cur[b] = v
                    s = score(blks, cur)
                    if s > cs:
                        cs, improved = s, True
                    else:
                        cur[b] = old
        if cs > bs:
            bs, best = cs, dict(cur)
            print('  재시작 %2d → 통과 %d/%d' % (restart, bs, len(blks)), flush=True)
        if bs == len(blks):
            break

    print()
    print('최종 통과 %d/%d' % (bs, len(blks)))
    print('제어코드 길이표:')
    for b in sorted(best):
        print('  %02X : %d바이트' % (b, best[b]))
    fail = [i for i, blk in enumerate(blks) if not ok(blk, best)]
    print('실패 메시지 %d개' % len(fail))
    open('work/ctrl_len.tsv', 'w', encoding='utf-8').write(
        ''.join('%02X\t%d\n' % (b, best[b]) for b in sorted(best)))


if __name__ == '__main__':
    main()
