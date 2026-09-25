# -*- coding: utf-8 -*-
"""`*.BIN` 문자열표(UI 용어·아이템명·설명) 추출/재삽입.

## 포맷 (2026-08-05 세션6 실측, FIELD_TEXT2.BIN)

    0x0000  32비트 BE 오프셋 N개          ← 선두 포인터표
    ...     널(0x00) 종단 문자열들

`N = 첫_오프셋 / 4` (첫 오프셋이 곧 표 바로 다음 = 데이터 시작).
문자 인코딩은 MDT 와 **같은 글리프 색인**(1B: 코드+0x20 / 2B: 0x10~0x1F 선두).

⚠️ 앞쪽 구역들은 텍스트가 아니라 데이터라 맹목 디코드하면 가타카나 노이즈가 된다
   (`チラソゼヅゼL` 류). `real_jp()` 로 거른다.

## 왜 필요한가 (세션6)

`/FIELD/*.MDT` 대사만 번역하고 이 파일들을 놔뒀더니, 한글에 내준 글리프 슬롯
(예 250=`道` 251=`具` 247=`使`)을 UI 가 그대로 참조해 **화면에 `령또`(=道具),
`갈가`(=使う) 로 떴다.** 슬롯을 되돌릴 수는 없으므로(이미 827음절이 쓰는 중)
**UI 도 같이 번역하는 것이 유일한 해법**이다.
"""
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_build import PUNCT_FALLBACK

M = codemap.base_map()
M.update(kanji_map())
REV = {}
for _c, _ch in sorted(M.items()):
    REV.setdefault(_ch, _c)

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
JPP = set('‥…。、・「」『』！？⁉‼～ー♪♥○※（）　 ')


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def decode(bs):
    out, i = [], 0
    while i < len(bs):
        b = bs[i]
        if b >= 0x20:
            out.append(M.get(b - 0x20, '?'))
            i += 1
        elif 0x10 <= b <= 0x1F and i + 1 < len(bs):
            out.append(M.get(0xE0 + (b - 0x10) * 256 + bs[i + 1], '?'))
            i += 2
        else:
            out.append('�')
            i += 1
    return ''.join(out)


def real_jp(t):
    """진짜 일본어 문자열인가 (데이터 구역이 우연히 가나로 읽힌 것과 구별)."""
    import re
    t = re.sub(r'\{[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\}', '', t)
    if len(t) < 2 or '?' in t or '�' in t:
        return False
    hira = sum(1 for c in t if c in HIRA)
    kan = sum(1 for c in t if is_kanji(c))
    kat = sum(1 for c in t if c in KATA)
    oth = sum(1 for c in t if c in JPP or c.isdigit() or c == '─' or c == '十')
    if hira + kan + kat + oth < len(t):
        return False
    if hira == 0 and kan == 0:
        # 가타카나만: 진짜 외래어 이름은 장음·중점이 섞이거나 짧다
        return 'ー' in t or '・' in t or len(t) <= 6
    return True


def sections(d):
    """선두 포인터표를 읽어 구역 경계 목록을 낸다."""
    first = int.from_bytes(d[0:4], 'big')
    if first < 8 or first > len(d) or first % 4:
        return []
    n = first // 4
    offs = [int.from_bytes(d[i * 4:i * 4 + 4], 'big') for i in range(n)]
    if any(not (0 < o <= len(d)) for o in offs):
        return []
    if offs != sorted(offs):
        return []
    return offs


FIRST_TEXT_SEC = 3
"""★구역 0~2 는 **반각 가타카나**(별도 글리프 집합)라 건드리지 않는다.

실측: 구역0 `ca df 90 c3 a8 90` 은 우리 전각표로 읽으면 `フリれノコれ` 쓰레기지만,
반각(JIS X0201 계열 커스텀)으로 보면 `ﾊﾟ_ﾃｨ_` = 구역3 의 `パーティー` 와 같은 말이다.
반각 글리프는 한글 배정에서 손대지 않았으므로 **화면에 일본어로 정상 표시**된다
= 이번 UI 깨짐의 원인이 아니다. 전각을 쓰는 구역 3 부터가 대상이다.
"""


def encode(s, ko=None):
    ko = ko or {}
    out = bytearray()
    for ch in s:
        c = ko.get(ch, REV.get(ch))
        if c is None and ch in PUNCT_FALLBACK:
            t = PUNCT_FALLBACK[ch]
            c = ko.get(t, REV.get(t))
        if c is None:
            raise KeyError(ch)
        if c < 0xE0:
            out.append(c + 0x20)
        else:
            k = c - 0xE0
            out += bytes((0x10 + k // 256, k % 256))
    return bytes(out)


def split_var_tokens(raw):
    """원바이트를 [(kind, payload)] 로 쪼갠다.

    kind='text' → payload=바이트(디코드 대상) / kind='var' → payload=`\x03 XX \x04`
    통짜(그대로 보존, 번역 대상 아님).
    """
    out, i, n = [], 0, len(raw)
    buf = bytearray()
    while i < n:
        if raw[i] == 0x03 and i + 2 < n and raw[i + 2] == 0x04:
            if buf:
                out.append(('text', bytes(buf)))
                buf = bytearray()
            out.append(('var', bytes(raw[i:i + 3])))
            i += 3
        else:
            buf.append(raw[i])
            i += 1
    if buf:
        out.append(('text', bytes(buf)))
    return out


def decode_with_vars(raw):
    """`{03:22}` 형태 토큰을 남기며 디코드 — 번역 원문용."""
    parts = []
    for kind, payload in split_var_tokens(raw):
        if kind == 'text':
            parts.append(decode(payload))
        else:
            parts.append('{%02X:%02X}' % (payload[0], payload[1]))
    return ''.join(parts)


def encode_with_vars(s, ko=None):
    """`decode_with_vars` 의 역. `{03:22}` 토큰을 그대로 3바이트로 되돌린다."""
    import re
    out = bytearray()
    pos = 0
    for mo in re.finditer(r'\{([0-9A-Fa-f]{2}):([0-9A-Fa-f]{2})\}', s):
        out += encode(s[pos:mo.start()], ko)
        out += bytes((int(mo.group(1), 16), int(mo.group(2), 16), 0x04))
        pos = mo.end()
    out += encode(s[pos:], ko)
    return bytes(out)


def extract(d):
    """[(오프셋, 바이트길이, 원문)] — 전각 텍스트 구역의 진짜 일본어 문자열만."""
    offs = sections(d)
    if not offs or len(offs) <= FIRST_TEXT_SEC:
        return []
    out = []
    i = offs[FIRST_TEXT_SEC]
    while i < len(d):
        j = i
        while j < len(d) and d[j] != 0:
            j += 1
        if j > i:
            t = decode_with_vars(d[i:j])
            if t != '?????????' and real_jp(t):
                out.append((i, j - i, t))
        i = j + 1
    return out


def rebuild(d, trans, ko=None):
    """번역을 반영한 새 바이트열을 만든다 — **개별 문자열 제자리 교체**.

    trans: {off: ko문자열} — off 는 `extract()` 가 낸 원본 오프셋과 정확히 같아야 한다.
    정책: MDT 런 빌더(`runs_build.py`)와 동일 — 각 문자열은 **원래 널종단 구간
    길이를 넘지 않는 한도 안에서** 제자리 교체하고, 남는 자리는 `0x00` 패딩.
    (섹션 전체를 다시 눌러 담지 않는다 — 그러면 오프셋이 죄다 밀려 검증이
    복잡해지고, 애초에 한글이 항상 더 짧아 개별 여유로 충분하다.)
    개별 문자열이 넘치면 KeyError 아닌 `ValueError` 로 실패시킨다(조용히 안 자름).
    """
    out = bytearray(d)
    for off, ko_text in trans.items():
        j = off
        while j < len(d) and d[j] != 0:
            j += 1
        L = j - off
        try:
            nb = encode_with_vars(ko_text, ko)
        except KeyError as e:
            raise KeyError('%s (off 0x%X, 텍스트 %r)' % (e, off, ko_text))
        if len(nb) > L:
            raise ValueError('0x%X 초과: %dB > %dB  %r' % (off, len(nb), L, ko_text))
        out[off:off + len(nb)] = nb
        # ★★패딩은 널이 아니라 **공백(0x20)** 이어야 한다.
        #   소비자가 **널을 세며 N번째 문자열**을 찾는 구조(예: FIELD_CMDMN.BIN
        #   0x160F8 의 인덱스표)라, 널로 패딩하면 빈 문자열이 하나 끼어들어
        #   그 뒤 순번이 전부 밀린다 → 메뉴가 군데군데 빈칸으로 나온다
        #   (2026-08-07 실기 확인. 원본도 `使う `·`変更 ` 처럼 공백으로 채워 둔다).
        out[off + len(nb):j] = b'\x20' * (L - len(nb))
    return bytes(out)
