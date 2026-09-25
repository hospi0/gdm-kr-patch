# -*- coding: utf-8 -*-
"""미조사 파일에서 **문자열 표**를 찾는다 (2026-08-07 세션8).

단건 판정은 압축·그래픽 데이터에서 무한히 오검출된다(SCNRL/MTOUT 실측).
진짜 문자열 표는 «깨끗한 문자열이 연속으로 뭉쳐» 있다 — 클러스터 조건을
걸면 노이즈가 사라진다. [[feedback_scan_coverage_and_detectors]]

    python tools/find_text_tables.py            # 미조사 파일 전부
    python tools/find_text_tables.py DICDT      # 이름에 DICDT 포함된 것만
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap
import halfwidth as H

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
PUNCT = set('　！？、。・：‥…～「」『』（）♥♪♩○◆★§')
LATIN = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

MIN_CLUSTER = 6      # 연속 실문자열 개수
MIN_LEN = 3


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def dec(raw):
    out = []
    half = False
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0x03:
            half = True
            i += 1
            continue
        if b == 0x04:
            half = False
            i += 1
            continue
        if b < 0x10:
            out.append('\x01')
            i += 1
            continue
        if half:
            out.append(H.IDX2CH.get(b - 0x20, '\x02'))
            i += 1
            continue
        if 0x10 <= b <= 0x1F and i + 1 < len(raw):
            out.append(B.M.get(0xE0 + (b - 0x10) * 256 + raw[i + 1], '\x02'))
            i += 2
            continue
        out.append(B.M.get(b - 0x20, '\x02'))
        i += 1
    return ''.join(out)


def clean(t):
    """제어·미매핑이 하나도 없고 일본어 비율이 높은가."""
    if '\x01' in t or '\x02' in t:
        return False
    core = t.strip('　 ')
    if len(core) < MIN_LEN:
        return False
    jp = sum(1 for c in core if c in HIRA or c in KATA or is_kanji(c))
    ok = sum(1 for c in core
             if c in HIRA or c in KATA or is_kanji(c) or c in PUNCT or c in LATIN or c in '　 ')
    if ok != len(core):
        return False
    return jp >= 2


def strings(d):
    out = []
    i = 0
    n = len(d)
    while i < n:
        if d[i] == 0:
            i += 1
            continue
        j = i
        while j < n and d[j] != 0:
            j += 1
        out.append((i, d[i:j]))
        i = j
    return out


def tables(d):
    """[(시작오프셋, [(off, len, text)…])] — 연속 클러스터만."""
    items = [(o, len(r), dec(r)) for o, r in strings(d)]
    res = []
    run = []
    for it in items:
        if clean(it[2]):
            run.append(it)
        else:
            if len(run) >= MIN_CLUSTER:
                res.append(run)
            run = []
    if len(run) >= MIN_CLUSTER:
        res.append(run)
    return res


def main():
    touched = set(os.listdir('work/build')) if os.path.isdir('work/build') else set()
    only = sys.argv[1:]
    root = 'work/dm'
    total = 0
    for fn in sorted(os.listdir(root)):
        if fn == 'bbg_region.bin':
            continue
        if only:
            if not any(o in fn for o in only):
                continue
        elif fn in touched:
            continue
        d = open(os.path.join(root, fn), 'rb').read()
        tt = tables(d)
        if not tt:
            continue
        n = sum(len(t) for t in tt)
        total += n
        print('\n########## %-20s %8d B   표 %d개 / 문자열 %d' % (fn, len(d), len(tt), n))
        for t in tt:
            print('  --- 0x%05X ~ 0x%05X  (%d개)' % (t[0][0], t[-1][0] + t[-1][1], len(t)))
            for off, ln, s in t[:12]:
                print('      0x%05X len=%3d  %s' % (off, ln, s))
            if len(t) > 12:
                print('      … 외 %d' % (len(t) - 12))
    print('\n총 문자열 %d' % total)


if __name__ == '__main__':
    main()
