# -*- coding: utf-8 -*-
"""놓친 메시지가 있는지 전수 조사한다.

기존 추출은 두 가지 제약이 있었다:
  (a) `script_section()` 이 **파일당 섹션 하나**만 고른다
  (b) `messages()` 가 블록이 **제어코드(<0x20)로 시작**할 것을 요구한다

둘 다 풀어서 다시 세어 본다.
"""
import os
import struct
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section, sections


def scan(s, strict=True):
    ln = len(s)
    out, p = [], 0
    while p < ln - 4:
        if s[p] == 0x20 and p % 2 == 0:
            L = s[p + 1]
            ok = (L >= 6 and L % 2 == 0 and p + 2 + L <= ln
                  and s[p + 2 + L - 1] == 0x07)
            if ok and strict:
                ok = s[p + 2] < 0x20
            if ok:
                out.append((p, s[p + 2:p + 2 + L]))
                p += 2 + L
                continue
        p += 2
    return out


def main():
    tot_cur = tot_all = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        cur = len(scan(d[o:o + b], strict=True))
        tot_cur += cur

        # 전 섹션 × 완화 조건
        best = []
        for so, sb in sections(d):
            for strict in (True, False):
                got = scan(d[so:so + sb], strict=strict)
                if got:
                    best.append((so, sb, strict, len(got)))
        # 같은 섹션은 완화 쪽(더 많이 잡히는 것)만
        bysec = {}
        for so, sb, strict, n in best:
            if so not in bysec or n > bysec[so][2]:
                bysec[so] = (sb, strict, n)
        allmsg = sum(v[2] for v in bysec.values())
        tot_all += allmsg
        mark = '' if allmsg == cur else '  ★'
        print('%-16s 현재 %3d / 전수 %3d (섹션 %d개)%s'
              % (f[6:], cur, allmsg, len(bysec), mark))
        if allmsg != cur:
            for so in sorted(bysec):
                sb, strict, n = bysec[so]
                tag = '← 현재 쓰는 섹션' if so == o else ''
                print('     +0x%06X %6dB  %3d개 %s %s'
                      % (so, sb, n, '엄격' if strict else '완화', tag))
    print('-' * 60)
    print('현재 추출 %d개 / 전수 스캔 %d개' % (tot_cur, tot_all))


if __name__ == '__main__':
    main()
