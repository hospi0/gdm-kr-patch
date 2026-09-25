# -*- coding: utf-8 -*-
"""shrink_fail.tsv 잔여분 최종 처리 (per-occurrence 실제 L 기준):
  1) other_fixes/other_fixes2 후보 중 fit 하는 것
  2) 그래도 안 되면 후보 문자열을 뒤에서부터 한 글자씩 깎아 시도
     (단, 결과가 1글자 이하로 줄면 — 사용자 결정: 원문 JP 유지, 적용 안 함)
"""
import csv
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
from runs_build import load_maps
import other_fixes
import other_fixes2

_, KO = load_maps()


def fits(t, L):
    try:
        return len(B.encode_with_vars(t, KO)) <= L
    except KeyError:
        return False


def best_fit(cands, L):
    for c in cands:
        if fits(c, L):
            return c
    # 마지막 후보를 기준으로 뒤에서 한 글자씩 깎는다(공백 제거 상태로)
    base = cands[-1].replace(' ', '') if cands else None
    if not base:
        return None
    s = base
    while len(s) > 1:
        s = s[:-1]
        if fits(s, L):
            return s
    return None


def main():
    rows = list(csv.DictReader(open('work/trans/shrink_fail.tsv', encoding='utf-8'), delimiter='\t'))
    other_rows = [r for r in rows if not r['ko'].startswith(('공격十', '방어十', '공격─', '방어─'))]
    by_file = {}
    dropped = []
    for r in other_rows:
        L = int(r['L'])
        cands = other_fixes2.FIXES2.get(r['ko']) or other_fixes.FIXES.get(r['ko']) or []
        chosen = best_fit(cands + [r['ko']], L)
        if chosen is None or len(chosen) <= 1:
            dropped.append((r['file'], r['off'], L, r['ko'], chosen))
            continue
        by_file.setdefault(r['file'], []).append((r['off'], chosen))

    print('반영', sum(len(v) for v in by_file.values()), '/ JP유지(1글자이하)', len(dropped))
    for f, off, L, ko, chosen in dropped:
        print('  DROP', f, off, 'L=%d' % L, repr(ko), '-> best', repr(chosen))

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
        drop_offs = {off for fn, off, L, ko, c in dropped if fn == f}
        replaced = added = removed = 0
        for off, ko in items:
            if off in existing:
                replaced += 1
            else:
                order.append(off)
                added += 1
            existing[off] = ko
        for off in drop_offs:
            if off in existing:
                del existing[off]
                order.remove(off)
                removed += 1
        order.sort()
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write('off\tko\n')
            for off in order:
                fh.write('%s\t%s\n' % (off, existing[off]))
        print(f, '교체', replaced, '신규', added, 'JP복원', removed, '(총', len(order), ')')


if __name__ == '__main__':
    main()
