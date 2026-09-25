# -*- coding: utf-8 -*-
"""디코드한 폰트가 화면에 실제로 찍힌 글리프와 **바이트 단위로 같은지** 대조한다.

스캔이 아니라 전체 대조다 — 세이브스테이트 VDP2 VRAM에서 뜯은 16x16 글리프가
FDATA.BIN에서 디코드한 어떤 코드와 정확히 일치하는지 본다.
"""
import struct
import sys

sys.path.insert(0, 'tools')
from font_decode import FULL_BASE, HALF_BASE, decode_glyph, table_len

VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, CW, CH, NCELL = 0x8000, 64, 8, 16, 32


def screen_boxes():
    d = open(VRAM, 'rb').read()
    rows = []
    for y in range(CH):
        line = []
        for c in range(NCELL):
            base = BLIT + c * CB + y * (CW // 2)
            for x in range(CW):
                b = d[base + x // 2]
                line.append(1 if ((b >> 4) if x % 2 == 0 else (b & 15)) else 0)
        rows.append(line)
    out = []
    for bi in range(NCELL // 2):
        L = [int(''.join(str(rows[y][bi * 16 + x]) for x in range(8)), 2)
             for y in range(CH)]
        R = [int(''.join(str(rows[y][bi * 16 + 8 + x]) for x in range(8)), 2)
             for y in range(CH)]
        if any(L) or any(R):
            out.append((bi, L, R))
    return out


def main():
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    n = table_len(d, FULL_BASE)
    tab = {}
    for code in range(n):
        g = decode_glyph(d, FULL_BASE, code)
        if g:
            tab.setdefault((bytes(g[0]), bytes(g[1])), []).append(code)
    print('전각 %d코드 → 서로 다른 글리프 %d종' % (n, len(tab)))

    ok = 0
    boxes = screen_boxes()
    for bi, L, R in boxes:
        key = (bytes(L), bytes(R))
        hit = tab.get(key)
        if hit:
            ok += 1
            print('  상자%-3d → 코드 %s  ✓ 바이트 완전 일치'
                  % (bi, ' / '.join('0x%03X' % c for c in hit[:4])))
        else:
            print('  상자%-3d → 일치 없음' % bi)
    print('%d/%d 일치' % (ok, len(boxes)))


if __name__ == '__main__':
    main()
