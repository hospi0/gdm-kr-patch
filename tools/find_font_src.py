# -*- coding: utf-8 -*-
"""화면에 그려진 글자(블릿 결과)에서 1bpp 폰트 원본을 RAM에서 역검색한다.

확정 사실(사용자 확인):
  VDP2 VRAM(**swap16 복원본**) 오프셋 0x8000부터 8px×16행 4bpp 셀이 연속으로
  놓이며, 그것이 화면의 대사 「フィーナ！ スー！ / あ あれ！？」다.

앞선 시도가 0건이었던 이유는 **스왑하지 않은 VRAM**을 썼기 때문이다.

원리: 엔진은 1bpp 글리프에 색을 입혀 블릿한다. 따라서 화면 글자의 '모양'은
RAM에 1bpp 비트열로 존재해야 한다. 니블!=0 → 1 로 환원해 검색한다.
"""
import os
import sys

VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT = 0x8000
CELL_W, CELL_H = 8, 16          # 셀 = 8px 폭, 16행 (8x8 타일 2개)
CELL_BYTES = CELL_W * CELL_H // 2
RAMS = ['WorkRAML_sw', 'WorkRAMH_sw', 'WorkRAML', 'WorkRAMH']


def cell_rows(d, idx):
    """셀 idx → 16행, 각 행 8비트(1bpp, MSB=왼쪽)"""
    base = BLIT + idx * CELL_BYTES
    rows = []
    for y in range(CELL_H):
        v = 0
        for x in range(0, CELL_W, 2):
            b = d[base + (y * CELL_W + x) // 2]
            v = (v << 2) | ((1 if (b >> 4) else 0) << 1) | (1 if (b & 15) else 0)
        rows.append(v)
    return rows


def main():
    d = open(VRAM, 'rb').read()
    n = 64
    cells = [cell_rows(d, i) for i in range(n)]
    nonblank = [i for i, r in enumerate(cells) if any(r)]
    print('셀 %d개 중 비어있지 않은 셀 %d개: %s' % (n, len(nonblank), nonblank[:24]))

    rams = {}
    for t in RAMS:
        p = 'work/state_%s/%s.bin' % ('b', t)
        if os.path.exists(p):
            rams[t] = open(p, 'rb').read()

    found = 0
    # (a) 8px 글리프: 16행 × 1바이트
    # (b) 16px 글리프: 인접 두 셀을 합쳐 16행 × 2바이트
    for i in nonblank[:20]:
        q1 = bytes(cells[i])
        cand = [('8px', q1)]
        if i + 1 < n:
            q2 = bytearray()
            for y in range(CELL_H):
                q2.append(cells[i][y])
                q2.append(cells[i + 1][y])
            cand.append(('16px', bytes(q2)))
        for kind, q in cand:
            for cut in (len(q), len(q) * 3 // 4, len(q) // 2):
                sub = q[:cut]
                if sub.count(0) > len(sub) - 4:
                    continue
                for t, mem in rams.items():
                    k = mem.find(sub)
                    if k >= 0:
                        print('  셀%-3d %-5s %2d바이트 → %s+0x%06X  %s'
                              % (i, kind, len(sub), t, k, sub[:8].hex()))
                        found += 1
                        break
                else:
                    continue
                break
    print('일치 %d건' % found)


if __name__ == '__main__':
    main()
