# -*- coding: utf-8 -*-
"""스크린샷 없이 "화면에서 깨질 문자열이 몇 개 남았는가"를 계산한다.

원리: 어떤 문자열이 화면에서 깨지려면 (a) 실제로 표시되는 텍스트여야 하고
(b) 그 글자 중 하나라도 한글에 재배정된 슬롯을 써야 한다. (a)는 이미 검증된
real_jp() 필터로, (b)는 kocodes.tsv 로 계산 가능 — 실기 확인이 필요 없다.

대상: 지금까지 찾은 37개 파일(BATLE_B001~032·B255·BTEST, FIELD_TEXT2/BATLE_TEXT2,
FIELD_B000·B255, FIELD_CMDMN.BIN) + `sections()` 포인터표가 없는 파일은
전체를 널종단 문자열로 훑어 별도 처리.
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap
from codemap_kanji_src import kanji_map

M = codemap.base_map()
M.update(kanji_map())
REV = {}
for c, ch in sorted(M.items()):
    REV.setdefault(ch, c)

ko = {}
for line in open('work/trans/kocodes.tsv', encoding='utf-8'):
    if line.strip() and not line.startswith('#'):
        a, b = line.rstrip('\n').split('\t')[:2]
        ko[b] = int(a, 16)
stolen_codes = set(ko.values())


def is_broken(t):
    for ch in t:
        c = REV.get(ch)
        if c is not None and c in stolen_codes:
            return True
    return False


FAMILY = (['BATLE_B%03d.BBG' % i for i in range(1, 33)]
          + ['BATLE_B255.BBG', 'BATLE_BTEST.BBG', 'FIELD_B000.BBG',
             'FIELD_B255.BBG', 'FIELD_TEXT2.BIN', 'BATLE_TEXT2.BIN'])

# ── 1) 정상 섹션 구조 파일들 ──
tot_strings = tot_broken = 0
per_file = {}
for fn in FAMILY:
    d = open('work/dm/' + fn, 'rb').read()
    rs = B.extract(d)
    broken = [(off, l, t) for off, l, t in rs if is_broken(t)]
    per_file[fn] = (len(rs), len(broken))
    tot_strings += len(rs)
    tot_broken += len(broken)

print('=== 정상 구조 파일(섹션3+, 도구/전투UI 계열) ===')
for fn in FAMILY:
    n, b = per_file[fn]
    if b:
        print('  %-22s 전체%5d  깨진것%4d' % (fn, n, b))
print('합계: 전체 %d / 깨짐 %d\n' % (tot_strings, tot_broken))

# ── 2) FIELD_CMDMN.BIN — 포인터표 없음, 전체 널종단 스캔 ──
d = open('work/dm/FIELD_CMDMN.BIN', 'rb').read()


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def real_jp_loose(t):
    import re
    t2 = re.sub(r'[\x00-\x1f]', '', t)
    if len(t2) < 2:
        return False
    hira = sum(1 for c in t2 if c in codemap.HIRA)
    kan = sum(1 for c in t2 if is_kanji(c))
    kat = sum(1 for c in t2 if c in codemap.KATA)
    if hira == 0 and kan == 0 and kat < 2:
        return False
    return True


cmdmn_hits = []
i = 0
while i < len(d):
    j = i
    while j < len(d) and d[j] != 0:
        j += 1
    if j > i:
        raw = d[i:j]
        t = B.decode_with_vars(raw)
        if real_jp_loose(t) and is_broken(t):
            cmdmn_hits.append((i, j - i, t))
    i = j + 1

print('=== FIELD_CMDMN.BIN (포인터표 없음, 전체 스캔) ===')
for off, l, t in cmdmn_hits:
    print('  0x%05X %2d  %r' % (off, l, t))
print('깨진 것 %d개\n' % len(cmdmn_hits))

print('=== 총계 ===')
print('깨진 문자열 %d개 (섹션구조 %d + CMDMN %d)'
      % (tot_broken + len(cmdmn_hits), tot_broken, len(cmdmn_hits)))
