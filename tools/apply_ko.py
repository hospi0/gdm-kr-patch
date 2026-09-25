# -*- coding: utf-8 -*-
"""번역 딕셔너리를 script.tsv 의 ko 열에 채워 넣는다.

TRANS[(file, off)] = [텍스트런0, 텍스트런1, ...] — ja를 {hex}/\\n/\\p 로 쪼갰을 때
나오는 "글자가 있는 런"의 개수와 정확히 같은 순서로 한국어 문자열을 준다.
빈 런(제어코드끼리 붙어 있어 생기는 '')은 자동으로 유지되므로 안 줘도 된다.
"""
import csv
import re
import sys

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def segments(ja):
    return [s for s in TOKRE.split(ja) if s and not TOKRE.fullmatch(s)]


def build(ja, parts):
    segs = TOKRE.split(ja)
    parts = list(parts)
    pi = 0
    out = []
    for s in segs:
        if s == '':
            continue
        if TOKRE.fullmatch(s):
            out.append(s)
        else:
            if pi >= len(parts):
                raise ValueError('parts 부족: ja=%r parts=%r' % (ja, parts))
            out.append(parts[pi])
            pi += 1
    if pi != len(parts):
        raise ValueError('parts 과다: ja=%r parts=%r (필요 %d, 받음 %d)'
                          % (ja, parts, pi, len(parts)))
    return ''.join(out)


# 번역 딕셔너리는 tools/trans_data.py 에서 가져온다 (분량이 많아 분리)
from trans_data import TRANS  # noqa: E402


def main():
    rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'),
                               delimiter='\t'))
    done = missing = errors = 0
    for r in rows:
        key = (r['file'], r['off'])
        if key not in TRANS:
            missing += 1
            r['ko'] = ''
            continue
        try:
            r['ko'] = build(r['ja'], TRANS[key])
            done += 1
        except ValueError as e:
            errors += 1
            print('오류 %s +%s: %s' % (key[0], key[1], e))
            r['ko'] = ''

    stale = [k for k in TRANS if k not in {(r['file'], r['off']) for r in rows}]
    with open('work/trans/script.tsv', 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, ['file', 'off', 'len', 'ja', 'ko'], delimiter='\t')
        w.writeheader()
        w.writerows(rows)
    print('번역 적용 %d / 미번역 %d / 오류 %d (전체 %d)' % (done, missing, errors, len(rows)))
    if stale:
        print('★TRANS 에는 있는데 TSV에 없는 키 %d개: %s' % (len(stale), stale[:5]))


if __name__ == '__main__':
    main()
