# -*- coding: utf-8 -*-
"""'런 단위 제자리 교체'로 갔을 때 번역이 실제로 얼마나 들어가는지 실측한다.

이미 번역한 282개 메시지의 ja/ko 쌍을 **런(제어코드 사이 텍스트 조각)** 단위로
잘라, 런마다 `한국어 바이트 <= 일본어 바이트` 를 만족하는지 센다.

한국어 바이트는 슬롯 배정(kocodes.tsv)을 그대로 쓴다:
  1바이트 슬롯에 있는 음절 = 1B, 나머지 = 2B(한자 영역 이스케이프).
"""
import csv
import re
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_build import PUNCT_FALLBACK

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def load_maps():
    m = codemap.base_map()
    m.update(kanji_map())
    rev = {}
    for c, ch in sorted(m.items()):
        rev.setdefault(ch, c)
    ko = {}
    for line in open('work/trans/kocodes.tsv', encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            ko[b] = int(a, 16)
    return rev, ko


def nbytes(s, rev, ko):
    """문자열이 스크립트에서 차지할 바이트 수"""
    n = 0
    for ch in s:
        c = ko.get(ch)
        if c is None:
            c = rev.get(ch)
        if c is None and ch in PUNCT_FALLBACK:
            t = PUNCT_FALLBACK[ch]
            c = ko.get(t, rev.get(t))
        if c is None:
            return None                  # 인코딩 불가
        n += 1 if c < 0xE0 else 2
    return n


def runs(s):
    return [p for p in TOKRE.split(s) if p and not TOKRE.fullmatch(p)]


def main():
    rev, ko = load_maps()
    rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'),
                               delimiter='\t'))
    tot = fit = 0
    over = []
    ja_b = ko_b = 0
    for r in rows:
        if not r['ko']:
            continue
        a, b = runs(r['ja']), runs(r['ko'])
        if len(a) != len(b):
            continue
        for x, y in zip(a, b):
            na, nb = nbytes(x, rev, ko), nbytes(y, rev, ko)
            if na is None or nb is None:
                continue
            tot += 1
            ja_b += na
            ko_b += nb
            if nb <= na:
                fit += 1
            else:
                over.append((nb - na, x, y))
    print('런 %d개 비교' % tot)
    print('  그대로 들어가는 런  %d개 (%.1f%%)' % (fit, 100.0 * fit / tot))
    print('  넘치는 런          %d개 (%.1f%%)' % (tot - fit, 100.0 * (tot - fit) / tot))
    print('  일본어 총 %d B → 한국어 총 %d B (%.2f배)' % (ja_b, ko_b, ko_b / ja_b))
    over.sort(reverse=True)
    print()
    print('가장 많이 넘치는 런:')
    for d, x, y in over[:10]:
        print('  +%2dB  %s' % (d, y))
        print('        (원문 %s)' % x)
    import statistics
    if over:
        ds = [d for d, _, _ in over]
        print()
        print('초과량: 평균 %.1fB, 중앙값 %dB, 최대 %dB'
              % (statistics.mean(ds), statistics.median(ds), max(ds)))


if __name__ == '__main__':
    main()
