# -*- coding: utf-8 -*-
"""전 섹션 × 완화 조건으로 잡힌 메시지 후보를 **텍스트로 렌더해** 진짜인지 가린다.

판정: 글자 런에 일본어(가나·한자)가 충분히 들어 있고 길이가 그럴듯하면 진짜.
현재 추출된 282개와 겹치지 않는 것만 낸다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section, sections
from script_parse import CTRL, TEXT, parse
from scan_all_msgs import scan

m = codemap.base_map()
m.update(kanji_map())

KANA = set(codemap.HIRA + codemap.KATA)


def text_of(blk):
    return ''.join(m.get(v, '?') for t, v in parse(blk) if t == TEXT)


def plausible(s):
    if len(s) < 4:
        return False
    k = sum(1 for c in s if c in KANA or 0x4E00 <= ord(c) <= 0x9FFF)
    return k >= max(3, len(s) * 0.4)


def main():
    known = set()
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        for p, blk in scan(d[o:o + b], strict=True):
            known.add((f, o + p))

    # ★ 진짜만 추린다: **현재 쓰는 스크립트 섹션 안**에서 완화 조건으로 추가되는 것.
    #   다른(대개 아주 큰) 섹션에서 잡히는 건 `20 LL … 07` 우연일치 노이즈다
    #   — 렌더해 보면 무작위 문자열이다.
    n = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        for p, blk in scan(d[o:o + b], strict=False):
            if (f, o + p) in known:
                continue
            t = text_of(blk)
            n += 1
            print('%-14s +0x%04X (%3dB) %s' % (f[6:], p, len(blk), t[:90]))
    print('-' * 60)
    print('놓친 메시지 %d개' % n)


if __name__ == '__main__':
    main()
