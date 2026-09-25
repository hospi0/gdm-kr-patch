# -*- coding: utf-8 -*-
"""박물관 번역 예산·인코딩 검사 (빌드 전 필수).

🔑 `bintext.encode()` 는 `ko=kocodes` 를 안 넘기면 한글 인코딩 자체가 실패한다.
   번역 전에 반드시 인코딩부터 검증할 것 — 세션7에 이걸로 1,260건을 날렸다.
"""
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
from museum import SPECS, bounds, strings, cells
from runs_build import load_maps

_, KOCODES = load_maps()


def enc(t):
    return B.encode_with_vars(t, KOCODES)


def missing_syllables(texts):
    bad = {}
    for t in texts:
        for ch in t:
            if '가' <= ch <= '힣' and ch not in KOCODES:
                bad.setdefault(ch, 0)
                bad[ch] += 1
    return bad


def main():
    import museum_ko
    import museum_desc_ko
    KO = dict(museum_ko.KO)
    for k, v in museum_desc_ko.KO.items():
        KO.setdefault(k, [v] if isinstance(v, str) else v)
    allko = [c for v in KO.values() for c in v]
    miss = missing_syllables(allko)
    if miss:
        print('★인코딩 불가 음절 %d종: %s' % (len(miss), ' '.join(sorted(miss))))
    else:
        print('인코딩 검증: 전 음절 사용 가능 ✅')

    print()
    grand_over = 0
    for fn, spec in SPECS.items():
        d = open('work/dm/' + fn, 'rb').read()
        for name, lo, hi in bounds(d, spec):
            ss = strings(d, lo, hi)
            need = 0
            untr = []
            over = []
            for o, l, t in ss:
                if l == 0:
                    need += 1
                    continue
                cand = KO.get(t.rstrip('　 '))
                if not cand:
                    untr.append((o, l, t))
                    need += l + 1
                    continue
                try:
                    e = enc(cand[0])
                except KeyError as ex:
                    over.append((t, '인코딩불가 %s' % ex))
                    need += l + 1
                    continue
                need += len(e) + 1
                if cells(e) > cells(d[o:o + l]):
                    over.append((t, '칸초과 %.1f>%.1f' % (cells(e), cells(d[o:o + l]))))
            room = hi - lo
            mark = '✅' if need <= room else '★초과 %+d' % (need - room)
            if need > room:
                grand_over += need - room
            print('%-16s %-10s 예산 %5d  필요 %5d  %s  미번역 %d' %
                  (fn[6:], name, room, need, mark, len(untr)))
            for o, l, t in untr[:8]:
                print('      미번역 0x%05X len=%2d %r' % (o, l, t))
            for t, why in over[:8]:
                print('      %s  <- %r' % (why, t))
    print('\n총 초과 %d B' % grand_over)


if __name__ == '__main__':
    main()
