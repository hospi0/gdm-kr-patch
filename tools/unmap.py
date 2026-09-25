# -*- coding: utf-8 -*-
"""화면에 깨져 보이는 한글을 원문 일본어로 역추적한다.

가나 슬롯을 한글로 재배정했으므로, **추출되지 않은 일본어 텍스트**는
그 자리의 한글 글리프로 렌더된다. 역으로 매핑하면 원문을 알 수 있다.

사용: python tools/unmap.py "수어 였더 2혼시사"
"""
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    ko = {}
    for line in open('work/trans/kocodes.tsv', encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            ko[int(a, 16)] = b
    ko_rev = {}
    for c, ch in ko.items():
        ko_rev.setdefault(ch, c)

    s = sys.argv[1]
    out = []
    for ch in s:
        c = ko_rev.get(ch)
        if c is None:
            out.append(ch)                      # 원래부터 있던 글자(숫자·기호)
        else:
            out.append(m.get(c, '?'))           # 그 코드의 원래 일본어 글자
    print('화면: %s' % s)
    print('원문: %s' % ''.join(out))
    for ch in s:
        c = ko_rev.get(ch)
        if c is not None:
            print('  %r → 0x%03X → 원래 %r' % (ch, c, m.get(c)))


if __name__ == '__main__':
    main()
