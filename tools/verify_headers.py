# -*- coding: utf-8 -*-
"""전수 검증: 빌드 결과물에서 `2LLL` 블록 헤더가 하나도 안 깨졌는지 확인한다.

세션6 버그의 본질이 「런이 헤더를 삼켜서 빌더가 그 위에 번역문을 썼다」이므로,
이 검사가 재발 감시의 핵심이다.
"""
import os
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from text_vm import scan_candidates
import extract_runs as er

bad = tot = 0
for fn in sorted(os.listdir('work/dm')):
    if not fn.endswith('.MDT'):
        continue
    a = open('work/dm/' + fn, 'rb').read()
    b = open('work/build/' + fn, 'rb').read()
    if len(a) != len(b):
        print('★ %s 크기 변경' % fn)
        bad += 1
        continue
    o, nbytes, _ = script_section(a)
    s = a[o:o + nbytes]
    # ⚠️ scan_candidates 는 우연히 `2LLL` 처럼 보이는 가짜까지 전부 낸다.
    #    실제로 채택된 신뢰 블록만 봐야 의미가 있다.
    for off, L, _toks in er.trusted_blocks(s):
        if off < 2:
            continue
        tot += 1
        # 블록 본문 바로 앞 2바이트 = `2LLL` 헤더
        if a[o + off - 2:o + off] != b[o + off - 2:o + off]:
            print('★ %s 헤더 파괴 @본문 0x%05X : %s → %s'
                  % (fn, off, a[o + off - 2:o + off].hex(' '),
                     b[o + off - 2:o + off].hex(' ')))
            bad += 1

print('블록 헤더 %d개 검사 — 파괴 %d개' % (tot, bad))
print('결과: %s' % ('통과' if bad == 0 else '실패'))
