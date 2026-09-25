# -*- coding: utf-8 -*-
"""EDFNT.DAT를 새턴 8x8 셀(타일) 인터리브 4bpp로 풀어서 렌더한다.

근거: 288 B = 32 B(8x8 4bpp 타일) x 9 = 3x3 타일 = 24x24 글리프.
선형 스캔라인 렌더에서 '6행 내용 + 2행 공백'이 반복된 것이 타일 인터리브의 신호였다.
"""
SHADE = ' .:-=+*#%@$&WMB8'
TILE = 32  # 8x8 4bpp


def glyph_pixels(data, base, tw, th):
    """tw x th 개의 8x8 타일로 이루어진 글리프 → [행][열] 니블 배열"""
    W, H = tw * 8, th * 8
    px = [[0] * W for _ in range(H)]
    for t in range(tw * th):
        ty, tx = divmod(t, tw)
        off = base + t * TILE
        for y in range(8):
            for x in range(0, 8, 2):
                idx = off + (y * 8 + x) // 2
                b = data[idx] if idx < len(data) else 0
                px[ty * 8 + y][tx * 8 + x] = b >> 4
                px[ty * 8 + y][tx * 8 + x + 1] = b & 15
    return px


def render(data, off, tw, th, count, rep):
    W, H = tw * 8, th * 8
    rows = [''] * H
    for g in range(count):
        px = glyph_pixels(data, off + g * tw * th * TILE, tw, th)
        for y in range(H):
            rows[y] += ''.join(SHADE[v] for v in px[y]) + '|'
    for r in rows:
        rep(r)


def main():
    a = open('work/dm/BIN_EDFNT.DAT', 'rb').read()
    out = open('work/probe_font4.txt', 'w', encoding='utf-8')

    def rep(s):
        out.write(s + '\n')

    for label, off, cnt in [('섹션1 @0x434', 0x434, 8),
                            ('섹션2 @0x1634', 0x1634, 8),
                            ('섹션0 @0x1F4', 0x1F4, 2),
                            ('섹션13 @0xD214', 0xD214, 8)]:
        rep('==== %s : 3x3 타일(24x24) 4bpp ====' % label)
        render(a, off, 3, 3, cnt, rep)
        rep('')
    out.close()
    print('wrote work/probe_font4.txt')


if __name__ == '__main__':
    main()
