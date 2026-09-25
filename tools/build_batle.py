# -*- coding: utf-8 -*-
"""전투 텍스트(기술·마법·아이템 설명, 장비 효과, 작전) 번역을 반영한다.

## 왜 별도 빌더인가

`ui_build.py` + `propagate_ui_dup.py` 가 다루는 섹션(UI 용어·아이템명)에
**설명문이 빠져 있었다**. 실기 전투 화면의 「敵1体／素早く短剣を投げつける」 가
`WDATA.DAT` 에서는 번역됐는데 `TEXT2.BIN`·`.BBG` 에는 원문 그대로 남아 있어
화면에 깨진 한글(=미번역 원문)로 떴다.

## 원본 기준 — ★`work/dm_all` 을 쓰면 안 된다

`work/dm_all` 은 2026-08-07 에 **패치된 ISO** 에서 뽑은 것이라 이미 우리 번역이
들어 있다(원본 디스크와 `FIELD_TEXT2.BIN` 10,257 B 불일치, 실측 확인).
무수정 원본은 `work/dm`(104개) 뿐이다.

## 정책

* 원문 바이트열 **직접 검색** — 이 파일들은 섹션표 구조가 서로 달라 오프셋 산술이
  안 통한다(§20.9).
* 앞뒤가 `0x00` 인 자리만 진짜 레코드로 인정(꼬리 우연일치 방지).
* 남는 자리는 **공백 0x20** 으로 채운다. 널을 쓰면 렌더러의 문자열 순번이 밀려
  화면이 군데군데 빈다([[feedback_null_padding_shifts_string_index]]).
* 출력은 `work/build` 에 **이미 있으면 그 위에** 쓴다 — 다른 빌더 결과를 지우지
  않기 위해서다.
"""
import json
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()

SRC, DST = 'work/dm', 'work/build'
TABLE = 'work/trans/batle_ko.json'

TARGETS = (['FIELD_TEXT2.BIN', 'BATLE_TEXT2.BIN']
           + ['BATLE_B%03d.BBG' % i for i in range(1, 33)]
           + ['BATLE_B255.BBG', 'BATLE_BTEST.BBG',
              'FIELD_B000.BBG', 'FIELD_B255.BBG', 'FIELD_CMDMN.BIN'])


def jp_bytes(orig, table):
    """번역표의 원문(디코드된 텍스트) → 원본 파일에 실재하는 바이트열"""
    out = {}
    start = 0
    for i, b in enumerate(orig):
        if b == 0:
            if i - start >= 4:
                raw = orig[start:i]
                try:
                    s = B.decode(raw)
                except Exception:
                    s = None
                if s in table and raw not in out:
                    out[raw] = table[s]
            start = i + 1
    return out


def find_all(d, sub):
    out, i = [], d.find(sub)
    while i != -1:
        out.append(i)
        i = d.find(sub, i + 1)
    return out


def main():
    table = json.load(open(TABLE, encoding='utf-8'))
    print('번역표 %d개' % len(table))

    # 원문 바이트열은 TEXT2 두 개에서 모은다(사본 파일들도 같은 바이트를 쓴다)
    pairs = {}
    for fn in ('FIELD_TEXT2.BIN', 'BATLE_TEXT2.BIN'):
        pairs.update(jp_bytes(open(os.path.join(SRC, fn), 'rb').read(), table))
    print('원문 바이트열 %d개 확보' % len(pairs))

    tot_m = tot_a = tot_o = 0
    for fn in TARGETS:
        p_src = os.path.join(SRC, fn)
        if not os.path.exists(p_src):
            print('%-20s 원본 없음 — 건너뜀' % fn)
            continue
        orig = open(p_src, 'rb').read()
        p_dst = os.path.join(DST, fn)
        cur = bytearray(open(p_dst, 'rb').read() if os.path.exists(p_dst) else orig)
        if len(cur) != len(orig):
            print('%-20s ★크기 불일치 — 건너뜀' % fn)
            continue
        m = a = o = 0
        for raw, ko in pairs.items():
            for pos in find_all(orig, raw):
                end = pos + len(raw)
                if end >= len(orig) or orig[end] != 0:
                    continue
                if pos and orig[pos - 1] != 0:
                    continue
                m += 1
                try:
                    enc = B.encode_with_vars(ko, KO)
                except KeyError:
                    continue
                if len(enc) > len(raw):
                    o += 1
                    continue
                cur[pos:pos + len(enc)] = enc
                cur[pos + len(enc):end] = b'\x20' * (len(raw) - len(enc))
                a += 1
        tot_m += m
        tot_a += a
        tot_o += o
        if a:
            os.makedirs(DST, exist_ok=True)
            open(p_dst, 'wb').write(bytes(cur))
        print('%-20s 매칭 %5d  반영 %5d  예산초과 %3d' % (fn, m, a, o))
    print('\n합계: 매칭 %d, 반영 %d, 예산초과 %d' % (tot_m, tot_a, tot_o))


if __name__ == '__main__':
    main()
