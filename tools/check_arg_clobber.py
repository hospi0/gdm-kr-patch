# -*- coding: utf-8 -*-
"""확정된 디코더로 **제어코드 인수 바이트**를 정확히 찾아, 번역이 그 자리를 덮는지 센다.

배경: `extract_runs.py` 는 제어코드 뒤 인수(0x20 이상이면 글자로 읽힌다)를 걸러내려고
`work/trans/junk_prefix.tsv` 수동 보정표를 쓴다. 실측 사례 `00 00 0B 00 | 21 | 10 17`
(2000.MDT +0x23F5) 에서 `21` 을 글자로 오독했고, **번역이 덮으면 실기 크래시**다.

이제 `0x0601D5A4` 에서 읽은 규칙으로 인수 바이트를 원리적으로 특정할 수 있다:
    0x0A~0x0F = 제어코드 + **2바이트 인수**

⚠️ 커버리지 한계를 명시한다 — 파싱은 블록 시작이라는 앵커가 있어야 정렬이 맞으므로,
   깨끗하게 검증된 op2 블록(`verify_text_vm3.clean_block`) 안에서만 판정한다.
   그 밖은 «미판정»으로 남긴다. 「내 데이터엔 이상 없음」이 검증이 아니다.
"""
import collections
import csv
import os
import struct
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from text_vm import decode_block
from verify_text_vm import blocks
from verify_text_vm3 import clean_block


def load_runs():
    runs = collections.defaultdict(list)
    with open('work/trans/runs.tsv', encoding='utf-8') as fp:
        r = csv.reader(fp, delimiter='\t')
        next(r)
        for row in r:
            if len(row) >= 4:
                ko = row[4] if len(row) > 4 else ''
                runs[row[0]].append((int(row[1], 16), int(row[2]), row[3], ko))
    return runs


def arg_offsets(sec, off, L):
    """블록 안에서 **제어코드 인수**로 소비되는 바이트 오프셋 집합."""
    toks, _ = decode_block(sec, off, L)
    p = off
    out = set()
    for t in toks:
        if t.kind == 'ctrl' and t.arg is not None:
            out.add(p + 1)
            out.add(p + 2)
        p += len(t.raw)
    return out


def main():
    runs = load_runs()
    tot_run = covered = clob = clob_tr = 0
    hits = []
    for f, rs in sorted(runs.items()):
        path = os.path.join('work/dm', 'FIELD_' + f)
        if not os.path.exists(path):
            continue
        d = open(path, 'rb').read()
        o, b, _ = script_section(d)
        sec = d[o:o + b]
        args = set()
        span = []
        for boff, L in blocks(sec):
            if clean_block(sec, boff, L) is None:
                continue
            args |= arg_offsets(sec, boff, L)
            span.append((boff, boff + L))
        for roff, rlen, ja, ko in rs:
            tot_run += 1
            if not any(a <= roff and roff + rlen <= b2 for a, b2 in span):
                continue                     # 검증된 블록 밖 → 미판정
            covered += 1
            bad = [x for x in range(roff, roff + rlen) if x in args]
            if bad:
                clob += 1
                if ko.strip():
                    clob_tr += 1
                    if len(hits) < 12:
                        hits.append((f, roff, rlen, ja, ko, len(bad)))
    print('런 %d개 중 검증된 블록 안에 완전히 들어간 것 %d개 (%.1f%%) — 나머지는 미판정'
          % (tot_run, covered, 100.0 * covered / max(tot_run, 1)))
    print('  인수 바이트를 포함한 런        : %d' % clob)
    print('  ★그중 번역이 들어간 것(위험)  : %d' % clob_tr)
    print()
    for f, off, ln, ja, ko, nb in hits:
        print('  %s +0x%X len=%d 인수%dB  ja=%s  ko=%s' % (f, off, ln, nb, ja, ko))


if __name__ == '__main__':
    main()
