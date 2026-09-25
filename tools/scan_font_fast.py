# -*- coding: utf-8 -*-
"""글리프 시트 탐색(고속판). 코드 색인 가정 없이 '글자다운 셀이 길게 이어지는 구간'을 찾는다.

scan_x0201.py가 0건이었으므로 JIS X0201 코드 배치 가정을 버린다.
대신 폰트의 본질적 성질만 요구한다:
  - 셀들이 연속으로 비어 있지 않다 (>= MINRUN 개)
  - 셀 내부 set-bit 밀도가 글자다운 범위
  - 셀들이 서로 다르다 (고유율 높음) → 같은 타일 반복·단색 영역 배제
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')

CELLS = [('8x8 1bpp', 8), ('8x12 1bpp', 12), ('8x16 1bpp', 16),
         ('12x12 1bpp', 24), ('16x16 1bpp', 32), ('12x12 4bpp', 72)]
MINRUN = 64
POP = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)


def best_run(data, cell):
    n = len(data) // cell
    if n < MINRUN:
        return None
    a = np.frombuffer(data[:n * cell], dtype=np.uint8).reshape(n, cell)
    bits = POP[a].sum(axis=1) / float(cell * 8)
    ok = (bits >= 0.10) & (bits <= 0.60)
    # 가장 긴 True 런 찾기
    best = (0, 0)
    i = 0
    while i < n:
        if ok[i]:
            j = i
            while j < n and ok[j]:
                j += 1
            if j - i > best[1] - best[0]:
                best = (i, j)
            i = j
        else:
            i += 1
    s, e = best
    if e - s < MINRUN:
        return None
    blk = a[s:e]
    uniq = len(set(map(bytes, blk))) / float(e - s)
    if uniq < 0.75:
        return None
    return (e - s, s * cell, uniq, float(bits[s:e].mean()))


def main():
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    rows = []
    for path, (lba, size) in sorted(files.items()):
        if size < 2048:
            continue
        data = I.read_range(buf, lba, min(size, 8 << 20))
        for label, cell in CELLS:
            r = best_run(data, cell)
            if r:
                rows.append((r[0], path, label, r[1], r[2], r[3]))
    rows.sort(reverse=True)
    with open('work/scan_font_fast.txt', 'w', encoding='utf-8') as f:
        for cnt, path, label, off, uniq, dens in rows[:120]:
            line = ('%-26s %-11s 연속 %4d칸  off=0x%06X  고유율 %.2f  밀도 %.2f'
                    % (path, label, cnt, off, uniq, dens))
            f.write(line + '\n')
    print('후보 %d건 → work/scan_font_fast.txt' % len(rows))
    for r in rows[:20]:
        print('%-26s %-11s 연속 %4d칸  off=0x%06X  고유율 %.2f  밀도 %.2f'
              % (r[1], r[2], r[0], r[3], r[4], r[5]))


if __name__ == '__main__':
    main()
