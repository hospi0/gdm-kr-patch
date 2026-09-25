# -*- coding: utf-8 -*-
"""깨진 한글 → 원문 역추적 (실기 스샷 판독용).

폰트 슬롯 재활용 패치에서 **미번역 원문**은 원문 코드 그대로 렌더되므로
한글 글리프로 읽힌다. 화면에서 읽은 한글을 코드로 되돌려 원문을 복원한다.
[[feedback_broken_hangul_reverse_lookup]] / [[feedback_font_reuse_untranslated_looks_scrambled]]

    python tools/unbreak.py "버히역랑우크"        # 한글 -> 원문
    python tools/unbreak.py --find "オープニング"   # 원문 -> 디스크 전 파일 위치
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()
REV_KO = {}
for ch, code in KO.items():
    REV_KO.setdefault(ch, code)


def code_to_bytes(code):
    if code < 0xE0:
        return bytes([code + 0x20])
    c = code - 0xE0
    return bytes([0x10 + c // 256, c % 256])


def kr_to_src(s):
    """한글 문자열 -> (원문, 바이트열). 모르는 글자는 그대로 둔다."""
    out, raw = [], bytearray()
    for ch in s:
        code = REV_KO.get(ch)
        if code is None:
            out.append(ch)
            raw += ch.encode('utf-8', 'replace')
            continue
        raw += code_to_bytes(code)
        out.append(B.M.get(code, '?'))
    return ''.join(out), bytes(raw)


def src_to_bytes(s):
    """원문 문자열 -> 바이트열 (게임 코드)."""
    rev = {}
    for code, ch in B.M.items():
        rev.setdefault(ch, code)
    raw = bytearray()
    for ch in s:
        code = rev.get(ch)
        if code is None:
            raise KeyError(ch)
        raw += code_to_bytes(code)
    return bytes(raw)


def find_on_disc(pat, root='work/dm'):
    hits = []
    for fn in sorted(os.listdir(root)):
        d = open(os.path.join(root, fn), 'rb').read()
        i = d.find(pat)
        while i >= 0:
            hits.append((fn, i))
            i = d.find(pat, i + 1)
    return hits


def main():
    a = sys.argv[1:]
    if a and a[0] == '--find':
        for s in a[1:]:
            raw = src_to_bytes(s)
            print('%r -> %s' % (s, raw.hex(' ')))
            for fn, off in find_on_disc(raw):
                print('   %-22s 0x%05X' % (fn, off))
        return
    for s in a:
        src, raw = kr_to_src(s)
        print('%r\n  -> %r\n  -> %s' % (s, src, raw.hex(' ')))


if __name__ == '__main__':
    main()
