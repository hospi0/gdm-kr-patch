# -*- coding: utf-8 -*-
"""stat_fixes.py 의 후보문자열을 실제 예산(shrink_fail.tsv 의 L)에 맞춰
검증하고, 맞는 첫 후보를 대상 tsv 에 추가한다."""
import csv
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
from runs_build import load_maps
import stat_fixes

_, KO = load_maps()


def fits(t, L):
    try:
        return len(B.encode_with_vars(t, KO)) <= L
    except KeyError:
        return False


def main():
    rows = list(csv.DictReader(open('work/trans/shrink_fail.tsv', encoding='utf-8'), delimiter='\t'))
    stat_rows = [r for r in rows if r['ko'].startswith(('공격十', '방어十', '공격─', '방어─'))]
    by_file = {}
    fail = []
    for r in stat_rows:
        key = (r['file'], r['off'])
        L = int(r['L'])
        cands = stat_fixes.FIXES.get(key)
        if not cands:
            fail.append((key, L, r['ko'], '수정안없음'))
            continue
        chosen = None
        for c in cands:
            if fits(c, L):
                chosen = c
                break
        if chosen is None:
            fail.append((key, L, r['ko'], '후보전부초과:' + repr(cands)))
            continue
        by_file.setdefault(r['file'], []).append((r['off'], chosen))
    print('처리대상', len(stat_rows), '성공', sum(len(v) for v in by_file.values()), '실패', len(fail))
    for k, L, ko, why in fail:
        print('  X', k, 'L=%d' % L, ko, '->', why)

    for f, items in by_file.items():
        existing = {}
        order = []
        with open(f, encoding='utf-8') as fh:
            fh.readline()
            for line in fh:
                line = line.rstrip('\n')
                if line:
                    off, ko = line.split('\t', 1)
                    existing[off] = ko
                    order.append(off)
        replaced = added = 0
        for off, ko in items:
            if off in existing:
                replaced += 1
            else:
                order.append(off)
                added += 1
            existing[off] = ko
        order.sort()
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write('off\tko\n')
            for off in order:
                fh.write('%s\t%s\n' % (off, existing[off]))
        print(f, '교체', replaced, '신규', added, '(총', len(order), ')')

    return fail


if __name__ == '__main__':
    main()
