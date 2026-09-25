# -*- coding: utf-8 -*-
"""폰트 코드 ↔ 글자 대응표를 자동으로 만든다.

게임 폰트는 16×16 1bpp다. MS Gothic 16px 내장 비트맵이 고전 JIS 16×16과
거의 같으므로, 후보 글자를 16×16으로 렌더해 **해밍 거리 최소**로 대응시킨다.

⚠️ 자동 대조는 틀릴 수 있다. 그래서
  (a) 이미 아는 코드 9개로 먼저 품질을 재고
  (b) 거리와 2등과의 격차(margin)를 함께 내서 의심스러운 것을 걸러낸다.
"""
import sys
import unicodedata

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, 'tools')
import font_codec as C

FONT = r'C:\Windows\Fonts\msgothic.ttc'
BOX = 16

# 이미 확정된 대응 (화면 대조로 얻음)
KNOWN = {0x026: 'あ', 0x070: 'れ', 0x078: 'ィ', 0x08E: 'ス', 0x09F: 'ナ',
         0x0AA: 'フ', 0x0CD: '！', 0x0CF: 'ー', 0x0D7: '？'}


def render(ch, font, size=16, dx=0, dy=0):
    img = Image.new('L', (BOX, BOX), 0)
    ImageDraw.Draw(img).text((dx, dy), ch, fill=255, font=font)
    px = img.load()
    return [sum((1 if px[x, y] >= 128 else 0) << (15 - x) for x in range(BOX))
            for y in range(BOX)]


def candidates():
    out = []
    # ASCII 전각
    for c in range(0x21, 0x7F):
        out.append(chr(c))
        out.append(chr(0xFF00 + c - 0x20))          # 전각형
    # 히라가나·가타카나
    out += [chr(c) for c in range(0x3041, 0x3097)]
    out += [chr(c) for c in range(0x30A1, 0x30FB)]
    out += ['ー', '、', '。', '・', '「', '」', '゛', '゜', '～', '…', '‥']
    # 기호
    out += [chr(c) for c in range(0x2010, 0x2050)]
    out += [chr(c) for c in range(0x2190, 0x21A0)]
    out += [chr(c) for c in range(0x2460, 0x2470)]
    out += ['♥', '♡', '★', '☆', '○', '●', '△', '▲', '□', '■', '◇', '◆', '※']
    # 한자 (CJK 통합, 상용 범위 전체)
    out += [chr(c) for c in range(0x4E00, 0xA000)]
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def build_index(font, dx, dy):
    idx = {}
    for ch in candidates():
        r = render(ch, font, dx=dx, dy=dy)
        if not any(r):
            continue
        idx.setdefault(tuple(r), ch)
    return idx


def best_match(rows, table):
    b1 = b2 = (10 ** 9, None)
    for cand, ch in table:
        d = sum(bin(rows[y] ^ cand[y]).count('1') for y in range(BOX))
        if d < b1[0]:
            b2, b1 = b1, (d, ch)
        elif d < b2[0]:
            b2 = (d, ch)
    return b1[0], b1[1], b2[0]


def main():
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    n = C.table_count(d, C.FULL_BASE)
    game = {c: C.raw_to_rows(C.glyph_full(d, c)) for c in range(n)}

    # 원점 보정 탐색 — 알려진 9개로 가장 잘 맞는 (dx,dy)를 고른다
    best = None
    for dy in range(-3, 3):
        for dx in range(-2, 3):
            f = ImageFont.truetype(FONT, 16)
            tot = 0
            for code, ch in KNOWN.items():
                r = render(ch, f, dx=dx, dy=dy)
                tot += sum(bin(game[code][y] ^ r[y]).count('1') for y in range(BOX))
            if best is None or tot < best[0]:
                best = (tot, dx, dy)
    tot, dx, dy = best
    print('원점 보정 dx=%d dy=%d, 알려진 9글자 총 해밍거리 %d (평균 %.1f)'
          % (dx, dy, tot, tot / len(KNOWN)))
    f = ImageFont.truetype(FONT, 16)
    for code, ch in sorted(KNOWN.items()):
        r = render(ch, f, dx=dx, dy=dy)
        dd = sum(bin(game[code][y] ^ r[y]).count('1') for y in range(BOX))
        print('  0x%03X %s  거리 %d' % (code, ch, dd))


if __name__ == '__main__':
    main()
