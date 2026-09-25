# -*- coding: utf-8 -*-
"""새 extract_runs 규칙이 제어코드 인수를 실제로 피하는지 검산한다.

방법: `text_vm.decode_block`(인터프리터 확정 디코더)로 검증된 「깨끗한 블록」
(clean_block, §16 기준) 안에서 제어코드 인수 바이트 위치를 정확히 계산하고,
새 `scan_runs()` 가 낸 런이 그 위치와 하나라도 겹치는지 전수로 센다.

기대값: **0건**. scan_runs 는 이제 0x0A~0x0F 를 만나면 인수 2바이트를 통째로
건너뛰므로, 원리적으로 인수 위치를 런에 포함할 수 없다.
"""
import os
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from text_vm import decode_block
from verify_text_vm import blocks
from verify_text_vm3 import clean_block
from extract_runs import scan_runs, blocked_ranges, text


def arg_offsets(sec, off, L):
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
    tot_arg = tot_run = clobber = 0
    hits = []
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        sec = d[o:o + b]
        args = set()
        for boff, L in blocks(sec):
            if clean_block(sec, boff, L) is None:
                continue
            args |= arg_offsets(sec, boff, L)
        tot_arg += len(args)
        runs = scan_runs(sec, blocked_ranges(sec))
        tot_run += len(runs)
        for roff, rlen, codes in runs:
            bad = [x for x in range(roff, roff + rlen) if x in args]
            if bad:
                clobber += 1
                if len(hits) < 10:
                    hits.append((f[6:], roff, rlen, text(codes), sorted(bad)))
    print('검증된 블록 안 제어코드 인수 바이트 총 %d개 (참고용 분모)' % tot_arg)
    print('새 규칙으로 낸 런 %d개 중 인수 바이트를 포함한 런: %d' % (tot_run, clobber))
    for f, off, ln, t, bad in hits:
        print('  %s +0x%X len=%d %r  인수위치=%s' % (f, off, ln, t, bad))


if __name__ == '__main__':
    main()
