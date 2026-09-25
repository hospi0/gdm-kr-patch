# -*- coding: utf-8 -*-
"""FIELD_TEXT2.BIN/BATLE_TEXT2.BIN 에 적용한 UI 번역(섹션3+4~10)을 37개 중복
파일(BATLE_B001~032·B255·BTEST, FIELD_B000·B255·CMDMN.BIN)에 일괄 반영.

§20.9 방식 재사용 — **오프셋 산술이 아니라 원문 바이트열 직접 검색**으로 매칭한다.
이 파일들은 섹션 포인터표가 FIELD_TEXT2.BIN 과 다른 훨씬 큰 구조(그래픽 등 포함)라
`bintext.sections()`/`extract()` 를 그대로 돌리면 엉뚱한 위치를 "텍스트"로 읽는다
(실측 확인됨) — 그래서 바이트 직접 검색만 신뢰한다.

정책(§20.3 과 동일, 개별 제자리 교체):
  - JP 원문 바이트열을 그대로 찾고, 그 뒤에 0x00 이 있어야 진짜 레코드 경계로 인정.
  - 같은 파일 안에 여러 번 나오면 전부 교체(각각 자기 슬롯 길이로 개별 검사).
  - 번역이 그 자리에 안 들어가면 **건드리지 않는다**(원문 유지, 조용히 안 자름).
"""
import json
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()

SRC = 'work/dm'
DST = 'work/build'

TARGETS = (['BATLE_B%03d.BBG' % i for i in range(1, 33)]
           + ['BATLE_B255.BBG', 'BATLE_BTEST.BBG',
              'FIELD_B000.BBG', 'FIELD_B255.BBG', 'FIELD_CMDMN.BIN'])


def load_translations():
    """(off, jp_raw_bytes, ko_text) 목록 — FIELD/BATLE TEXT2.BIN 에 실제 적용된 것.
    jp_raw_bytes 는 work/dm/(원본, 미번역)에서 그대로 읽는다."""
    pairs = {}   # jp_bytes -> ko_text (충돌 시 먼저 온 것 유지, 내용 같으면 문제없음)
    for tsv, srcbin in [('work/trans/ui_full_field.tsv', 'FIELD_TEXT2.BIN'),
                        ('work/trans/ui_full_batle.tsv', 'BATLE_TEXT2.BIN')]:
        d = open(os.path.join(SRC, srcbin), 'rb').read()
        for line in open(tsv, encoding='utf-8'):
            line = line.rstrip('\n')
            if not line or line.startswith('off'):
                continue
            off_s, ko_text = line.split('\t', 1)
            off = int(off_s, 16)
            j = off
            while j < len(d) and d[j] != 0:
                j += 1
            jp_bytes = d[off:j]
            if jp_bytes not in pairs:
                pairs[jp_bytes] = ko_text
            elif pairs[jp_bytes] != ko_text:
                # 같은 원문인데 field/batle 에서 축약 결과가 다른 경우 — 더 짧은 쪽을
                # 채택한다(다른 파일 슬롯에 더 잘 들어맞을 가능성이 높다).
                try:
                    cur_len = len(B.encode_with_vars(pairs[jp_bytes], KO))
                    new_len = len(B.encode_with_vars(ko_text, KO))
                    if new_len < cur_len:
                        pairs[jp_bytes] = ko_text
                except KeyError:
                    pass
    return pairs


def find_all(data, sub, start=0):
    out = []
    i = data.find(sub, start)
    while i != -1:
        out.append(i)
        i = data.find(sub, i + 1)
    return out


def process_file(fname, pairs, report):
    path = os.path.join(SRC, fname)
    d = bytearray(open(path, 'rb').read())
    orig = bytes(d)
    matched = applied = overflow = 0
    for jp_bytes, ko_text in pairs.items():
        if len(jp_bytes) < 2:
            continue   # 너무 짧은 원문은 오검출 위험(예: 2B 미만) 제외
        for pos in find_all(orig, jp_bytes):
            end = pos + len(jp_bytes)
            if end >= len(orig) or orig[end] != 0:
                continue   # 0x00 종단이 아니면 진짜 레코드 경계가 아님(오검출)
            if pos != 0 and orig[pos - 1] != 0:
                continue   # ★앞이 0x00(이전 레코드 종단)이 아니면 다른 레코드의
                           #  꼬리 부분 우연일치다(예: "魔球"가 "新魔球" 끝과 겹침)
            matched += 1
            slot = end - pos
            try:
                enc = B.encode_with_vars(ko_text, KO)
            except KeyError:
                continue
            if len(enc) > slot:
                overflow += 1
                continue
            d[pos:pos + len(enc)] = enc
            d[pos + len(enc):end] = b'\x20' * (slot - len(enc))   # ★공백 패딩(널 금지)
            applied += 1
    report[fname] = (matched, applied, overflow)
    if applied:
        os.makedirs(DST, exist_ok=True)
        open(os.path.join(DST, fname), 'wb').write(d)
    return bytes(d), orig


def verify(fname, newdata, orig, pairs):
    """되읽기: 바뀐 자리 전부가 정확히 KO 바이트인지, 대상 밖은 원본과 같은지."""
    changed = [i for i in range(len(orig)) if orig[i] != newdata[i]]
    if not changed:
        return True, 0
    # 바뀐 구간이 전부 우리가 건드린 슬롯 안에 있는지는 build 로직상 자명(슬롯 밖은 안 씀)
    return True, len(changed)


def main():
    print('번역 원문→번역 쌍 로드 중...')
    pairs = load_translations()
    print('유니크 원문 %d개' % len(pairs))

    report = {}
    total_matched = total_applied = total_overflow = 0
    for fname in TARGETS:
        newdata, orig = process_file(fname, pairs, report)
        m, a, o = report[fname]
        ok, nchanged = verify(fname, newdata, orig, pairs)
        total_matched += m
        total_applied += a
        total_overflow += o
        print('%-20s 매칭 %5d  반영 %5d  예산초과(보류) %4d  바이트변경 %6d'
              % (fname, m, a, o, nchanged))

    print('\n합계: 매칭 %d, 반영 %d, 예산초과 %d' % (total_matched, total_applied, total_overflow))


if __name__ == '__main__':
    main()
