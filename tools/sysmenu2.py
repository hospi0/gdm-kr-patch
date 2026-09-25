# -*- coding: utf-8 -*-
"""시스템 메뉴 문자열 — **세그먼트 인식** 추출/빌드 (2026-08-07 2차).

1차(`extract_sysmenu`/`build_sysmenu`)의 두 가지 결함을 고친다:

1. **반각이 섞인 문자열을 통째로 건너뛰었다.** `0x03`=반각 전환, `0x04`=전각 복귀
   인데, 전각 구간만 미번역이면 그 부분이 한글 글리프로 깨진다
   (실기: `魔法LV1`→`홀 설LV1`, `本体RAM`→`직편RAM`).
   → 전각 구간만 번역하고 반각·제어 바이트는 **바이트 그대로 보존**한다.

2. **렌더 폭(칸수)을 안 봤다.** 게임은 라벨 자리를 원본 최대 폭만큼만 지우므로
   번역이 원본보다 넓으면 **잔상이 남는다**(실기: `마법・기술`(5칸)의 `술`이 남아
   다음 화면을 오염). → 칸수 상한을 강제한다.

★패딩은 반드시 공백(0x20). 널로 채우면 문자열 순번이 밀린다(§21.9).
"""
import re
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()

HALF_ON, HALF_OFF = 0x03, 0x04


def segments(raw):
    """[(kind, bytes)] — kind: 'full'(전각 글자런) / 'keep'(반각·제어, 그대로 보존)"""
    out = []
    cur = bytearray()
    kind = 'full'
    i = 0
    while i < len(raw):
        b = raw[i]
        if b in (HALF_ON, HALF_OFF):
            if cur:
                out.append((kind, bytes(cur)))
                cur = bytearray()
            out.append(('keep', bytes([b])))
            kind = 'keep' if b == HALF_ON else 'full'
            i += 1
            continue
        if kind == 'full' and 0x10 <= b <= 0x1F and i + 1 < len(raw):
            cur += raw[i:i + 2]
            i += 2
            continue
        cur.append(b)
        i += 1
    if cur:
        out.append((kind, bytes(cur)))
    return out


def decode_full(seg):
    return B.decode(seg)


def cells(raw):
    """렌더 칸수 — 전각 1칸, 반각 0.5칸(제어코드 0칸)."""
    n = 0.0
    kind = 'full'
    i = 0
    while i < len(raw):
        b = raw[i]
        if b in (HALF_ON, HALF_OFF):
            kind = 'keep' if b == HALF_ON else 'full'
            i += 1
            continue
        if kind == 'full':
            n += 1
            i += 2 if 0x10 <= b <= 0x1F else 1
        else:
            n += 0.5
            i += 1
    return n


# ★1바이트 대역에 복제해 둔 음절(font_apply.ALT_1BYTE 와 짝). 슬롯이 1바이트
#   모자랄 때만 쓰인다 — `관두기` 를 3바이트 슬롯에 넣기 위한 것.
KO_ALT = dict(KO)
KO_ALT['두'] = 0xCE


def encode_ko(t, alt=False):
    return B.encode_with_vars(t, KO_ALT if alt else KO)


def encode_best(t, slot):
    """일반 인코딩이 슬롯을 넘으면 1바이트 복제 슬롯을 써서 다시 시도."""
    e = encode_ko(t)
    if len(e) <= slot:
        return e
    e2 = encode_ko(t, alt=True)
    return e2 if len(e2) <= slot else e


def rebuild(raw, ko_list, slot=None):
    """전각 세그먼트를 순서대로 ko_list 로 교체. 반각·제어는 그대로.
    반환 bytes (패딩 전). ko_list 원소가 None 이면 그 세그먼트는 원본 유지."""
    out = bytearray()
    k = 0
    for kind, seg in segments(raw):
        if kind != 'full':
            out += seg
            continue
        t = ko_list[k] if k < len(ko_list) else None
        k += 1
        if t is None:
            out += seg
        else:
            out += encode_best(t, slot - len(out)) if slot else encode_ko(t)
    return bytes(out)


def fit(raw, ko_list, slot, cell_cap=None):
    """(성공?, 결과바이트, 사유)"""
    try:
        nb = rebuild(raw, ko_list, slot)
    except KeyError as e:
        return False, None, '인코딩불가 %s' % e
    if len(nb) > slot:
        return False, None, '바이트초과 %d>%d' % (len(nb), slot)
    cap = cell_cap if cell_cap is not None else cells(raw)
    c = cells(nb)
    if c > cap:
        return False, None, '칸초과 %.1f>%.1f' % (c, cap)
    return True, nb + b'\x20' * (slot - len(nb)), ''
