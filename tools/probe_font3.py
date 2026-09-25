# -*- coding: utf-8 -*-
"""EDFNT.DAT 섹션을 4bpp 가정으로 렌더한다.

섹션 크기가 전부 288의 배수 → 288 B = 24x24 4bpp 한 칸이 유력 가설.
비교를 위해 16x16 4bpp(128 B), 12x12 4bpp(72 B)도 같이 그린다.
"""
SHADE = ' .:-=+*#%@$&WMB8'


def render_4bpp(data, off, w, h, count, rep, gap=' '):
    cell = w * h // 2
    rows = ['' for _ in range(h)]
    for g in range(count):
        base = off + g * cell
        for y in range(h):
            line = ''
            for x in range(0, w, 2):
                idx = base + (y * w + x) // 2
                b = data[idx] if idx < len(data) else 0
                line += SHADE[b >> 4] + SHADE[b & 15]
            rows[y] += line + gap
    for r in rows:
        rep(r)


def main():
    a = open('work/dm/BIN_EDFNT.DAT', 'rb').read()
    out = open('work/probe_font3.txt', 'w', encoding='utf-8')

    def rep(s):
        out.write(s + '\n')

    for label, (w, h), off, cnt in [
        ('24x24 4bpp @섹션1', (24, 24), 0x434, 8),
        ('24x24 4bpp @섹션2', (24, 24), 0x1634, 8),
        ('16x16 4bpp @섹션1', (16, 16), 0x434, 10),
        ('12x12 4bpp @섹션1', (12, 12), 0x434, 12),
        ('24x24 4bpp @섹션0', (24, 24), 0x1F4, 2),
    ]:
        rep('==== %s ====' % label)
        render_4bpp(a, off, w, h, cnt, rep)
        rep('')
    out.close()
    print('wrote work/probe_font3.txt')


if __name__ == '__main__':
    main()
