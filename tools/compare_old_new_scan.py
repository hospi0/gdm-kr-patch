# -*- coding: utf-8 -*-
"""옛 scan_runs(바이그램 추측)와 새 scan_runs(확정 규칙)를 **같은 기준**으로 비교.

기준: text_vm.decode_block 로 검증된 「깨끗한 블록」 안의 제어코드 인수 위치.
번역 대상으로 실제 채택되는 런(translatable + not noise)만 놓고, 그 런이
인수 바이트를 포함하는 개수를 센다.
"""
import os
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section, scan_skips
from text_vm import decode_block
from verify_text_vm import blocks
from verify_text_vm3 import clean_block
import codemap
from codemap_kanji_src import kanji_map

CM = codemap.base_map()
CM.update(kanji_map())
KANA = set(codemap.HIRA + codemap.KATA)
JPP = set('‥…。、・「」『』！？⁉‼～ー♪♥○※（）　 ')
MINLEN, MINRATIO, LONG_RUN = 3, 0.6, 12


def is_jp(ch):
    return ch in KANA or 0x4E00 <= ord(ch) <= 0x9FFF or ch in JPP


def text(codes):
    return ''.join(CM.get(c, '?') for c in codes)


def translatable(codes):
    t = text(codes)
    return len(t) >= MINLEN and sum(1 for c in t if is_jp(c)) / len(t) >= MINRATIO


def looks_noise(t):
    if not t:
        return True
    latin = sum(1 for c in t if c.isascii() and c.isalpha())
    if latin / len(t) > 0.08:
        return True
    if len(t) < LONG_RUN:
        return False
    if ' ' in t:
        return False
    if sum(1 for c in t if 0x4E00 <= ord(c) <= 0x9FFF or c == '・') >= 2:
        return False
    return True


def blocked_ranges(s):
    return [(sp, sp + 4) for sp, st, en, LL in scan_skips(s)]


# ---- 옛 scan_runs (세션3, 바이그램 추측 포함) ----
import pickle
with open('work/trans/bigram.pkl', 'rb') as f:
    _BG = pickle.load(f)


def _peek(s, i, n, two_first):
    out, first = [], True
    while i < n and len(out) < 8:
        b = s[i]
        if b >= 0x20:
            out.append(b - 0x20)
            i += 1
        elif 0x10 <= b <= 0x14 and i + 1 < n:
            if first and not two_first:
                i += 1
                first = False
                continue
            out.append(0xE0 + (b - 0x10) * 256 + s[i + 1])
            i += 2
        else:
            break
        first = False
    return ''.join(CM.get(x, '?') for x in out)


def _plaus(t):
    import math
    if len(t) < 2:
        return -99.0
    return sum(math.log(1 + _BG.get((a, b), 0)) for a, b in zip(t, t[1:])) / (len(t) - 1)


def lead10_is_ctrl(s, i, n):
    return _plaus(_peek(s, i, n, False)) > _plaus(_peek(s, i, n, True))


def old_scan_runs(s, blocked=()):
    block = bytearray(len(s))
    for a, b in blocked:
        for i in range(a, min(b, len(s))):
            block[i] = 1
    out, i, n = [], 0, len(s)
    cur, st = [], None
    while i < n:
        b = s[i]
        if block[i]:
            if st is not None:
                out.append((st, i - st, cur))
            cur, st = [], None
            i += 1
        elif b >= 0x20:
            if st is None:
                st = i
            cur.append(b - 0x20)
            i += 1
        elif 0x10 <= b <= 0x14 and i + 1 < n and not block[i + 1] \
                and not (st is None and lead10_is_ctrl(s, i, n)):
            if st is None:
                st = i
            cur.append(0xE0 + (b - 0x10) * 256 + s[i + 1])
            i += 2
        else:
            if st is not None:
                out.append((st, i - st, cur))
            cur, st = [], None
            i += 1
    if st is not None:
        out.append((st, n - st, cur))
    return out


# ---- 새 scan_runs ----
from extract_runs import scan_runs as new_scan_runs


def arg_offsets(sec, off, L):
    toks, _ = decode_block(sec, off, L)
    p = off
    out = set()
    for t in toks:
        if t.kind == 'ctrl' and t.arg is not None:
            out.add(p + 1)
            out.add(p + 2)
        p += len(t.raw)
    return out


def eval_scanner(scan_fn, name):
    tot = clob = chars = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        sec = d[o:o + b]
        args = set()
        for boff, L in blocks(sec):
            if clean_block(sec, boff, L) is None:
                continue
            args |= arg_offsets(sec, boff, L)
        for roff, rlen, codes in scan_fn(sec, blocked_ranges(sec)):
            if not translatable(codes):
                continue
            if looks_noise(text(codes)):
                continue
            tot += 1
            chars += len(codes)
            if any(x in args for x in range(roff, roff + rlen)):
                clob += 1
    print('%s: 번역대상 런 %d개 / 글자 %d자 / 인수 침범 %d건 (%.2f%%)'
          % (name, tot, chars, clob, 100.0 * clob / max(tot, 1)))


def main():
    eval_scanner(old_scan_runs, '옛 스캐너(바이그램 추측)')
    eval_scanner(new_scan_runs, '새 스캐너(확정 규칙)   ')


if __name__ == '__main__':
    main()
