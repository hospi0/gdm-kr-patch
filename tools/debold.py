# -*- coding: utf-8 -*-
"""블릿된 글리프가 '가로 볼드(G | G>>1)'의 결과인지 판정하고, 맞으면 원본 G를 복원한다.

근거: G의 길이 k짜리 가로 런은 G|(G>>1)에서 같은 위치·길이 k+1이 된다.
     따라서 볼드 결과에는 **길이 1짜리 런이 존재할 수 없다.**
     길이 1 런이 하나도 없으면 볼드 가설이 성립하고, 복원은 유일하다.
"""
VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, CW, CH, NCELL = 0x8000, 64, 8, 16, 28


def bitrows():
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
    return rows


def runs(line):
    out, x, n = [], 0, len(line)
    while x < n:
        if line[x]:
            s = x
            while x < n and line[x]:
                x += 1
            out.append((s, x - s))
        else:
            x += 1
    return out


def main():
    rows = bitrows()
    W = len(rows[0])

    hist = {}
    for y in range(CH):
        for _, L in runs(rows[y]):
            hist[L] = hist.get(L, 0) + 1
    print('가로 잉크 런 길이 분포: %s' % dict(sorted(hist.items())))
    print('길이 1짜리 런 %d개 → 가로 볼드 가설 %s'
          % (hist.get(1, 0), '성립' if hist.get(1, 0) == 0 else '기각'))

    # 세로 방향도 같은 검사
    vhist = {}
    for x in range(W):
        col = [rows[y][x] for y in range(CH)]
        for _, L in runs(col):
            vhist[L] = vhist.get(L, 0) + 1
    print('세로 잉크 런 길이 분포: %s' % dict(sorted(vhist.items())))
    print('길이 1짜리 세로런 %d개 → 세로 볼드 가설 %s'
          % (vhist.get(1, 0), '성립' if vhist.get(1, 0) == 0 else '기각'))

    if hist.get(1, 0):
        return

    # 복원: 각 런 (s, L) → (s, L-1)
    thin = [[0] * W for _ in range(CH)]
    for y in range(CH):
        for s, L in runs(rows[y]):
            for x in range(s, s + L - 1):
                thin[y][x] = 1
    print()
    print('== 볼드 제거 결과 ==')
    print('    ' + ''.join('|' if x % 16 == 0 else ' ' for x in range(W)))
    for y in range(CH):
        print('%2d  %s' % (y, ''.join('#' if v else '.' for v in thin[y])))
    ink = [any(thin[y][x] for y in range(CH)) for x in range(W)]
    print('열  ' + ''.join('#' if v else '.' for v in ink))
    print('잉크 런(시작,폭): %s' % runs(ink))


if __name__ == '__main__':
    main()
