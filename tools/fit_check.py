# -*- coding: utf-8 -*-
"""후보 번역이 런 예산에 들어가는지 실제 인코더로 검사한다 (추정 금지).

사용: python tools/_fit_check.py <후보tsv>   (열: file / off / ko)
"""
import csv
import sys

sys.path.insert(0, 'tools')
from runs_build import load_maps, encode, BuildError

RUNS = 'work/trans/runs.tsv'


def main(path):
    rev, ko = load_maps()
    budget = {}
    ja = {}
    for r in csv.DictReader(open(RUNS, encoding='utf-8'), delimiter='\t'):
        budget[(r['file'], r['off'])] = int(r['len'])
        ja[(r['file'], r['off'])] = r['ja']

    ok = bad = 0
    for r in csv.DictReader(open(path, encoding='utf-8'), delimiter='\t'):
        k = (r['file'], r['off'])
        if k not in budget:
            print('없는키 %s %s' % k)
            bad += 1
            continue
        L = budget[k]
        try:
            n = len(encode(r['ko'], rev, ko))
        except BuildError as e:
            print('X %-10s %-6s %s' % (k[0], k[1], e))
            bad += 1
            continue
        if n <= L:
            ok += 1
            print('O %-10s %-6s %2d/%2d  %s' % (k[0], k[1], n, L, r['ko']))
        else:
            bad += 1
            print('X %-10s %-6s %2d/%2d (+%d)  %s   ja=%s'
                  % (k[0], k[1], n, L, n - L, r['ko'], ja[k]))
    print('\n들어감 %d / 초과·실패 %d' % (ok, bad))


if __name__ == '__main__':
    main(sys.argv[1])
