#!/usr/bin/env python3
"""Render the English theater selection-screen plates into the decoded 0x15000 plate block.

The block (DORAM slot-8 [6], decoded contiguously to VDP1 VRAM from 0x299c0) holds, in order:
  header  144x40 @0x00000   ->  "SCREENING MENU"        (JP: 上映メニュー)
  empty   152x48 @0x01680   ->  (unchanged template)
  drama1  152x48 @0x03300   ->  "Gumbo: After the Banquet"    (ガンボ、宴会の後で)
  drama3  152x48 @0x04f80   ->  "Where They Fall"            (落ちてゆく先…)
  drama5  152x48 @0x06c00   ->  "Cooking Showdown!"          (料理で決戦！)
  drama2  152x48 @0x08880   ->  "This Is the Way of a Man"   (これが男の生きる道)
  drama4  152x48 @0x0a500   ->  "Beyond the End of the World"(世界の果てを越えて)
(plate<->drama mapping identified by the baked JP text — the block order is 1,3,5,2,4.)

Each plate is 8bpp palette-indexed (slot-6 palette @ CRAM word 0x500).  We keep pixel value 0
transparent, clear a text band to the plate's background index, and draw the English title with a
bitmap font in a bright stroke index.  Palette indices (from the captured CRAM):
  * drama plates: starfield background ~57..66; text stroke = 15 (white) / 14 outline.
  * header:       yellow button 187/165; text = 193 (blue) with 194 (dark-blue) outline.

The result is fed to gfx_plate_encode.encode_block (clean-terminating literal stream) and must
still round-trip byte-exact + normal-exit (gfx_plate_roundtrip).  Titles come from
src/theater/captions/drama{1..5}.json `title_en` (read-only).

First-pass art: legible English on a simplified (solid) background band; the starfield/decoration
behind the JP text is not reconstructed.  On-screen review pending (the screening menu is not
drivable headlessly).
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CAPTIONS = HERE / "captions"

DECODE_SIZE = 0x15000

# (offset, w, h, title, bg_index, fg_index, outline_index, band(top,bot))
# band = vertical range (rows) to clear+draw; None => whole plate interior.
PLATES = [
    ("header", 0x00000, 144, 40, "Screening Menu", 187, 193, 194, (6, 34)),
    ("drama1", 0x03300, 152, 48, None, 57, 66, None, (4, 44)),
    ("drama3", 0x04f80, 152, 48, None, 57, 66, None, (4, 44)),
    ("drama5", 0x06c00, 152, 48, None, 57, 66, None, (4, 44)),
    ("drama2", 0x08880, 152, 48, None, 57, 66, None, (4, 44)),
    ("drama4", 0x0a500, 152, 48, None, 57, 66, None, (4, 44)),
]
DRAMA_TITLE = {p[0]: None for p in PLATES}


def _title_for(name: str) -> str | None:
    if name.startswith("drama"):
        j = json.loads((CAPTIONS / f"{name}.json").read_text())
        return j["title_en"]
    return None


def _modal_bg(seg: bytes, w: int, band: tuple[int, int]) -> int:
    """Background index = most common NON-zero index in the plate's top border rows."""
    top = [seg[y * w + x] for y in range(0, max(2, band[0])) for x in range(w) if seg[y * w + x]]
    if not top:
        top = [b for b in seg if b]
    return Counter(top).most_common(1)[0][0]


def _fit_font(text: str, maxw: int, maxh: int, lines_max: int = 2):
    """Pick the largest default-font size whose wrapped text fits maxw x maxh."""
    for size in range(maxh, 6, -1):
        font = ImageFont.load_default(size=size)
        for nlines in range(1, lines_max + 1):
            lines = _wrap(text, font, maxw, nlines)
            if lines is None:
                continue
            th = sum(_line_h(font, ln) for ln in lines)
            if th <= maxh and all(_line_w(font, ln) <= maxw for ln in lines):
                return font, lines
    font = ImageFont.load_default(size=8)
    return font, [text]


def _line_w(font, s):
    b = font.getbbox(s)
    return b[2] - b[0]


def _line_h(font, s):
    b = font.getbbox(s)
    return b[3] - b[1] + 2


def _wrap(text, font, maxw, nlines):
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if _line_w(font, t) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
            if len(lines) >= nlines:
                return None
    if cur:
        lines.append(cur)
    return lines if len(lines) <= nlines else None


def _draw_plate(seg: bytearray, w: int, h: int, title: str, bg: int, fg: int,
                outline: int, band: tuple[int, int]) -> None:
    t0, t1 = band
    # clear the text band to background
    for y in range(t0, min(t1, h)):
        for x in range(w):
            seg[y * w + x] = bg
    # render text to a 1-bit mask via PIL, then stamp fg (+outline) indices
    maxw, maxh = w - 12, (t1 - t0) - 4
    font, lines = _fit_font(title, maxw, maxh, lines_max=2)
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    total_h = sum(_line_h(font, ln) for ln in lines)
    y = t0 + max(0, ((t1 - t0) - total_h) // 2)
    for ln in lines:
        lw = _line_w(font, ln)
        bx = font.getbbox(ln)
        d.text(((w - lw) // 2 - bx[0], y - bx[1]), ln, fill=255, font=font)
        y += _line_h(font, ln)
    px = img.load()
    # outline: 8-neighbourhood of stroke pixels (drawn first, under the stroke)
    if outline is not None:
        stroke = [(x, yy) for yy in range(h) for x in range(w) if px[x, yy] > 96]
        for (x, yy) in stroke:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nx, ny = x + dx, yy + dy
                    if 0 <= nx < w and 0 <= ny < h and px[nx, ny] <= 96:
                        seg[ny * w + nx] = outline
    for yy in range(h):
        for x in range(w):
            if px[x, yy] > 96:
                seg[yy * w + x] = fg


def build_block(orig_block: bytes) -> bytes:
    out = bytearray(orig_block)
    for name, off, w, h, _t, bg, fg, outline, band in PLATES:
        title = _title_for(name)
        if title is None and _t is None:
            continue
        title = _t if _t is not None else title
        seg = bytearray(out[off:off + w * h])
        if bg is None:
            bg = _modal_bg(seg, w, band)
        _draw_plate(seg, w, h, title, bg, fg, outline, band)
        out[off:off + w * h] = seg
    return bytes(out)


def _preview(orig_block: bytes, cram: bytes, outdir: str) -> None:
    base = 0xa00

    def rgb(v):
        wd = ((cram[base + 2 * v] << 8) | cram[base + 2 * v + 1]) & 0x7FFF
        return ((wd & 0x1f) << 3, ((wd >> 5) & 0x1f) << 3, ((wd >> 10) & 0x1f) << 3)

    lut = [rgb(v) for v in range(256)]
    new = build_block(orig_block)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    for name, off, w, h, *_ in PLATES:
        seg = new[off:off + w * h]
        img = Image.new("RGB", (w, h))
        img.putdata([lut[b] for b in seg])
        img.resize((w * 3, h * 3), Image.NEAREST).save(f"{outdir}/{name}.png")
        print("preview", name)


if __name__ == "__main__":
    # Preview: python3 gfx_build_plates.py <block.bin> <cram.bin> <outdir>
    blk = Path(sys.argv[1]).read_bytes()
    cr = Path(sys.argv[2]).read_bytes()
    _preview(blk, cr, sys.argv[3])
