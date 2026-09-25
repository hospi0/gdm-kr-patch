# -*- coding: utf-8 -*-
"""mark_suspects()가 만든 불투명 토큰이 실제로 어떤 폰트 코드(글리프)를
가리키는지 전부 뽑는다.

이런 토큰은 원본 바이트를 그대로 들고 있다가 그대로 되쓰기 때문에, 그 바이트가
런타임에 (a) 진짜 제어 인수로 먹히거나 (b) 글자 코드로 렌더될 수 있다 — 어느
쪽인지 모른다. 그래서 (b)일 가능성에 대비해 이 코드들의 **글리프 자체는
한글로 재배치하지 않는다**(재배치해도 텍스트 자체는 안전하지만, 화면에
낯선 한글이 덧붙어 보일 위험이 있다).
"""
import os
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from script_parse import CTRL, TEXT, parse
from script_extract import mark_suspects
from script_render import messages

codes = set()
for f in sorted(os.listdir('work/dm')):
    if not f.endswith('.MDT'):
        continue
    d = open('work/dm/' + f, 'rb').read()
    o, b, _ = script_section(d)
    for p, blk in messages(d[o:o + b]):
        toks = parse(blk)
        opaqued = mark_suspects(toks)
        # parse() 결과에서 TEXT였는데 mark_suspects 후 CTRL이 된 코드만 추린다
        text_codes = [v for t, v in toks if t == TEXT]
        remaining_text = [v for t, v in opaqued if t == TEXT]
        removed = len(text_codes) - len(remaining_text)
        if removed:
            # 어떤 코드가 없어졌는지 다중집합 차분으로 구한다
            from collections import Counter
            before, after = Counter(text_codes), Counter(remaining_text)
            for v in before:
                if before[v] > after.get(v, 0):
                    codes.add(v)

print('불투명 토큰이 참조하는 폰트 코드 %d개: %s'
      % (len(codes), sorted('0x%03X' % c for c in codes)))
