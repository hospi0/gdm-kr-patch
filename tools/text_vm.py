# -*- coding: utf-8 -*-
"""블록 내부 텍스트 디코더 — 인터프리터에서 그대로 옮긴 것 (추측 아님).

출처: `0x0601D5A4`(바이트 디코더) + `0x0601D4E2`(글자/제어 판정) + `0x0601DBFE`(글리프 색인).

    p = *(0x06021CFC); b = *p++; tok = b
    if b >= 0x0A:
        if   b < 0x10:  인수 = (*p++ << 8) | *p++     # 제어코드 + 2바이트 인수
        elif b < 0x20:  tok  = ((b - 0x0F) << 8) | *p++  # 2바이트 글자
        else:           pass                          # 1바이트 글자
    *(0x06021CFC) = p

    호출부:  tok >= 0x10 → 글자(글리프 색인 = tok - 0x20) / tok < 0x10 → 제어코드

따라서 **확정**:
    0x00~0x09  제어코드, 총 1바이트
    0x0A~0x0F  제어코드, 총 3바이트 (2바이트 인수)
    0x10~0x1F  2바이트 글자 선두 (글리프 = 0xE0 + (b-0x10)*256 + 다음바이트)
    0x20~0xFF  1바이트 글자 (글리프 = b - 0x20)

글리프 슬롯이 정확히 1,504 = 0xE0 + 5*256 이므로 실제로 쓰이는 선두는 0x10~0x14뿐이다
(0x15 이상은 색인이 표 밖으로 나간다 → 유효한 텍스트에는 나올 수 없다).
"""

CTRL_MAX = 0x0A          # 이 미만은 인수 없음
LEAD_MIN = 0x10          # 이상은 글자
CHAR1_MIN = 0x20         # 이상은 1바이트 글자
GLYPH_MAX = 1504         # 폰트 슬롯 수


class Tok:
    """디코드 결과 하나."""
    __slots__ = ('kind', 'code', 'arg', 'raw')

    def __init__(self, kind, code, arg, raw):
        self.kind = kind      # 'char' | 'ctrl'
        self.code = code      # char면 글리프 색인, ctrl이면 제어코드 값
        self.arg = arg        # ctrl 2바이트 인수 (없으면 None)
        self.raw = raw        # 소비한 원본 바이트열

    def __repr__(self):
        if self.kind == 'char':
            return 'char(0x%03X)' % self.code
        return 'ctrl(%02X%s)' % (self.code, '' if self.arg is None else ' %04X' % self.arg)


def decode_one(buf, p):
    """`0x0601D5A4` 한 번 호출. (Tok, 다음위치) 를 낸다."""
    start = p
    b = buf[p]
    p += 1
    tok = b
    arg = None
    if b >= CTRL_MAX:
        if b < LEAD_MIN:                       # 0x0A~0x0F
            arg = (buf[p] << 8) | buf[p + 1]
            p += 2
        elif b < CHAR1_MIN:                    # 0x10~0x1F
            tok = ((b - 0x0F) << 8) | buf[p]
            p += 1
    if tok >= LEAD_MIN:
        return Tok('char', tok - 0x20, None, buf[start:p]), p
    return Tok('ctrl', tok, arg, buf[start:p]), p


def decode_block(buf, off, length):
    """블록 하나를 전부 디코드한다.

    낸다: (토큰목록, 끝위치). 끝위치가 off+length 와 다르면 **정렬 실패**다.
    """
    toks = []
    p = off
    end = off + length
    while p < end:
        t, p = decode_one(buf, p)
        toks.append(t)
    return toks, p


def scan_candidates(buf):
    """op2(텍스트) 헤더 후보 — **워드 정렬**로 `2LLL` 워드를 전수 스캔한다.

    인터프리터가 명령을 읽는 방식과 같다(BE16 워드 스트림, `MOV.W @R5+`).
    이 자체는 후보일 뿐이다 — VM 명령 스트림·3D 데이터 안에도 우연히 상위
    니블이 2인 워드가 섞이므로, 실제 텍스트인지는 `decode_block` 결과를
    (진짜 끝에서 끝나는지·글리프가 표 안인지 등으로) 별도로 검증해야 한다.
    """
    out = []
    n = len(buf)
    for i in range(0, n - 1, 2):
        w = (buf[i] << 8) | buf[i + 1]
        if (w >> 12) == 2:
            L = w & 0x0FFF
            if L >= 2 and i + 2 + L <= n:
                out.append((i + 2, L))
    return out
