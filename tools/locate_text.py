# -*- coding: utf-8 -*-
"""텍스트가 실제로 어느 섹션에 있는지 일본어 런 밀도로 찾는다.

`script_section()` 은 옛 `20 LL` 규칙으로 섹션을 골랐다. 런 단위 제자리 교체로
가려면 그 전제를 버리고 **텍스트가 실제로 있는 구간**을 직접 재야 한다.
섹션은 서로 겹치기도 하므로(헤더에 뷰가 섞여 있다) 겹침 정리도 한다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import sections

m = codemap.base_map()
m.update(kanji_map())
KANA = set(codemap.HIRA + codemap.KATA)
JPP = set('‥…。、・「」『』！？⁉‼～ー♪♥○※（）　 ')


def is_jp(ch):
    return ch in KANA or 0x4E00 <= ord(ch) <= 0x9FFF or ch in JPP


def jp_runs(s, minlen=6, minratio=0.8):
    """길이 minlen 이상, 일본어 비율 minratio 이상인 런 개수와 총 글자수"""
    n = cnt = chars = 0
    cur = []
    for x in s:
        ch = m.get(x - 0x20) if x >= 0x20 else None
        if ch is not None and is_jp(ch):
            cur.append(ch)
        else:
            if len(cur) >= minlen:
                t = ''.join(cur)
                if sum(1 for c in t if is_jp(c)) / len(t) >= minratio:
                    cnt += 1
                    chars += len(t)
            cur = []
    if len(cur) >= minlen:
        t = ''.join(cur)
        if sum(1 for c in t if is_jp(c)) / len(t) >= minratio:
            cnt += 1
            chars += len(t)
    return cnt, chars


def main():
    grand_r = grand_c = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        rows = []
        for so, sb in sections(d):
            if so + sb > len(d):
                continue
            c, ch = jp_runs(d[so:so + sb])
            if c:
                rows.append((so, sb, c, ch))
        rows.sort(key=lambda r: -r[3])
        tr = sum(r[2] for r in rows)
        tc = sum(r[3] for r in rows)
        grand_r += tr
        grand_c += tc
        print('%-14s 텍스트 있는 섹션 %d개  런 %4d  글자 %6d'
              % (f[6:], len(rows), tr, tc))
        for so, sb, c, ch in rows[:3]:
            print('     +0x%06X %7dB  런 %4d 글자 %6d' % (so, sb, c, ch))
    print('-' * 60)
    print('합계 런 %d개, 글자 %d자 (섹션 겹침 포함 — 중복 있음)' % (grand_r, grand_c))


if __name__ == '__main__':
    main()
