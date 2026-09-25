# -*- coding: utf-8 -*-
"""runs.tsv 에서 길이 초과 번역만 골라 auto_shrink 의 축약 규칙을 적용한다.

세션3 auto_shrink.py 는 특정 배치 파일(batch_clean.tsv) 병합용이라 지금
(세션4, 런 경계 재계산 이후) 남은 18건 같은 **일반 초과 정리**에는 안 맞는다.
같은 축약 로직(try_shrink)만 재사용해 runs.tsv 를 직접 고친다.
"""
import csv
import sys

sys.path.insert(0, 'tools')
from auto_shrink import fits, try_shrink

TSV = 'work/trans/runs.tsv'


def main():
    rows = list(csv.DictReader(open(TSV, encoding='utf-8'), delimiter='\t'))
    n_ok = n_fail = 0
    fails = []
    for r in rows:
        ko = r['ko'].strip()
        if not ko:
            continue
        L = int(r['len'])
        if fits(ko, L):
            continue
        newt, how = try_shrink(ko, L)
        if newt is None:
            fails.append((r['file'], r['off'], L, r['ja'], ko))
            n_fail += 1
        else:
            r['ko'] = newt
            n_ok += 1
            print('축약(%s) %s +%s: %r -> %r' % (how, r['file'], r['off'], ko, newt))

    with open(TSV, 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t')
        w.writerow(['file', 'off', 'len', 'ja', 'ko'])
        for r in rows:
            w.writerow([r['file'], r['off'], r['len'], r['ja'], r['ko']])

    print('자동 축약 성공 %d / 실패(사람 필요) %d' % (n_ok, n_fail))
    for f, off, L, ja, ko in fails:
        print('  %s +%s len=%d ja=%s ko=%s' % (f, off, L, ja, ko))


if __name__ == '__main__':
    main()
