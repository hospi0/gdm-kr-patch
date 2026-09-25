# -*- coding: utf-8 -*-
"""slot_plan.json 을 바탕으로 실제 코드 배정표 kocodes.tsv 를 만든다.

배정 정책:
  - 1바이트(히라+가타 재배치 가능분) → 빈도 상위 한글 음절
  - 2바이트(한자 영역, 0x0D8~) → 쉼표·마침표 + 나머지 한글

★ 예약(절대 재배정 금지): **번역문(ko)에 그대로 남는 기존 글자의 코드 전부.**
  『』「」・‥※♥♪ 같은 기호와, 원문 그대로 둔 가비지 세그먼트('ニ必0')가 여기 해당한다.
  이걸 안 지키면 화면에 엉뚱한 한글이 나온다 — 실제로 「」를 덮어써서
  「설정 자료집」이 「덕설정 자료집붙」으로 깨졌다.
"""
import csv
import json
import re
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')

with open('work/trans/slot_plan.json', encoding='utf-8') as f:
    plan = json.load(f)

m = codemap.base_map()
m.update(kanji_map())
rev = {}
for c, ch in sorted(m.items()):
    rev.setdefault(ch, c)

# 번역문이 그대로 쓰는 기존 글자 → 그 코드를 전부 예약한다
reserved = set()
for r in csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'), delimiter='\t'):
    if not r['ko']:
        continue
    for s in TOKRE.split(r['ko']):
        if not s or TOKRE.fullmatch(s):
            continue
        for ch in s:
            if 0xAC00 <= ord(ch) <= 0xD7A3:
                continue                    # 한글은 새로 그릴 글자
            if ch in rev:
                reserved.add(rev[ch])
print('예약 코드 %d개 (번역문이 그대로 쓰는 기존 글자)' % len(reserved))

free1 = [c for c in plan['free1'] if c not in reserved]
hangul_all = plan['top'] + plan['rest']
other = plan['other']          # [',', '.']

top = hangul_all[:len(free1)]
rest = hangul_all[len(free1):]

rows = []
for code, ch in zip(free1, top):
    rows.append((code, ch))

# 2바이트(한자 영역) 배정: 0x0D8부터 순서대로, 예약 코드 제외
n = 1504  # 전각 슬롯 총수
kanji_codes = [c for c in range(0xD8, n) if c not in reserved]
need2 = other + rest
assert len(need2) <= len(kanji_codes), '2바이트 배정 수가 한자 슬롯보다 많다 (%d > %d)' % (
    len(need2), len(kanji_codes))
for code, ch in zip(kanji_codes, need2):
    rows.append((code, ch))

rows.sort()
with open('work/trans/kocodes.tsv', 'w', encoding='utf-8') as f:
    f.write('# GDM 한글 슬롯 배정 — 1바이트 160자(빈도 상위) + 2바이트 464자(쉼표·마침표+나머지)\n')
    for code, ch in rows:
        f.write('%03X\t%s\n' % (code, ch))

print('work/trans/kocodes.tsv  %d항목 (1바이트 %d + 2바이트 %d)'
      % (len(rows), len(top), len(need2)))
print('1바이트 코드 범위: 0x%03X ~ 0x%03X' % (min(free1), max(free1)))
print('2바이트 코드 범위: 0x%03X ~ 0x%03X' % (min(c for c, _ in rows if c >= 0xD8),
                                           max(c for c, _ in rows if c >= 0xD8)))
