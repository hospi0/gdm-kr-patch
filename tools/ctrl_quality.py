# -*- coding: utf-8 -*-
"""제어코드 길이를 **추출문 품질**로 판정한다.

LL 제약(정확히 LL바이트 소비 + 07 종료)만으로는 대부분의 코드 길이가 갈리지 않는다.
길이가 틀리면 **인수 바이트를 글자로 먹거나 글자를 인수로 삼켜** 텍스트가 망가진다.

측정 지표 (낮을수록 좋음):
  나쁜시작 = 제어코드 직후 텍스트 런이 일본어에서 첫 글자가 될 수 없는 문자로 시작
             (요음·촉음 등 작은 가나, 장음 ー, 々, ？, ！)
  유령한자 = 스크립트 전체에서 딱 1번만 나오는 한자 코드 수
             (오파싱이 만들어내는 코드는 대개 1회성이다)
"""
import os
import sys
from collections import Counter

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section
from script_render import messages

CTRL = [b for b in range(0x20) if not (0x10 <= b <= 0x14)]
BAD_START = set('ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮー々？！‼⁉：・')


def blocks():
    out = []
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        out += [blk for p, blk in messages(d[o:o + b])]
    return out


def evaluate(blks, L, m):
    bad = 0
    codes = Counter()
    fail = 0
    for blk in blks:
        i, prev_ctrl = 0, True
        n = len(blk)
        okend = False
        while i < n:
            b = blk[i]
            if b >= 0x20:
                c = b - 0x20
                i += 1
            elif 0x10 <= b <= 0x14 and i + 1 < n:
                c = 0xE0 + (b - 0x10) * 256 + blk[i + 1]
                i += 2
            elif b == 0x07:
                okend = (i == n - 1)
                break
            else:
                i += L[b]
                prev_ctrl = True
                continue
            codes[c] += 1
            if prev_ctrl and m.get(c) in BAD_START:
                bad += 1
            prev_ctrl = False
        if not okend:
            fail += 1
    ghost = sum(1 for c, k in codes.items() if c >= 0xD8 and k == 1)
    return bad, ghost, len(codes), fail


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    blks = blocks()
    base = {b: 2 for b in CTRL}
    base[0x07] = 1
    base[0x0E] = 1
    base[0x01] = 1

    print('%-28s %-8s %-8s %-8s %s' % ('길이표', '나쁜시작', '유령한자', '글자종', '파싱실패'))

    def show(tag, L):
        bad, ghost, nc, fail = evaluate(blks, L, m)
        print('%-28s %-8d %-8d %-8d %d' % (tag, bad, ghost, nc, fail))
        return bad + ghost

    show('전부1B', {b: 1 for b in CTRL})
    show('전부2B(07,0E=1)', {**{b: 2 for b in CTRL}, 0x07: 1, 0x0E: 1})
    show('기준(01,07,0E=1)', base)
    print()
    print('== 애매한 코드를 하나씩 바꿔 본 결과 ==')
    b0, g0, _, _ = evaluate(blks, base, m)
    for b in sorted(CTRL):
        row = []
        for v in (1, 2, 3):
            if v == base[b]:
                row.append('%d:기준' % v)
                continue
            L = dict(base)
            L[b] = v
            bad, ghost, nc, fail = evaluate(blks, L, m)
            row.append('%d:%+d/%+d' % (v, bad - b0, ghost - g0))
        print('  %02X  %s' % (b, '  '.join(row)))


if __name__ == '__main__':
    main()
