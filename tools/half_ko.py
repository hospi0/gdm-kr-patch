# -*- coding: utf-8 -*-
r"""반각(8×8) 한글 — 음절 번호·인코딩·상수 (2026-10-16).

반각 글꼴(VDP2 셀 0~255 = 글자 코드)은 1바이트라 한글이 안 들어간다 → 2바이트:
    [선두 바이트 L][둘째 바이트 i]   음절 번호 s = LEADS.index(L) * 223 + (i - 0x20) - (i > 0x25)
  · 선두 = 반각 표(TEXT2 구역 0~2)에서 한 번도 안 쓰인 코드(。「」、 등). 둘째 = 0x20~0xFF 에서 `%`(0x25) 뺌
    — 메뉴 문자열은 vsprintf(0x060C478C)를 거치므로 `%` 금지, 0x00 은 문자열 끝·순번 세기라 금지.
  · 음절 목록 = kocodes(전각 한글 배정)의 음절을 코드 순서대로. 전각과 같은 집합이라 번역문 그대로 쓸 수 있다.
그리기 = 훅이 RAM 의 1bpp 글리프(han8gdm)를 VDP2 셀 CELL0‥CELL0+NSLOT-1 (캐시) 에 4bpp 로 풀어 찍는다.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

LEADS = [0xFE, 0xFF, 0xA3]                    # 3 × 223 = 669 음절. ⛔0xA0 = 작은 「3」(Lv3 — 코드가 직접 찍음, 2026-10-16 실기 네모)
#   0xFE·0xFF = 빈 네모 글리프(안 씀), 0xA3 = 」(반각 8×8 문자열엔 안 나옴 — 전각 오독 흔적만)
PER_LEAD = 223
CELL0, NSLOT = 0x520, 224                     # VRAM 0xA400‥0xBFFF — 메뉴·전투 스테이트 15장 공통 빈칸
INK = 0xE                                     # 원래 반각 글꼴의 글자 몸 색인


def syllables():
    out = []
    for line in open(os.path.join(ROOT, 'work', 'trans', 'kocodes.tsv'), encoding='utf-8'):
        line = line.rstrip('\r\n')
        if not line or line.startswith('#'):
            continue
        a, b = line.split('\t')[:2]
        out.append((int(a, 16), b))
    need = needed()
    seen, res = set(), []
    for _, ch in sorted(out):
        if ch in need and ch not in seen:
            seen.add(ch); res.append(ch)
    miss = need - seen
    assert not miss, ('kocodes 에 없는 반각 음절', ''.join(sorted(miss)))
    assert len(res) <= len(LEADS) * PER_LEAD, len(res)
    return res


def needed():
    """반각에서 실제로 쓰는 음절만(선두 3개 × 223 = 669 칸 안) — 이름 번역 + 메뉴 라벨·이름 표"""
    import csv
    import menu_labels as ML
    S = set()
    for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'trans', 'half_names.tsv'), encoding='utf-8'), delimiter='	'):
        S |= {c for c in r['번역'] if '가' <= c <= '힣'}
    import json
    for v in json.load(open(os.path.join(ROOT, 'work', 'trans', 'mdat_ko.json'), encoding='utf-8')).values():   # 적 이름·기술(반각 칸)
        S |= {c for c in v if '가' <= c <= '힣'}
    for v in list(ML.LABELS.values()) + [k for _, k in ML.NAMES]:
        S |= {c for c in v if '가' <= c <= '힣'}
    return S


_S = None


def index():
    global _S
    if _S is None:
        _S = {ch: i for i, ch in enumerate(syllables())}
    return _S


def code_of(s):
    L, k = divmod(s, PER_LEAD)
    i = 0x20 + k + (1 if k >= 0x05 else 0)     # 0x25 건너뜀
    return bytes([LEADS[L], i])


def decode_index(lead, i):
    return LEADS.index(lead) * PER_LEAD + (i - 0x20) - (1 if i > 0x25 else 0)


def encode(text):
    """한글·ASCII 혼합 → 반각 바이트열. 한글은 2바이트, ASCII(0x20~0x7E)는 그대로."""
    S = index(); out = bytearray()
    for ch in text:
        if '가' <= ch <= '힣':
            if ch not in S:
                raise KeyError('반각 한글 음절표에 없음: %r (kocodes 에 추가 필요)' % ch)
            out += code_of(S[ch])
        elif 0x20 <= ord(ch) < 0x7F:
            out.append(ord(ch))
        else:
            raise KeyError('반각으로 못 쓰는 글자: %r' % ch)
    return bytes(out)


if __name__ == '__main__':
    S = syllables(); print('음절', len(S))
    for s in (0, 1, 4, 5, 6, 222, 223, len(S) - 1):
        c = code_of(s); assert decode_index(c[0], c[1]) == s and c[1] != 0x25, s
    print('왕복 검사 통과')
