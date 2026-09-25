# -*- coding: utf-8 -*-
"""블릿된 텍스트 줄을 셀 경계 없이 이어붙여 ASCII 아트로 출력한다.

글자가 8px 셀 경계에 정렬돼 있는지(고정폭) 아니면 비트 시프트돼 있는지(가변폭)
눈으로 판정하기 위한 것.
"""
VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, CW, CH, NCELL = 0x8000, 64, 8, 16, 28

d = open(VRAM, 'rb').read()
rows = []
for y in range(CH):
    line = []
    for c in range(NCELL):
        base = BLIT + c * CB + y * (CW // 2)
        for x in range(CW):
            b = d[base + x // 2]
            v = (b >> 4) if x % 2 == 0 else (b & 15)
            line.append(1 if v else 0)
    rows.append(line)

W = NCELL * CW
# 8px 셀 눈금
print('    ' + ''.join('|' if x % 8 == 0 else ('.' if x % 4 == 0 else ' ')
                       for x in range(W)))
for y, line in enumerate(rows):
    print('%2d  %s' % (y, ''.join('#' if v else '.' for v in line)))

# 각 열의 잉크 유무 → 글자 경계 추정
ink = [any(rows[y][x] for y in range(CH)) for x in range(W)]
print('열  ' + ''.join('#' if v else '.' for v in ink))
runs, x = [], 0
while x < W:
    if ink[x]:
        s = x
        while x < W and ink[x]:
            x += 1
        runs.append((s, x - s))
    else:
        x += 1
print('잉크 런(시작,폭): %s' % runs)
