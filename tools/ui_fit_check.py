# -*- coding: utf-8 -*-
"""bintext 후보 번역이 원래 널종단 구간(개별 예산)에 들어가는지 검사한다.

사용: python tools/ui_fit_check.py <원본.BIN> <후보tsv(off/ko)>
"""
import csv
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps, BuildError


def main(bin_path, tsv_path):
    d = open(bin_path, 'rb').read()
    rev, ko = load_maps()
    ok = bad = 0
    for r in csv.DictReader(open(tsv_path, encoding='utf-8'), delimiter='\t'):
        off = int(r['off'], 16)
        j = off
        while j < len(d) and d[j] != 0:
            j += 1
        L = j - off
        try:
            nb = B.encode_with_vars(r['ko'], ko)
        except KeyError as e:
            print('X %-6s 인코딩불가 %s   %r' % (r['off'], e, r['ko']))
            bad += 1
            continue
        if len(nb) <= L:
            ok += 1
            print('O %-6s %2d/%2d  %s' % (r['off'], len(nb), L, r['ko']))
        else:
            bad += 1
            print('X %-6s %2d/%2d (+%d)  %s' % (r['off'], len(nb), L, len(nb) - L, r['ko']))
    print('\n들어감 %d / 초과·실패 %d' % (ok, bad))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
