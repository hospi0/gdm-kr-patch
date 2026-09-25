# -*- coding: utf-8 -*-
"""시스템 메뉴 2차 빌드 — 세그먼트 인식 + 칸수 상한 + 공백 패딩 + 널경계 회귀검사."""
import os
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
import sysmenu2 as S2
import extract_sysmenu as E
import sysmenu_ko2 as K

SRC, DST = 'work/dm', 'work/build'


def null_bounds(d, lo, hi):
    out = []
    i = lo
    while i < hi:
        j = i
        while j < hi and d[j] != 0:
            j += 1
        out.append(i)
        i = j + 1
    return out


def main():
    total = skipped = 0
    for fname, lo, hi in E.REGIONS:
        src = open(os.path.join(SRC, fname), 'rb').read()
        base = os.path.join(DST, fname)
        d = bytearray(open(base if os.path.exists(base) else os.path.join(SRC, fname), 'rb').read())
        before = bytes(d)
        applied = []
        i = lo
        while i < hi:
            j = i
            while j < hi and src[j] != 0:
                j += 1
            raw = src[i:j]
            if not raw:
                i = j + 1
                continue
            segs = [B.decode(s) for k, s in S2.segments(raw) if k == 'full']
            if not segs or not any(t.strip() for t in segs):
                i = j + 1
                continue
            # 세그먼트별 후보 조합 (첫 후보부터 시도)
            cap = None
            if fname == K.TAB_GROUP[0] and K.TAB_GROUP[1] <= i < K.TAB_GROUP[2]:
                cap = max(K.TAB_GROUP[3], S2.cells(raw))
            cands = [K.SEG.get(t) for t in segs]
            if any(c is None for c in cands):
                print('  ? 번역없음 %s 0x%05X %s' % (fname[6:], i, segs))
                skipped += 1
                i = j + 1
                continue
            chosen = None
            for pickset in _combos(cands):
                ok, nb, why = S2.fit(raw, pickset, len(raw), cap)
                if ok:
                    chosen = (pickset, nb)
                    break
            if chosen is None:
                print('  X 못맞춤 %s 0x%05X %s (칸상한 %s)' % (fname[6:], i, segs, cap or S2.cells(raw)))
                skipped += 1
                i = j + 1
                continue
            d[i:i + len(raw)] = chosen[1]
            applied.append((i, segs, chosen[0]))
            i = j + 1

        newb = bytes(d)
        assert len(newb) == len(before)
        open(os.path.join(DST, fname), 'wb').write(newb)

        # ★회귀검사: 널 경계가 원본과 동일한가 (§21.9)
        ob = null_bounds(src, lo, hi)
        nb_ = null_bounds(newb, lo, hi)
        print('%-18s 반영 %2d  널경계 %s' % (fname[6:], len(applied),
                                          '일치 ✅' if ob == nb_ else '★불일치 ❌'))
        total += len(applied)
    print('\n합계 반영 %d, 미해결 %d' % (total, skipped))


def _combos(cands, i=0):
    if i == len(cands):
        yield []
        return
    for c in cands[i]:
        for rest in _combos(cands, i + 1):
            yield [c] + rest


if __name__ == '__main__':
    main()
