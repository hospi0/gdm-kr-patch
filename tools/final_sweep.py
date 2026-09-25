# -*- coding: utf-8 -*-
"""**결정적 미번역 검사** — 빌드본에 히라가나가 남아 있는 자리를 전부 찾는다.

원리: 번역된 자리는 한글 코드가 들어가 있으므로 kocodes 우선 디코드하면
한글로 읽힌다. 그러니 **빌드본에서 히라가나가 연달아 나오면 그 자리는 미번역**이다.
추출기가 런으로 잡았든 못 잡았든 상관없이 잡힌다 —
「추출기 기준으로 검사」하는 순환논리(세션7의 audit_runs)를 피하려는 것.

노이즈 파일(런 0개)은 스크립트 바이트가 우연히 가나로 읽히므로 제외한다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap
from extract_runs import extract
from runs_build import load_maps

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
_, KO = load_maps()
REV = {v: k for k, v in KO.items()}


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
            c = 0xE0 + (b - 0x10) * 256 + raw[i + 1]
            i += 2
        else:
            c = b - 0x20
            i += 1
        out.append(REV.get(c) or B.M.get(c, '\x01'))
    return ''.join(out)


def main():
    minrun = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    total = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        name = f[6:]
        orig = open('work/dm/' + f, 'rb').read()
        base, s0, rs = extract(orig, name)
        if not rs:
            continue                      # 노이즈 파일
        new = open('work/build/' + f, 'rb').read()
        s = new[base:base + len(s0)]
        t = decode(s)
        # 히라가나가 minrun 개 이상 «가까이» 모인 구간
        hits = []
        i = 0
        while i < len(t):
            if t[i] not in HIRA:
                i += 1
                continue
            j = i
            n = 0
            gap = 0
            while j < len(t) and gap < 3:
                if t[j] in HIRA or t[j] in KATA or 0x4E00 <= ord(t[j]) <= 0x9FFF:
                    if t[j] in HIRA:
                        n += 1
                    gap = 0
                else:
                    gap += 1
                j += 1
            if n >= minrun:
                hits.append((i, t[max(0, i - 2):j]))
            i = j
        if hits:
            total += len(hits)
            print('\n### %s (%d)' % (name, len(hits)))
            for i, frag in hits[:20]:
                print('   ~+0x%05X  %s' % (i, frag.replace('\x00', '|').replace('\x01', '?')[:60]))
    print('\n총 미번역 의심 %d건' % total)


if __name__ == '__main__':
    main()
