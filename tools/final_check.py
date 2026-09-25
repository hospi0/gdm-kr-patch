# -*- coding: utf-8 -*-
"""**전 파일 최종 미번역 검사** — 원본↔빌드 바이트 차분 기준.

판정 규칙 ([[feedback_untranslated_detector_byte_diff]]):
  «빌드 == 원본» 인 구간을 원문 코드표로 디코드해 일본어가 연속으로 나오면 미번역.

★가타카나만 있는 줄을 놓치지 말 것 — `ム～～ ム～～～～` 같은 의성어는
  히라가나가 0개라 「히라가나 N자 이상」 필터에 전부 걸러진다. 실기 제보로 두 번 겪었다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap
from find_uncovered import segments

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
NOISE_MDT = {'0000.MDT', '0004.MDT', 'EC08.MDT', 'E8FF.MDT'}

# (파일, [(lo,hi)…]) — 텍스트 구간이 확정된 파일
RANGES = {
    'FIELD_FACE2.DAT': [(0x0049C, 0x01258), (0x0165C, 0x03EBC), (0x03EC8, 0x03F0C)],
    'FIELD_DORAM.BIN': [(0x0AC00, 0x0ACB0)],
}


def isjp(c):
    return c in HIRA or c in KATA or 0x4E00 <= ord(c) <= 0x9FFF


def decode(raw):
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if 0x10 <= b <= 0x1F and i + 1 < len(raw):
            out.append(B.M.get(0xE0 + (b - 0x10) * 256 + raw[i + 1], '\x01'))
            i += 2
            continue
        out.append(B.M.get(b - 0x20, '\x01') if b >= 0x20 else '\x00')
        i += 1
    return ''.join(out)


def check_ranges():
    bad = []
    for fn, rs in RANGES.items():
        o = open('work/dm_all/' + fn, 'rb').read()
        n = open('work/build/' + fn, 'rb').read()
        for lo, hi in rs:
            for so, sl in segments(o, lo, hi):
                t = decode(o[so:so + sl])
                if sum(1 for c in t if isjp(c)) >= 2 and o[so:so + sl] == n[so:so + sl]:
                    bad.append((fn, so, t))
    return bad


def check_museum():
    from museum import SPECS, bounds, strings
    bad = []
    for fn, spec in SPECS.items():
        o = open('work/dm/' + fn, 'rb').read()
        n = open('work/build/' + fn, 'rb').read()
        for name, lo, hi in bounds(o, spec):
            for off, L, t in strings(o, lo, hi):
                if L and sum(1 for c in t if isjp(c)) >= 2 and o[off:off + L] == n[off:off + L]:
                    bad.append((fn, off, t))
    return bad


def check_mdt(minjp=3):
    from extract_runs import extract
    bad = []
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT') or f[6:] in NOISE_MDT:
            continue
        name = f[6:]
        o = open('work/dm/' + f, 'rb').read()
        n = open('work/build/' + f, 'rb').read()
        base, s, rs = extract(o, name)
        if not rs:
            continue
        lo, hi = base, base + len(s)
        i = lo
        while i < hi:
            if o[i] != n[i]:
                i += 1
                continue
            j = i
            while j < hi and o[j] == n[j]:
                j += 1
            t = decode(o[i:j])
            k = 0
            while k < len(t):
                if not isjp(t[k]):
                    k += 1
                    continue
                m = k
                while m < len(t) and isjp(t[m]):
                    m += 1
                if m - k >= minjp:
                    frag = t[max(0, k - 4):m + 4]
                    if not any(x in frag for x in ('ぬ', 'ぼ敷', 'ぼ?', '回え', '左F', '左G')):
                        bad.append((name, i, frag))
                k = m
            i = j
    return bad


def main():
    for tag, rows in (('구간지정(FACE2/DORAM)', check_ranges()),
                      ('박물관(DICDT/MTMES/MTOUT)', check_museum()),
                      ('대사 MDT', check_mdt())):
        print('\n=== %s : %d건' % (tag, len(rows)))
        for r in rows[:25]:
            print('   %-18s 0x%05X  %s' % (r[0], r[1], r[2]))


if __name__ == '__main__':
    main()
