# -*- coding: utf-8 -*-
"""auto_shrink 규칙으로 안 줄던 12건을 손으로 다듬어 runs.tsv 에 반영한다."""
import csv
import sys

sys.path.insert(0, 'tools')
from runs_build import load_maps, encode, BuildError

TSV = 'work/trans/runs.tsv'

FIXES = {
    ('2000.MDT', '00E8D'): '진도 그랬어‥‥',
    ('2000.MDT', '04A1A'): '집에 일 생기면',
    ('2000.MDT', '052C8'): '조개 간판의 우미네코정',
    ('E80C.MDT', '00385'): '와하하핫',
    ('E810.MDT', '00112'): '내 손으로! 다시 한번~~',
    ('E810.MDT', '00237'): '보고 싶은 표정 십자버튼으로 선택',
    ('E81C.MDT', '00304'): '모은 책이나 게임 등',
    ('E81C.MDT', '00511'): '자‥',
    ('E81C.MDT', '00805'): '지켜보겠습니다',
    ('EA18.MDT', '0009E'): '그냥‥',
    ('EB08.MDT', '003EA'): '오호홋‼',
    ('EB1C.MDT', '00348'): '크윽‥ 이 힘이!',
}


def main():
    rev, ko = load_maps()
    rows = list(csv.DictReader(open(TSV, encoding='utf-8'), delimiter='\t'))
    n = 0
    for r in rows:
        key = (r['file'], r['off'])
        if key in FIXES:
            newt = FIXES[key]
            L = int(r['len'])
            b = len(encode(newt, rev, ko))
            assert b <= L, (key, newt, b, L)
            r['ko'] = newt
            n += 1
    with open(TSV, 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t')
        w.writerow(['file', 'off', 'len', 'ja', 'ko'])
        for r in rows:
            w.writerow([r['file'], r['off'], r['len'], r['ja'], r['ko']])
    print('반영 %d / %d건' % (n, len(FIXES)))


if __name__ == '__main__':
    main()
