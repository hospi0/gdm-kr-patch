# -*- coding: utf-8 -*-
"""JIS X0201 배치 지문으로 폰트 시트를 찾는다.

TEXT2.BIN이 1바이트 반각 가타카나(JIS X0201)를 쓰는 것이 확인됐으므로,
코드값으로 색인되는 글리프 시트가 있다면 '빈 칸 배치'가 아래와 같아야 한다.

    0x00-0x1F  제어      → 빈칸
    0x20       스페이스  → 빈칸
    0x21-0x7E  ASCII     → 채움
    0x7F-0xA0  미사용    → 빈칸
    0xA1-0xDF  가타카나  → 채움
    0xE0-0xFF  미사용    → 빈칸

메모리 교훈 [[feedback_scan_coverage_and_detectors]]: 검출기는 양성·음성·고유율을
모두 제약해야 한다. 여기서는 '채워야 할 칸이 찼는가'(양성)와 '비어야 할 칸이
비었는가'(음성)를 모두 요구하고, 채운 칸의 고유율도 함께 본다.
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')

# 셀 바이트 크기 후보: (설명, 바이트)
CELLS = [('8x8 1bpp', 8), ('8x12 1bpp', 12), ('8x16 1bpp', 16),
         ('12x12 1bpp', 24), ('16x16 1bpp', 32),
         ('8x8 4bpp', 32), ('12x12 4bpp', 72), ('16x16 4bpp', 128)]

MASK = np.zeros(256, dtype=np.int8)      # 1=채움, 0=빈칸, -1=무관
MASK[0x21:0x7F] = 1
MASK[0xA1:0xE0] = 1
CARE = np.ones(256, dtype=bool)
FILL = MASK == 1
EMPTY = ~FILL


def scan(data, cell, min_score=0.93):
    """cell 바이트 단위로 256칸 창을 밀며 지문 일치도를 잰다."""
    n = len(data)
    if n < cell * 256 + 4:
        return []
    a = np.frombuffer(data, dtype=np.uint8)
    hits = []
    # 셀 비어있음 여부를 4바이트 스텝마다 다시 계산하면 느리다.
    # cell 정렬 가정으로 시작 오프셋을 0..cell-1 중 4의 배수만 시도한다.
    for base in range(0, cell, 4):
        m = (n - base) // cell
        if m < 256:
            continue
        cells = a[base:base + m * cell].reshape(m, cell)
        nonempty = cells.any(axis=1)
        for s in range(0, m - 256 + 1):
            w = nonempty[s:s + 256]
            score = ((w == FILL).sum()) / 256.0
            if score >= min_score:
                blk = cells[s:s + 256][FILL]
                uniq = len(set(map(bytes, blk))) / float(FILL.sum())
                if uniq >= 0.7:
                    hits.append((score, uniq, base + s * cell))
    return hits


def main():
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    out = open('work/scan_x0201.txt', 'w', encoding='utf-8')
    found = 0
    for path, (lba, size) in sorted(files.items()):
        if size < 2048 or size > 6 << 20:
            continue
        data = I.read_range(buf, lba, min(size, 2 << 20))
        for label, cell in CELLS:
            for score, uniq, off in scan(data, cell):
                found += 1
                line = ('%-26s %-11s 셀%-4d off=0x%06X  지문일치 %.3f  고유율 %.2f'
                        % (path, label, cell, off, score, uniq))
                out.write(line + '\n')
                print(line)
    out.close()
    print('일치 %d건 → work/scan_x0201.txt' % found)


if __name__ == '__main__':
    main()
