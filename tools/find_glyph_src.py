# -*- coding: utf-8 -*-
"""블릿된 글자 픽셀(VDP2 VRAM)에서 1bpp 글리프 원본을 Work RAM에서 역검색한다.

근거(Shining 03_dynamic_vram.md / font.py):
이 계열 엔진은 1bpp 글리프 테이블을 RAM에 두고, 렌더러가 색을 입혀
스테이징 버퍼를 거쳐 VRAM에 블릿한다. 따라서 화면에 보이는 글자의 '모양'은
RAM 어딘가에 **1bpp 비트열**로 그대로 존재해야 한다.

방법: 블릿 결과를 행 단위 1bpp로 환원하고, 그 행 비트열을 Work RAM에서 찾는다.
1바이트/행(8px)과 2바이트/행(16px) 두 가지를 모두 시도한다.
"""
import os
import sys

VDP2 = 'work/state_b/VRAM_1.bin'
REGION = (0x8000, 0x8500)
RAMS = ['WorkRAML_sw', 'WorkRAMH_sw', 'WorkRAML', 'WorkRAMH', 'VRAM']


def rows_1bpp_8px(d, start, end):
    """4bpp 8px 행(4바이트) → 1bpp 1바이트. 0이 아닌 니블을 1로 본다."""
    out = []
    for off in range(start, end, 4):
        v = 0
        for k in range(4):
            b = d[off + k]
            v = (v << 2) | ((1 if (b >> 4) else 0) << 1) | (1 if (b & 15) else 0)
        out.append(v)
    return bytes(out)


def main():
    d = open(VDP2, 'rb').read()
    rows = rows_1bpp_8px(d, *REGION)
    print('블릿 구간 %d행(8px) 환원' % len(rows))

    rams = {}
    for t in RAMS:
        p = 'work/state_b/%s.bin' % t
        if os.path.exists(p):
            rams[t] = open(p, 'rb').read()

    # 비어 있지 않은 행이 연속으로 N개인 구간을 질의로 쓴다
    queries = []
    i = 0
    while i < len(rows):
        if rows[i]:
            j = i
            while j < len(rows) and rows[j]:
                j += 1
            if j - i >= 6:
                queries.append((i, bytes(rows[i:j])))
            i = j
        else:
            i += 1
    print('질의 %d개 (연속 6행 이상)' % len(queries))

    found = 0
    for ri, q in queries[:60]:
        for n in (len(q), 12, 10, 8, 6):
            if n > len(q):
                continue
            sub = q[:n]
            for t, mem in rams.items():
                k = mem.find(sub)
                if k >= 0:
                    print('  행%-4d %2d행질의 %s → %s+0x%06X'
                          % (ri, n, sub.hex(), t, k))
                    found += 1
                    break
            else:
                continue
            break
    print('일치 %d건' % found)


if __name__ == '__main__':
    main()
