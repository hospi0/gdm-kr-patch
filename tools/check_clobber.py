# -*- coding: utf-8 -*-
"""한글 슬롯 배정이 **번역문에 그대로 남는 글자**를 덮어쓰지 않는지 검사한다.

번역문(ko)에는 원문에서 그대로 가져온 기호가 남는다 — 『』「」・‥※♥♪ 등.
그 글자의 코드가 한글로 재배정되면 화면에 엉뚱한 한글이 나온다.
(실제로 「」(0x198/0x199)를 덮어써서 「설정 자료집」이 깨졌다.)
"""
import csv
import re
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    rev = {}
    for c, ch in sorted(m.items()):
        rev.setdefault(ch, c)

    ko_map = {}
    for line in open('work/trans/kocodes.tsv', encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            ko_map[int(a, 16)] = b

    rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'),
                               delimiter='\t'))
    used = set()
    for r in rows:
        if not r['ko']:
            continue
        for s in TOKRE.split(r['ko']):
            if not s or TOKRE.fullmatch(s):
                continue
            used.update(s)

    # 번역문에 쓰이는 글자 중, 원본 폰트 코드를 가진 것(= 한글이 아닌 기존 글자)
    keep = {ch: rev[ch] for ch in used if ch in rev and not (0xAC00 <= ord(ch) <= 0xD7A3)}
    clob = {ch: c for ch, c in keep.items() if c in ko_map}
    print('번역문이 쓰는 기존 글자 %d종' % len(keep))
    if clob:
        print('★ 한글로 덮여버린 글자 %d종:' % len(clob))
        for ch, c in sorted(clob.items(), key=lambda kv: kv[1]):
            print('   %r 코드 0x%03X → 지금 %r 로 배정됨' % (ch, c, ko_map[c]))
    else:
        print('덮어쓴 글자 없음 — 안전')
    return clob


if __name__ == '__main__':
    main()
