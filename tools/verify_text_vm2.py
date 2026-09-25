# -*- coding: utf-8 -*-
"""text_vm 검산 2차 — **알려진 대사가 실제로 들어 있는 블록**만 놓고 비교한다.

1차(`verify_text_vm.py`)는 op2 후보를 선형 스캔해서 3D 데이터 노이즈가 대량으로
섞였고, 그래서 「표 밖 글리프」 수치에 판별력이 없었다.

여기서는 `work/trans/runs.tsv`(실기에서 대사로 확인된 글자 런)를 기준으로,
**그 런을 포함하는 op2 블록**만 골라 새 규칙과 옛 규칙을 비교한다.
"""
import collections
import csv
import os
import struct
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from text_vm import decode_block, GLYPH_MAX
from verify_text_vm import CM, blocks, new_parse, old_parse, render


def load_runs():
    runs = collections.defaultdict(list)
    with open('work/trans/runs.tsv', encoding='utf-8') as fp:
        r = csv.reader(fp, delimiter='\t')
        next(r)
        for row in r:
            if len(row) >= 4:
                runs[row[0]].append((int(row[1], 16), int(row[2]), row[3]))
    return runs


def main():
    runs = load_runs()
    tot = nok = ook = 0
    nbad = obad = 0
    lead_hi = 0          # 0x15~0x1F 바이트가 나온 블록 수
    samples = []
    for f, rs in sorted(runs.items()):
        path = os.path.join('work/dm', 'FIELD_' + f)
        if not os.path.exists(path):
            continue
        d = open(path, 'rb').read()
        o, b, _ = script_section(d)
        sec = d[o:o + b]
        cand = blocks(sec)
        for off, L in cand:
            hit = [x for x in rs if off <= x[0] < off + L]
            if not hit:
                continue
            tot += 1
            a1, b1 = new_parse(sec, off, L)
            a2, b2 = old_parse(sec, off, L)
            nok += 1 if a1 else 0
            ook += 1 if a2 else 0
            nbad += b1
            obad += b2
            if any(0x15 <= c <= 0x1F for c in sec[off:off + L]):
                lead_hi += 1
            if a1 and not a2 and len(samples) < 5:
                toks, _ = decode_block(sec, off, L)
                samples.append((f, off, render(toks)))
    print('알려진 대사를 포함한 op2 블록 %d개' % tot)
    print('  새 규칙: 정렬 성공 %d (%.1f%%) / 표 밖 글리프 %d'
          % (nok, 100.0 * nok / max(tot, 1), nbad))
    print('  옛 규칙: 정렬 성공 %d (%.1f%%) / 표 밖 글리프 %d'
          % (ook, 100.0 * ook / max(tot, 1), obad))
    print('  0x15~0x1F 바이트를 가진 블록: %d개 (새 규칙이 2바이트 글자 선두로 읽는 값)' % lead_hi)
    print()
    print('새 규칙만 정렬에 성공한 예:')
    for f, off, t in samples:
        print('  %s +0x%X  %s' % (f, off, t[:110]))


if __name__ == '__main__':
    main()
