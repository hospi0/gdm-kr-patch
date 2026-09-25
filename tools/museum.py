# -*- coding: utf-8 -*-
"""박물관 컨텐츠 문자열표 — 추출/빌드 공통 모델 (2026-08-07 세션8).

실기 스샷에서 몬스터 도감·캐릭터 표정집·씬 목록이 통째로 «깨진 한글»로
나왔다 = 미번역 원문([[feedback_font_reuse_untranslated_looks_scrambled]]).
`ジャスティン` 역추적(`tools/unbreak.py`)으로 출처를 찾았고, 셋 다
**한 번도 추출조차 안 된 파일**이었다([[feedback_scan_whole_disc_not_filelist]]).

구조 (셋 다 동일):
    [BE32 섹션 오프셋표][섹션1][섹션2]…
    각 섹션 = 널 종단 문자열을 빽빽하게 이어붙인 것.

★렌더러는 «널을 세어 N번째 문자열»을 찾는다(§21.9와 같은 구조) →
  짧은 번역의 남는 자리는 반드시 **공백 0x20**으로 채운다. 널로 채우면
  빈 문자열이 끼어들어 순번이 전부 밀린다.
  [[feedback_null_padding_shifts_string_index]]
"""
import struct
import sys

sys.path.insert(0, 'tools')
import bintext as B
import halfwidth as H

# (파일, [(섹션이름, 헤더인덱스)])  — 끝은 다음 오프셋(마지막은 EOF)
SPECS = {
    'FIELD_MTMES.DAT': dict(nhdr=6, sections=[
        ('미술설정1', 0), ('미술설정2', 1), ('몬스터설정', 2),
        ('캐릭터설정1', 3), ('캐릭터설정2', 4), ('캐릭터설정3', 5)]),
    'FIELD_DICDT.DAT': dict(nhdr=12, sections=[
        ('도감머리말', 4), ('몬스터명', 5), ('출현지', 6), ('설명문', 7)]),
    'FIELD_MTOUT.DAT': dict(nhdr=4, sections=[('카테고리명', 3)]),
}


def header(d, n):
    return [struct.unpack_from('>I', d, i * 4)[0] for i in range(n)]


def bounds(d, spec):
    """[(섹션이름, 시작, 끝)]"""
    off = header(d, spec['nhdr'])
    out = []
    for name, idx in spec['sections']:
        lo = off[idx]
        cands = [o for o in off if o > lo] + [len(d)]
        out.append((name, lo, min(cands)))
    return out


def decode(raw):
    """전각/반각 모드를 따라가며 디코드."""
    out = []
    half = False
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0x03:
            out.append('{半}')
            half = True
            i += 1
            continue
        if b == 0x04:
            out.append('{全}')
            half = False
            i += 1
            continue
        if b < 0x10:
            out.append('{%02x}' % b)
            i += 1
            continue
        if half:
            out.append(H.IDX2CH.get(b - 0x20, '�'))
            i += 1
            continue
        if 0x10 <= b <= 0x1F and i + 1 < len(raw):
            out.append(B.M.get(0xE0 + (b - 0x10) * 256 + raw[i + 1], '�'))
            i += 2
            continue
        out.append(B.M.get(b - 0x20, '�'))
        i += 1
    return ''.join(out)


def strings(d, lo, hi):
    """[(오프셋, 슬롯길이, 원문)] — 슬롯길이는 종단 널 제외 바이트 수.

    ★널로 그냥 자르면 안 된다. `0x10~0x1F` 은 2바이트 글자의 선두이고
      **둘째 바이트가 0x00 인 글자가 실재한다**(`10 00`, `12 00` = 幅 등).
      실측: 「敵の防御力を 大幅」이 「…大」+「に下げたり」로 잘려 있었다.
      [[feedback_null_padding_shifts_string_index]] 와 같은 계열의 함정.
    """
    out = []
    i = lo
    start = lo
    while i < hi:
        b = d[i]
        if 0x10 <= b <= 0x1F:
            i += 2
            continue
        if b == 0:
            out.append((start, i - start, decode(d[start:i])))
            i += 1
            start = i
            continue
        i += 1
    if start < hi:
        out.append((start, hi - start, decode(d[start:hi])))
    return out


def cells(raw):
    """렌더 칸수 — 전각 1, 반각 0.5."""
    n = 0.0
    half = False
    i = 0
    while i < len(raw):
        b = raw[i]
        if b in (0x03, 0x04):
            half = b == 0x03
            i += 1
            continue
        if half:
            n += 0.5
            i += 1
        else:
            n += 1
            i += 2 if 0x10 <= b <= 0x1F else 1
    return n
