# -*- coding: utf-8 -*-
"""고정 길이 정책(블록 길이 원본과 동일) 기준으로 초과하는 메시지를 전부 찾는다.
script_build.py 의 인코딩 로직만 재사용해 실제로 raise 하지 않고 목록만 낸다.
"""
import csv
import os
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from script_build import BuildError, load_rev, text_to_tokens
from script_parse import emit
from script_render import messages

TSV = 'work/trans/script.tsv'
SRC = 'work/dm'


def main():
    m_rev, ko_rev = load_rev()
    rows = list(csv.DictReader(open(TSV, encoding='utf-8'), delimiter='\t'))
    byfile = {}
    for r in rows:
        byfile.setdefault(r['file'], {})[int(r['off'], 16)] = r

    over = []
    for f in sorted(os.listdir(SRC)):
        if not f.endswith('.MDT'):
            continue
        name = f[6:]
        d = open(os.path.join(SRC, f), 'rb').read()
        o, blen, _ = script_section(d)
        s = d[o:o + blen]
        msgs = messages(s)
        for p, blk in msgs:
            r = byfile.get(name, {}).get(p)
            ko = (r or {}).get('ko', '').strip()
            if not ko:
                continue
            try:
                toks = text_to_tokens(ko, m_rev, ko_rev)
            except BuildError as e:
                print('★인코딩 실패 %s +0x%04X: %s' % (name, p, e))
                continue
            nb = emit(toks)
            if len(nb) > len(blk):
                over.append((name, p, len(blk), len(nb), len(nb) - len(blk), ko))

    print('초과 메시지 %d개' % len(over))
    for name, p, ob, nb, d, ko in over:
        print('  %-12s +0x%04X  %dB -> %dB (%+dB)' % (name, p, ob, nb, d))
        print('     %s' % ko[:120])


if __name__ == '__main__':
    main()
