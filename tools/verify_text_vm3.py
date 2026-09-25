# -*- coding: utf-8 -*-
"""text_vm 검산 3차 — 스캔 통계를 접고 **깨끗한 블록의 본문을 직접 대조**한다.

1·2차는 선형 스캔 후보에 3D 데이터 노이즈가 압도적이라 통계가 무의미했다
([[feedback_terra_verify_by_render_not_scan]] 의 그 함정).

여기서는 판정 기준을 「진짜 텍스트 블록의 지문」으로 좁힌다:

  · 새 규칙으로 정확히 끝에서 끝나고
  · 표 밖 글리프 0개이고
  · 마지막 토큰이 제어코드 0x07(종단)이고
  · 일본어 글자 비율이 높다

이 조건을 통과한 블록에 대해서만, **옛 §9 규칙이 같은 본문을 내는지** 대조한다.
"""
import os
import struct
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from text_vm import decode_block, GLYPH_MAX
from verify_text_vm import CM, blocks, OLD_LEN, render
import codemap

KANA = set(codemap.HIRA + codemap.KATA)
JPP = set('‥…。、・「」『』！？⁉‼～ー♪♥○※（）　 ')


def is_jp(ch):
    return ch in KANA or 0x4E00 <= ord(ch) <= 0x9FFF or ch in JPP


def clean_block(sec, off, L):
    """진짜 텍스트 블록이면 토큰목록, 아니면 None."""
    try:
        toks, end = decode_block(sec, off, L)
    except IndexError:
        return None
    if end != off + L:
        return None
    chars = [t for t in toks if t.kind == 'char']
    if not chars or any(not (0 <= t.code < GLYPH_MAX) for t in chars):
        return None
    if toks[-1].kind != 'ctrl' or toks[-1].code != 0x07:
        return None
    txt = [CM.get(t.code, '〓') for t in chars]
    if len(txt) < 4:
        return None
    if sum(1 for c in txt if is_jp(c)) / len(txt) < 0.8:
        return None
    return toks


def old_render(sec, off, L):
    """옛 §9 규칙으로 같은 구간을 읽어 본문 문자열을 낸다. 파싱 실패면 None."""
    p, end = off, off + L
    out = []
    while p < end:
        b = sec[p]
        if b >= 0x20:
            out.append(CM.get(b - 0x20, '〓'))
            p += 1
        elif 0x10 <= b <= 0x14:
            if p + 1 >= end:
                return None
            out.append(CM.get(0xE0 + (b - 0x10) * 256 + sec[p + 1], '〓'))
            p += 2
        else:
            n = OLD_LEN.get(b)
            if n is None:
                return None
            if b == 0x01:
                out.append('\\n')
            p += n
    return None if p != end else ''.join(out)


def new_text(toks):
    out = []
    for t in toks:
        if t.kind == 'char':
            out.append(CM.get(t.code, '〓'))
        elif t.code == 0x01:
            out.append('\\n')
    return ''.join(out)


def main():
    root = 'work/dm'
    files = sorted(f for f in os.listdir(root) if f.startswith('FIELD_') and f.endswith('.MDT'))
    nblk = nchar = 0
    same = diff = failed = 0
    samples = []
    for f in files:
        d = open(os.path.join(root, f), 'rb').read()
        r = script_section(d)
        if not r:
            continue
        o, b, _ = r
        sec = d[o:o + b]
        for off, L in blocks(sec):
            toks = clean_block(sec, off, L)
            if toks is None:
                continue
            nblk += 1
            nt = new_text(toks)
            nchar += len(nt)
            ot = old_render(sec, off, L)
            if ot is None:
                failed += 1
            elif ot == nt:
                same += 1
            else:
                diff += 1
                if len(samples) < 8:
                    samples.append((f[6:], off, nt, ot))
    print('진짜 텍스트 블록 %d개 / 글자 %d자' % (nblk, nchar))
    print('  옛 규칙과 본문 동일  : %d (%.1f%%)' % (same, 100.0 * same / max(nblk, 1)))
    print('  옛 규칙이 다르게 읽음: %d (%.1f%%)' % (diff, 100.0 * diff / max(nblk, 1)))
    print('  옛 규칙이 파싱 실패  : %d (%.1f%%)' % (failed, 100.0 * failed / max(nblk, 1)))
    print()
    for f, off, nt, ot in samples:
        print('%s +0x%X' % (f, off))
        print('  새: %s' % nt[:100])
        print('  옛: %s' % ot[:100])


if __name__ == '__main__':
    main()
