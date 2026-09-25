# -*- coding: utf-8 -*-
"""**미번역 최종 검출** — 원본과 «바이트가 같은» 자리를 원문 코드로 읽는다.

★두 번 틀린 방식(쓰지 말 것):
  1) 추출기(런) 기준 검사 → 순환논리. 추출기가 놓친 자리는 영원히 안 잡힌다.
  2) 한글 우선 디코드로 「가나가 남았나」 보기 → **미번역 원문이 한글로 읽힌다**.
     폰트 슬롯을 재활용했으므로 원문 1바이트 코드는 이제 한글 음절을 가리킨다.
     실기에서 「C용것크오 맥한데」로 보이던 자리를 이 방식은 0건으로 보고했다.

옳은 판정: 번역된 자리는 바이트가 바뀐다. 그러니
  «빌드 == 원본» 인 구간을 원문 코드표로 디코드해서 진짜 일본어면 미번역이다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap
from extract_runs import extract

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
NOISE = {'0000.MDT', '0004.MDT', 'EC08.MDT', 'E8FF.MDT'}


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def decode(raw):
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b < 0x10:
            out.append('\x00')
            i += 1
            continue
        if 0x10 <= b <= 0x1F and i + 1 < len(raw):
            out.append(B.M.get(0xE0 + (b - 0x10) * 256 + raw[i + 1], '\x01'))
            i += 2
            continue
        out.append(B.M.get(b - 0x20, '\x01'))
        i += 1
    return ''.join(out)


def main():
    minjp = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    total = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT') or f[6:] in NOISE:
            continue
        name = f[6:]
        orig = open('work/dm/' + f, 'rb').read()
        new = open('work/build/' + f, 'rb').read()
        base, s, rs = extract(orig, name)
        if not rs:
            continue
        lo, hi = base, base + len(s)
        hits = []
        i = lo
        while i < hi:
            if orig[i] != new[i]:
                i += 1
                continue
            j = i
            while j < hi and orig[j] == new[j]:
                j += 1
            t = decode(orig[i:j])
            # 같은 구간 안에서 «연속 일본어» 조각만 뽑는다
            k = 0
            while k < len(t):
                if not (t[k] in HIRA or t[k] in KATA or is_kanji(t[k])):
                    k += 1
                    continue
                m = k
                while m < len(t) and (t[m] in HIRA or t[m] in KATA or is_kanji(t[m])):
                    m += 1
                if m - k >= minjp:
                    hits.append((i, t[max(0, k - 4):m + 4]))
                k = m
            i = j
        if hits:
            total += len(hits)
            print('\n### %-10s (%d)' % (name, len(hits)))
            seen = set()
            for off, frag in hits:
                key = frag.strip()
                if key in seen:
                    continue
                seen.add(key)
                print('   0x%05X  %s' % (off, frag.replace('\x00', '|').replace('\x01', '?')))
    print('\n총 미번역 %d건' % total)


if __name__ == '__main__':
    main()
