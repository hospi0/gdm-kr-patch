#!/usr/bin/env python3
"""edfnt.py — (de)compose the ending-credits container FIELD/EDFNT.DAT.

EDFNT.DAT is a BE-u32 offset-table archive (same layout as the minigame
containers, see tools/mg_stb.py) whose every used slot is a **pre-rendered
4bpp text-line bitmap, 24 px tall**, width = slot_size/12. It is NOT a glyph
font + index table — each slot is one whole line of credits text drawn as art.
So translation = redrawing each line's bitmap, then repacking CONSTANT-SIZE
(offsets unchanged → disc-patchable in place, like mg_stb.py repack).

Subcommands:
  dump   EDFNT.DAT OUTDIR             extract every slot + render a PNG per slot
  author EDFNT.DAT SLOT "TEXT" OUT    render TEXT into slot SLOT's W x24 4bpp strip
  patch  EDFNT.DAT MAP.json OUT.DAT   replace slots (constant-size) from {slot: "TEXT"}

A slot's English strip must fit the slot's original WIDTH (it is left-aligned,
transparent-padded). Width is fixed by the slot size, so very short JP slots
(e.g. a 2-kanji header at 48 px) constrain the English; wide name/title slots
(360-408 px) have ample room. `author`/`patch` raise if the text overflows.
"""
import json
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

H = 24  # every EDFNT strip is 24 px tall


def parse_table(d):
    tsz = struct.unpack(">I", d[:4])[0]
    if tsz % 4 or tsz > len(d):
        raise ValueError(f"implausible table_size {tsz:#x}")
    raw = [struct.unpack(">I", d[i * 4:i * 4 + 4])[0] for i in range(tsz // 4)]
    offs = []
    for o in raw:
        if o == 0xFFFFFFFF:
            break
        if o:
            offs.append(o)
    spans = []
    for i, o in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else len(d)
        spans.append((o, end - o))
    return tsz, spans


def slot_width(size):
    return size * 2 // H  # 4bpp -> 2 px/byte, height 24


def decode_strip(buf, w):
    img = Image.new("L", (w, H))
    px = img.load()
    for i in range(w * H):
        b = buf[i // 2]
        v = (b >> 4) if i % 2 == 0 else (b & 0xF)
        px[i % w, i // w] = v * 17
    return img


def encode_strip(img, w):
    """L-mode (0..255) WxH image -> 4bpp packed bytes (value = round(L/17))."""
    px = img.load()
    out = bytearray(w * H // 2)
    for i in range(w * H):
        v = min(15, (px[i % w, i // w] + 8) // 17)
        if i % 2 == 0:
            out[i // 2] = (out[i // 2] & 0x0F) | (v << 4)
        else:
            out[i // 2] = (out[i // 2] & 0xF0) | v
    return bytes(out)


_FONTS = {}


def font(size):
    # Pillow's bundled scalable default (no external file dependency).
    if size not in _FONTS:
        _FONTS[size] = ImageFont.load_default(size=size)
    return _FONTS[size]


def render_text(text, w):
    """Render ASCII into a w x24 grayscale strip (white text on black),
    vertically centred, left-aligned with a small margin. The font auto-shrinks
    (18 -> 9 px) to fit the slot's fixed width; raises only if it can't fit at 9px."""
    img = Image.new("L", (w, H), 0)
    dr = ImageDraw.Draw(img)
    for size in range(18, 8, -1):
        f = font(size)
        bbox = dr.textbbox((0, 0), text, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= w - 2:
            y = (H - th) // 2 - bbox[1]
            dr.text((2, y), text, fill=255, font=f)
            return img
    raise ValueError(f"text {text!r} does not fit slot width {w}px even at 9px")


def cmd_dump(dat, outdir):
    d = Path(dat).read_bytes()
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    _, spans = parse_table(d)
    for i, (o, sz) in enumerate(spans):
        w = slot_width(sz)
        (out / f"{i:03d}.bin").write_bytes(d[o:o + sz])
        decode_strip(d[o:o + sz], w).save(out / f"{i:03d}.png")
    print(f"dumped {len(spans)} slots -> {outdir}")


def cmd_author(dat, slot, text, outbin):
    d = Path(dat).read_bytes()
    _, spans = parse_table(d)
    o, sz = spans[int(slot)]
    w = slot_width(sz)
    buf = encode_strip(render_text(text, w), w)
    assert len(buf) == sz, (len(buf), sz)
    Path(outbin).write_bytes(buf)
    print(f"slot {slot}: '{text}' -> {w}x{H} 4bpp, {len(buf)} bytes (== original)")


def cmd_patch(dat, mapfile, outdat):
    d = bytearray(Path(dat).read_bytes())
    _, spans = parse_table(d)
    mapping = json.loads(Path(mapfile).read_text())
    for k, text in mapping.items():
        o, sz = spans[int(k)]
        w = slot_width(sz)
        buf = encode_strip(render_text(text, w), w)
        assert len(buf) == sz
        d[o:o + sz] = buf
        print(f"  slot {k}: '{text}' ({w}px) patched in place")
    Path(outdat).write_bytes(d)
    print(f"wrote {outdat} ({len(d)} bytes, same size as input)")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    c = argv[1]
    if c == "dump":
        cmd_dump(argv[2], argv[3])
    elif c == "author":
        cmd_author(argv[2], argv[3], argv[4], argv[5])
    elif c == "patch":
        cmd_patch(argv[2], argv[3], argv[4])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
