#!/usr/bin/env python3
"""mg_logo.py — author the English deck-swab title logo into the decoded bg sprite.

The 甲板掃除 ("deck swab") kanji are white/grey embossed glyphs on a brown wood
plank; the chrome "REMIX" (already English) overlaps the plank's lower-right and is
pixel-interlocked with 除, so it cannot be auto-separated. Strategy: detect the
greyscale kanji pixels and in-paint them with wood (copy the nearest wood pixel in
the same row — the grain is horizontal), while PROTECTING the REMIX zone, then stamp
"DECK SWAB" embossed (black outline + white core) in the cleared left area.

Operates on a decoded 352x224 8bpp bg buffer (mg_knpan chunk 0..4, dst 0x14000) and
the bg palette (CRAM @ 0x600). Returns the edited buffer; mg_knpan.patch re-encodes.
"""
import struct

WHITE = 101   # kanji/text core (rgb 248,248,248)
BLACK = 45    # outline (rgb 0,0,0)
W = 352

# 5x7 block font (superset of tools/mg_text.py FONT, adds W/V/J/Z/&/digits as needed)
FONT = {
    'A': ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    'B': ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    'C': ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    'D': ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    'E': ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    'K': ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    'S': ["01110", "10001", "10000", "01110", "00001", "10001", "01110"],
    'W': ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    'B2': [],
    ' ': ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
}


def _text_width(text, scale, spacing):
    return len(text) * (6 * scale) if not spacing else \
        sum((5 * scale + spacing) for _ in text)


def stamp(buf, text, scale, x0, y0, gap=1):
    """Draw embossed text: 8-neighbour black outline, then white core."""
    # pass 1: outline
    cx = x0
    for ch in text.upper():
        g = FONT.get(ch, FONT[' '])
        for ry, row in enumerate(g):
            for rx, c in enumerate(row):
                if c == '1':
                    for sy in range(scale):
                        for sx in range(scale):
                            X = cx + rx * scale + sx
                            Y = y0 + ry * scale + sy
                            for dx in (-1, 0, 1):
                                for dy in (-1, 0, 1):
                                    xx, yy = X + dx, Y + dy
                                    if 0 <= xx < W and 0 <= yy < 224:
                                        buf[yy * W + xx] = BLACK
        cx += 5 * scale + gap * scale
    # pass 2: white core
    cx = x0
    for ch in text.upper():
        g = FONT.get(ch, FONT[' '])
        for ry, row in enumerate(g):
            for rx, c in enumerate(row):
                if c == '1':
                    for sy in range(scale):
                        for sx in range(scale):
                            X = cx + rx * scale + sx
                            Y = y0 + ry * scale + sy
                            if 0 <= X < W and 0 <= Y < 224:
                                buf[Y * W + X] = WHITE
        cx += 5 * scale + gap * scale


def make_logo(bg, cram, text="DECK SWAB", scale=2, x0=50, y0=34,
              protect_x=158, protect_y=48, box=(44, 224, 12, 84)):
    """In-paint the kanji and stamp `text`. bg: bytearray(352*224). Returns it."""
    def rgb(idx):
        v = struct.unpack(">H", cram[0x600 + idx * 2:0x600 + idx * 2 + 2])[0]
        return ((v & 0x1F) << 3, ((v >> 5) & 0x1F) << 3, ((v >> 10) & 0x1F) << 3)

    def is_gray(idx):
        r, g, b = rgb(idx)
        return abs(r - g) < 26 and abs(g - b) < 26 and (r + g + b) > 90

    def is_wood(idx):
        r, g, b = rgb(idx)
        return idx != 0 and r > g and g >= b and (r + g + b) > 90 and not is_gray(idx)

    X0, X1, Y0, Y1 = box
    for y in range(Y0, Y1):
        woodxs = [x for x in range(X0, X1) if is_wood(bg[y * W + x])]
        for x in range(X0, X1):
            if x >= protect_x and y >= protect_y:
                continue  # REMIX zone
            if is_gray(bg[y * W + x]):
                if woodxs:
                    nx = min(woodxs, key=lambda wx: abs(wx - x))
                    bg[y * W + x] = bg[y * W + nx]
                else:
                    bg[y * W + x] = 122  # fallback wood tone
    stamp(bg, text, scale, x0, y0)
    return bg


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "tools")
    import mg_knpan
    knpan = open(sys.argv[1] if len(sys.argv) > 1 else "work/mgame/KNPAN.DAT", "rb").read()
    cram = open("work/mgame/cram/cram.bin", "rb").read()
    full = bytearray(mg_knpan.decode_screen(knpan))
    bg = bytearray(full[0x14000:0x27400])
    make_logo(bg, cram)
    full[0x14000:0x27400] = bg
    open("work/mgame/screen_logo.bin", "wb").write(full)
    print("wrote work/mgame/screen_logo.bin")
