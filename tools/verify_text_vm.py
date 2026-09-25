# -*- coding: utf-8 -*-
"""text_vm 디코더를 실제 데이터로 검산한다.

두 가지를 본다.

1. **알려진 블록**(E800 스크립트 +0x108, 워드 0x201A) 이 정확히 끝에서 끝나는가.
2. 전 MDT 의 op2 후보 블록을 새 규칙과 옛 규칙(§9 길이표)으로 각각 파싱해
   **정렬 성공률·표 밖 글리프 수**를 비교한다.

옛 규칙이 맞다면 두 결과가 비슷할 것이고, 새 규칙이 맞다면 새 쪽만 깨끗해야 한다.
"""
import os
import struct
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section
from text_vm import decode_block, GLYPH_MAX

CM = codemap.base_map()
CM.update(kanji_map())

# §9 의 옛 제어코드 길이표 (틀렸다고 의심되는 쪽)
OLD_LEN = {}
for c in (0x01, 0x02, 0x05, 0x06, 0x07, 0x09, 0x0B, 0x1A):
    OLD_LEN[c] = 1
for c in (0x00, 0x03, 0x04, 0x08, 0x0A, 0x0D, 0x15, 0x16, 0x17, 0x18, 0x19,
          0x1B, 0x1C, 0x1D, 0x1E, 0x1F):
    OLD_LEN[c] = 2
for c in (0x0C, 0x0E, 0x0F):
    OLD_LEN[c] = 3


def old_parse(buf, off, length):
    """옛 규칙: 0x10~0x14 만 2바이트 글자, 나머지 <0x20 은 위 길이표대로 제어코드."""
    p, end = off, off + length
    bad = 0
    while p < end:
        b = buf[p]
        if b >= 0x20:
            p += 1
        elif 0x10 <= b <= 0x14:
            if p + 1 >= end:
                return None, bad
            g = 0xE0 + (b - 0x10) * 256 + buf[p + 1]
            if g >= GLYPH_MAX:
                bad += 1
            p += 2
        else:
            n = OLD_LEN.get(b)
            if n is None:
                return None, bad
            p += n
    return p == end, bad


def new_parse(buf, off, length):
    try:
        toks, p = decode_block(buf, off, length)
    except IndexError:
        return None, 0
    bad = sum(1 for t in toks if t.kind == 'char' and not (0 <= t.code < GLYPH_MAX))
    return p == off + length, bad


def render(toks):
    out = []
    for t in toks:
        if t.kind == 'char':
            out.append(CM.get(t.code, '〓'))
        elif t.code == 0x01:
            out.append('\\n')
        else:
            out.append('{%02X%s}' % (t.code, '' if t.arg is None else ':%04X' % t.arg))
    return ''.join(out)


def blocks(sec):
    """op2 후보를 선형 스캔한다 (워드 정렬, 상위 니블 2, 길이 1 이상)."""
    out = []
    for i in range(0, len(sec) - 1, 2):
        w = struct.unpack_from('>H', sec, i)[0]
        if (w >> 12) == 2:
            L = w & 0x0FFF
            if 2 <= L and i + 2 + L <= len(sec):
                out.append((i + 2, L))
    return out


def main():
    root = 'work/dm'
    files = sorted(f for f in os.listdir(root) if f.startswith('FIELD_') and f.endswith('.MDT'))

    # 1) 알려진 블록
    d = open(os.path.join(root, 'FIELD_E800.MDT'), 'rb').read()
    o, b, _ = script_section(d)
    sec = d[o:o + b]
    w = struct.unpack_from('>H', sec, 0x108)[0]
    print('E800 스크립트 +0x108 워드 = 0x%04X (op=%d, L=%d)' % (w, w >> 12, w & 0xFFF))
    toks, end = decode_block(sec, 0x10A, w & 0xFFF)
    print('  끝위치 0x%X (기대 0x%X) → %s' % (end, 0x10A + (w & 0xFFF),
                                              '정렬 OK' if end == 0x10A + (w & 0xFFF) else '★정렬 실패'))
    print('  본문:', render(toks))
    print()

    # 2) 전수 비교
    tot = nok = nbad = ook = obad = 0
    for f in files:
        d = open(os.path.join(root, f), 'rb').read()
        r = script_section(d)
        if not r:
            continue
        o, b, _ = r
        sec = d[o:o + b]
        for off, L in blocks(sec):
            tot += 1
            a1, b1 = new_parse(sec, off, L)
            a2, b2 = old_parse(sec, off, L)
            nok += 1 if a1 else 0
            nbad += b1
            ook += 1 if a2 else 0
            obad += b2
    print('op2 후보 블록 %d개' % tot)
    print('  새 규칙: 정렬 성공 %d (%.1f%%) / 표 밖 글리프 %d' % (nok, 100.0 * nok / max(tot, 1), nbad))
    print('  옛 규칙: 정렬 성공 %d (%.1f%%) / 표 밖 글리프 %d' % (ook, 100.0 * ook / max(tot, 1), obad))


if __name__ == '__main__':
    main()
