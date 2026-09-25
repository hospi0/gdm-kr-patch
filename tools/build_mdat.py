# -*- coding: utf-8 -*-
"""`BATLE/M_DAT.BIN` 의 적 이름·기술명을 한글로 바꾼다.

## 구조 (2026-08-08 실측)

적 1마리 블록 = **0x34(52 B) 고정 레코드**가 연달아 붙는다.

    X          적 이름      예) 0xD29A0 `グレートベレー`
    X + 0x34   기술 1       예) 0xD29D4 `溜め斬り`
    X + 0x68   기술 2       예) 0xD2A08 `バーストショット`

문자열은 널 종단이고 뒤는 0 패딩이다. 실제 쓸 수 있는 폭은
「문자열 + 뒤따르는 널런」 — 309칸 중 193칸이 정확히 20 B(전각 10자).

## 원본

`work/dm_all/BATLE_M_DAT.BIN` 은 **원본 디스크와 바이트 전량 일치**를 확인했다
(우리가 이 파일을 건드린 적이 없어서다). `work/dm` 에는 이 파일이 없다.

## 정책

* 원문 바이트열 직접 검색, 앞뒤가 `0x00` 인 자리만 인정.
* 남는 자리는 **공백 0x20** — 널을 넣으면 문자열 순번이 밀린다.
"""
import json
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()

SRC, DST = 'work/dm_all', 'work/build'
FN = 'BATLE_M_DAT.BIN'
TABLE = 'work/trans/mdat_ko.json'


def main():
    table = json.load(open(TABLE, encoding='utf-8'))
    orig = open(os.path.join(SRC, FN), 'rb').read()
    p_dst = os.path.join(DST, FN)
    cur = bytearray(open(p_dst, 'rb').read() if os.path.exists(p_dst) else orig)
    assert len(cur) == len(orig), '빌드본 크기가 원본과 다르다'

    # 원문(디코드) → 실제 바이트열
    raws = {}
    start = 0
    for i, b in enumerate(orig):
        if b == 0:
            if 4 <= i - start <= 40:
                try:
                    s = B.decode(orig[start:i])
                except Exception:
                    s = None
                if s in table:
                    raws.setdefault(orig[start:i], table[s])
            start = i + 1
    print('번역표 %d개 → 원문 바이트열 %d개' % (len(table), len(raws)))

    m = a = o = 0
    for raw, ko in raws.items():
        pos = orig.find(raw)
        while pos != -1:
            end = pos + len(raw)
            if orig[end] == 0 and (pos == 0 or orig[pos - 1] == 0):
                # 쓸 수 있는 폭 = 문자열 + 뒤따르는 널런
                z = end
                while z < len(orig) and orig[z] == 0:
                    z += 1
                slot = z - pos
                m += 1
                try:
                    enc = B.encode_with_vars(ko, KO)
                except KeyError:
                    pos = orig.find(raw, pos + 1)
                    continue
                if len(enc) > slot - 1:          # 종단 널 한 칸은 남긴다
                    o += 1
                else:
                    cur[pos:pos + len(enc)] = enc
                    cur[pos + len(enc):end] = b'\x20' * (end - pos - len(enc))
                    a += 1
            pos = orig.find(raw, pos + 1)
    print('매칭 %d  반영 %d  예산초과 %d' % (m, a, o))

    if a:
        os.makedirs(DST, exist_ok=True)
        open(p_dst, 'wb').write(bytes(cur))

    # 되읽기 검증
    ok = bad = 0
    for raw, ko in raws.items():
        enc = B.encode_with_vars(ko, KO)
        pos = orig.find(raw)
        while pos != -1:
            end = pos + len(raw)
            if orig[end] == 0 and (pos == 0 or orig[pos - 1] == 0) and len(enc) <= end - pos:
                want = enc + b'\x20' * (end - pos - len(enc))
                if bytes(cur[pos:end]) == want:
                    ok += 1
                else:
                    bad += 1
            pos = orig.find(raw, pos + 1)
    print('되읽기 일치 %d / 불일치 %d' % (ok, bad))


if __name__ == '__main__':
    main()
