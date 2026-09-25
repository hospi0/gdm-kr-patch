# -*- coding: utf-8 -*-
import csv
import re

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def strip(s):
    return ''.join(p for p in TOKRE.split(s) if p and not TOKRE.fullmatch(p))


rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'), delimiter='\t'))
for want in ('!', '?', '~', ',', '.', chr(0xB7)):
    print('=== %r 사용처 ===' % want)
    n = 0
    for r in rows:
        if not r['ko']:
            continue
        txt = strip(r['ko'])
        if want in txt:
            print(' ', r['file'], r['off'], repr(txt)[:100])
            n += 1
            if n >= 8:
                break
