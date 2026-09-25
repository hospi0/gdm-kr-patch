# -*- coding: utf-8 -*-
"""1bpp → 4bpp 확장 룩업표를 찾는다.

글리프를 1bpp에서 4bpp 셀로 펴는 코드는 거의 항상 비트확장표를 쓴다.
  - 2비트 → 1바이트 : 00 0F F0 FF
  - 4비트 → 2바이트 : 0000 000F 00F0 00FF 0F00 …  (16항목 32B)
  - 8비트 → 4바이트 : 00000000 0000000F …          (256항목 1024B)
색 인덱스가 15가 아닐 수도 있으므로 1~15를 전부 시도한다.
니블 순서(상위부터/하위부터)도 둘 다 본다.
"""
import os


def spread(v, nbits, color, lsb_first):
    out = 0
    bits = [(v >> i) & 1 for i in range(nbits)]
    if not lsb_first:
        bits = bits[::-1]
    for b in bits:
        out = (out << 4) | (color if b else 0)
    return out.to_bytes(nbits // 2, 'big')


def tables():
    for color in range(1, 16):
        for lsb in (False, True):
            for nbits in (4, 8):
                t = b''.join(spread(i, nbits, color, lsb) for i in range(1 << nbits))
                yield ('%dbit색%d%s' % (nbits, color, '역' if lsb else ''), t)
            # 2비트 표
            t = b''.join(spread(i, 2, color, lsb) for i in range(4))
            yield ('2bit색%d%s' % (color, '역' if lsb else ''), t)


def main():
    targets = []
    for dirn in ('work/state_b', 'work/dm'):
        if not os.path.isdir(dirn):
            continue
        for f in sorted(os.listdir(dirn)):
            p = os.path.join(dirn, f)
            if os.path.isfile(p) and os.path.getsize(p) >= 64:
                targets.append((dirn.split('/')[-1] + '/' + f, open(p, 'rb').read()))

    tabs = [(n, t) for n, t in tables() if len(t) >= 8]
    print('표 %d종' % len(tabs))
    hits = 0
    for name, d in targets:
        for tn, t in tabs:
            i = d.find(t)
            while i >= 0:
                print('  %-34s +0x%06X  %s (%dB)' % (name, i, tn, len(t)))
                hits += 1
                i = d.find(t, i + 1)
    print('일치 %d건' % hits)


if __name__ == '__main__':
    main()
