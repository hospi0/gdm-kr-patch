# -*- coding: utf-8 -*-
"""`extract_runs` 가 런으로 잡지 못한 **미커버 텍스트 조각**을 전수 추출한다.

★왜 필요한가 (2026-08-07 세션8에 실기로 드러난 사고):
  `runs_build.py` 는 `extract()` 가 돌려준 런을 돌면서 runs.tsv 를 **오프셋으로
  조회**한다. 그래서 런으로 잡히지 않은 자리는 runs.tsv 에 행을 넣어도
  **조용히 버려진다**. 세션7의 「미추출 문장 45건 병합」은 실제로 아무 일도
  하지 않았고, 실기에서 대사 한 줄만 원문으로 남아 깨져 보였다.
  → 미커버 조각은 별도 경로(`patch_missed.py`)로 **직접 오프셋 기록**해야 한다.

조각 판정:
  · 텍스트 구간(`extract` 가 돌려준 s) 안에서 런이 덮지 않은 바이트 구간을 잡고
  · 제어 바이트(<0x10)로 잘라 세그먼트를 만든다
    ⚠️ 2바이트 글자(선두 0x10~0x1F)의 **둘째 바이트가 0x00~0x0F 일 수 있으므로**
       반드시 코덱을 따라가며 잘라야 한다.
  · 가나·한자 비율과 히라가나 개수로 진짜 문장만 남긴다
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap
from extract_runs import extract

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
PUNCT = set('　！？、。・‥…～「」『』（）♥♪♩○◆★§：‼⁉々')
LATIN = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ')


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def segments(s, lo, hi):
    """[(off, len)] — 제어 바이트로 끊은 텍스트 세그먼트 (코덱 인식)."""
    out = []
    i = lo
    start = None
    while i < hi:
        b = s[i]
        if 0x10 <= b <= 0x1F and i + 1 < hi:
            if start is None:
                start = i
            i += 2
            continue
        if b < 0x10:
            if start is not None:
                out.append((start, i - start))
                start = None
            i += 1
            continue
        if start is None:
            start = i
        i += 1
    if start is not None:
        out.append((start, hi - start))
    return out


def decode(raw):
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if 0x10 <= b <= 0x1F and i + 1 < len(raw):
            out.append(B.M.get(0xE0 + (b - 0x10) * 256 + raw[i + 1], '�'))
            i += 2
            continue
        out.append(B.M.get(b - 0x20, '�') if b >= 0x20 else '�')
        i += 1
    return ''.join(out)


def real(t):
    core = t.strip('　 ')
    if len(core) < 4 or '�' in core:
        return False
    hira = sum(1 for c in core if c in HIRA)
    kata = sum(1 for c in core if c in KATA)
    kanji = sum(1 for c in core if is_kanji(c))
    ok = sum(1 for c in core
             if c in HIRA or c in KATA or is_kanji(c) or c in PUNCT or c in LATIN)
    if ok != len(core):
        return False
    if max(core.count(c) for c in set(core)) / len(core) > 0.5:
        return False
    return hira >= 2 or (kanji >= 2 and kata + hira >= 1) or (kata >= 4 and kanji >= 1)


def scan(root='work/dm'):
    """[(file, off, len, jp)] — off 는 텍스트 구간 s 기준(runs.tsv 와 같은 좌표)."""
    out = []
    for f in sorted(os.listdir(root)):
        if not f.endswith('.MDT'):
            continue
        name = f[6:]
        d = open(os.path.join(root, f), 'rb').read()
        base, s, rs = extract(d, name)
        if not rs:
            continue                       # 런 0개 = 노이즈 파일
        cov = bytearray(len(s))
        for off, L, _ in rs:
            cov[off:off + L] = b'\x01' * min(L, len(s) - off)
        i = 0
        while i < len(s):
            if cov[i]:
                i += 1
                continue
            j = i
            while j < len(s) and not cov[j]:
                j += 1
            for so, sl in segments(s, i, j):
                t = decode(s[so:so + sl])
                if real(t):
                    out.append((name, so, sl, t))
            i = j
    return out


def main():
    hits = scan()
    print('미커버 실문장 %d건' % len(hits))
    cur = None
    for name, off, L, t in hits:
        if name != cur:
            print('\n### %s' % name)
            cur = name
        print('  +0x%05X len=%3d  %s' % (off, L, t))
    with open('work/trans/uncovered.tsv', 'w', encoding='utf-8') as f:
        f.write('file\toff\tlen\tja\tko\n')
        for name, off, L, t in hits:
            f.write('%s\t%05X\t%d\t%s\t\n' % (name, off, L, t))
    print('\n-> work/trans/uncovered.tsv')


if __name__ == '__main__':
    main()
