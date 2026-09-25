# -*- coding: utf-8 -*-
"""EDFNT.DAT의 BE32 섹션 테이블을 해석하고 각 섹션 시작에서 글리프를 렌더한다."""
import os
import struct


def entropy(b):
    if not b:
        return 0.0
    import math
    from collections import Counter
    c = Counter(b)
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def render_1bpp(data, off, w, h, count, rep):
    stride = (w + 7) // 8
    cell = stride * h
    rows = ['' for _ in range(h)]
    for g in range(count):
        base = off + g * cell
        for y in range(h):
            bits = ''
            for xb in range(stride):
                idx = base + y * stride + xb
                b = data[idx] if idx < len(data) else 0
                for k in range(7, -1, -1):
                    if len(bits) < w:
                        bits += '#' if (b >> k) & 1 else '.'
            rows[y] += bits + ' '
    for r in rows:
        rep(r)


def main():
    a = open('work/dm/BIN_EDFNT.DAT', 'rb').read()
    out = open('work/probe_font2.txt', 'w', encoding='utf-8')

    def rep(s):
        out.write(s + '\n')

    # BE32 오름차순이 끊기는 지점까지를 테이블로 본다
    offs = []
    i = 0
    while i + 4 <= len(a):
        v = struct.unpack_from('>I', a, i)[0]
        if offs and not (offs[-1] < v <= len(a)):
            break
        if not offs and not (0 < v <= len(a)):
            break
        offs.append(v)
        i += 4
        if offs[0] <= i:      # 테이블이 첫 섹션 시작에 닿으면 끝
            break
    rep('섹션 테이블 항목 %d개, 테이블 크기 %d B, 첫 섹션 0x%X'
        % (len(offs), i, offs[0] if offs else -1))
    rep('')
    rep('idx  start      size     엔트로피(비트/바이트)')
    ends = offs[1:] + [len(a)]
    for n, (s, e) in enumerate(zip(offs, ends)):
        rep('%3d  0x%06X  %-8d %.2f' % (n, s, e - s, entropy(a[s:e])))
    rep('')

    for n in range(min(4, len(offs))):
        s = offs[n]
        for (w, h) in [(16, 16), (12, 12)]:
            rep('==== 섹션 %d @0x%X  %dx%d 1bpp ====' % (n, s, w, h))
            render_1bpp(a, s, w, h, 14, rep)
            rep('')
    out.close()
    print('wrote work/probe_font2.txt')


if __name__ == '__main__':
    main()
