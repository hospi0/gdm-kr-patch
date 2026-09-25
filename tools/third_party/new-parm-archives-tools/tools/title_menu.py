#!/usr/bin/env python3
"""title_menu.py — translate the GDM title-screen START MENU (/BIN/TTL.DAT).

The title screen's menu (新しく始める / 続きを行なう) is NOT text through a font: the
labels are pre-rendered 96x16 8bpp bitmaps living in the sprite sheet of TTL.DAT
**section 5**, compressed with the minigame ST1 chunk codec (resident chunk-loop
0x06013F90, decode 0x06015DF0 — the exact codec cracked in tools/mg_codec/mg_tree).

TTL.DAT container: 8 BE u32 section offsets at +0.
  sec 0 (0x020)  palette (raw 0x200, CRAM)          — title bg palette
  sec 1 (0x220)  ST1 blob, 8 chunks -> VDP2 0x25E40000 (128KB logo/earth bitmap)
  sec 2 (0xa22c) palette (raw 0x200)
  sec 3 (0xa42c) ST1 blob, 1 chunk (0x3b80)
  sec 4 (0xc680) palette (raw 0x200) = CRAM bank 0x100 (the sprite-sheet palette)
  sec 5 (0xc880) ST1 blob, 2 chunks -> VDP1 0x25C01000..0x25C08080 (sprite sheet)
  sec 6/7        further data (count-0 framing; not touched)

Sprite-sheet layout (offsets within the decoded 0x7080-byte section-5 stream, i.e.
VDP1 address - 0x1000):
  0x0000  flame-cursor animation frames
  0x4800  "PRESS START BUTTON" 216x16 (already English)
  0x5580  新しく始める  96x16  (New Game,   bright)   <- VDP1 0x6580
  0x5b80  続きを行なう  96x16  (Continue,   bright)   <- VDP1 0x6b80
  0x6180  続きを行なう  96x16  (Continue,   dimmed = no save data)  <- VDP1 0x7180
  0x6780  flame cursor 24x24 frames, ...
All three labels sit in CHUNK 1 (stream offset 0x4000..0x7080), so only chunk 1 is
re-encoded; mg_splice.patch_slot keeps the result inside the section-5 slot
(size-preserving for the whole file -> plain mg_inject.py onto the disc).

TITLE.BIN (0x0602C000) draws them via literals 0x25C06580/6B80/7180 @0x5438-0x5444;
it picks 6B80 vs 7180 for item 2 from the save-exists flag [0x06038EEB].

Dictionary: 新しく始める -> "New Game", 続きを行なう -> "Continue" (dictionary/terms.json).

Usage:
  tools/title_menu.py build  TTL_IN.DAT TTL_OUT.DAT [--preview-dir DIR]
  tools/title_menu.py verify TTL_ORIG.DAT TTL_PATCHED.DAT [--png-dir DIR]
  tools/title_menu.py fold   TRACK1.bin        # patch /BIN/TTL.DAT in place on a built track
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mg_splice
import mg_tree

from PIL import Image, ImageDraw, ImageFont

SEC_SHEET = 5            # section index of the sprite-sheet ST1 blob
SEC_SHEET_PAL = 4        # raw 0x200 palette section for the sheet (CRAM bank 0x100)
LABEL_W, LABEL_H = 96, 16
CHUNK1_BASE = 0x4000     # stream offset where chunk 1's pixels start
LABELS = [               # (stream offset, text, dim)
    (0x5580, "New Game", False),
    (0x5b80, "Continue", False),
    (0x6180, "Continue", True),
]
# Grayscale ramp actually present in the sheet palette (index -> luminance).
RAMP = [0x01, 0x1a, 0x12, 0x13, 0x11, 0x18, 0x15, 0x14, 0x1d, 0x19,
        0x17, 0x16, 0x1b, 0x1c, 0x10]
BG_LUMA = 140            # what label edges blend against (earth/space backdrop)


def sections(dat):
    return list(struct.unpack_from(">8I", dat, 0))


def sheet_palette_rgb(dat):
    """256 (r,g,b) tuples from the raw RGB555 palette section."""
    off = sections(dat)[SEC_SHEET_PAL]
    out = []
    for i in range(256):
        v = struct.unpack_from(">H", dat, off + i * 2)[0]
        out.append(((v & 0x1f) << 3, ((v >> 5) & 0x1f) << 3, ((v >> 10) & 0x1f) << 3))
    return out


def _luma(rgb):
    return (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) // 1000


def render_label(text, dim, palette_rgb):
    """Render `text` as a 96x16 8bpp index bitmap in the JP labels' visual style:
    white antialiased glyphs with a dark outline over transparent (index 0);
    dim variant = gray body (index 0x19 luminance), for the disabled Continue."""
    ss = 4  # supersample
    W, H = LABEL_W * ss, LABEL_H * ss
    img = Image.new("L", (W, H), 0)          # coverage of body
    outl = Image.new("L", (W, H), 0)         # coverage of outline
    # largest default-font size that fits
    for size in range(15 * ss, 6 * ss, -1):
        font = ImageFont.load_default(size=size)
        b = font.getbbox(text)
        tw, th = b[2] - b[0], b[3] - b[1]
        if tw <= W - 2 * ss and th <= H - 2 * ss:
            break
    x = (W - tw) // 2 - b[0]
    y = (H - th) // 2 - b[1]
    d = ImageDraw.Draw(outl)
    d.text((x, y), text, font=font, fill=255, stroke_width=ss, stroke_fill=255)
    d = ImageDraw.Draw(img)
    d.text((x, y), text, font=font, fill=255)
    img = img.resize((LABEL_W, LABEL_H), Image.LANCZOS)
    outl = outl.resize((LABEL_W, LABEL_H), Image.LANCZOS)

    body_luma = 136 if dim else 248
    outline_luma = 24
    ramp = [(idx, _luma(palette_rgb[idx])) for idx in RAMP]

    def nearest(l):
        return min(ramp, key=lambda t: abs(t[1] - l))[0]

    out = bytearray(LABEL_W * LABEL_H)
    bp = img.load()
    op = outl.load()
    for yy in range(LABEL_H):
        for xx in range(LABEL_W):
            a_out = op[xx, yy] / 255.0       # total glyph+outline coverage
            a_body = bp[xx, yy] / 255.0      # body-only coverage
            if a_out < 0.15:
                continue                     # transparent
            # colour inside the glyph: body over outline; edges blend to backdrop
            inner = body_luma * a_body + outline_luma * (1 - a_body)
            l = inner * a_out + BG_LUMA * (1 - a_out)
            out[yy * LABEL_W + xx] = nearest(int(l))
    return bytes(out)


def label_png(pixels, palette_rgb, path, scale=3):
    img = Image.new("RGB", (LABEL_W, LABEL_H))
    px = img.load()
    for y in range(LABEL_H):
        for x in range(LABEL_W):
            px[x, y] = palette_rgb[pixels[y * LABEL_W + x]]
    img.resize((LABEL_W * scale, LABEL_H * scale), Image.NEAREST).save(path)


def build_bytes(dat, preview_dir=None):
    """Core: TTL.DAT bytes in -> patched TTL.DAT bytes out (same size)."""
    hdr = sections(dat)
    blob_src, slot_end = hdr[SEC_SHEET], hdr[SEC_SHEET + 1]
    pal = sheet_palette_rgb(dat)

    chunks = mg_splice.decode_slot(dat, blob_src)
    assert len(chunks) == 2, f"expected 2 sheet chunks, got {len(chunks)}"
    assert len(chunks[0]["pixels"]) == CHUNK1_BASE
    c1 = bytearray(chunks[1]["pixels"])

    for off, text, dim in LABELS:
        rel = off - CHUNK1_BASE
        assert 0 <= rel and rel + LABEL_W * LABEL_H <= len(c1), hex(off)
        px = render_label(text, dim, pal)
        c1[rel:rel + LABEL_W * LABEL_H] = px
        if preview_dir:
            os.makedirs(preview_dir, exist_ok=True)
            label_png(px, pal, os.path.join(
                preview_dir, f"authored_{off:04x}_{text.replace(' ', '_')}{'_dim' if dim else ''}.png"))

    new = mg_splice.patch_slot(dat, blob_src, slot_end, {1: bytes(c1)},
                               snap=True, palette_rgb=pal)
    assert len(new) == len(dat)

    # verify: decode back
    nchunks = mg_tree.decode_blob(new, blob_src)
    assert nchunks[0]["pixels"] == chunks[0]["pixels"], "chunk 0 disturbed!"
    got = nchunks[1]["pixels"]
    ndiff = sum(1 for a, b in zip(got, bytes(c1)) if a != b)
    print(f"title_menu: chunk1 decode diff after snap = {ndiff} px "
          f"(snap nudges), slot [{blob_src:#x},{slot_end:#x}) OK")
    if preview_dir:
        for off, text, dim in LABELS:
            rel = off - CHUNK1_BASE
            label_png(got[rel:rel + LABEL_W * LABEL_H], pal, os.path.join(
                preview_dir, f"decoded_{off:04x}_{text.replace(' ', '_')}{'_dim' if dim else ''}.png"))
    return new


def build(ttl_in, ttl_out, preview_dir=None):
    new = build_bytes(open(ttl_in, "rb").read(), preview_dir)
    open(ttl_out, "wb").write(new)
    print(f"built {ttl_out}")
    return 0


def fold(track1):
    """Patch /BIN/TTL.DAT IN PLACE on a built MODE1/2352 track (size-preserving)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    import iso
    with open(track1, "r+b") as f:
        hit = iso.find(f, "TTL.DAT")
        if not hit:
            raise SystemExit("TTL.DAT not found on track")
        _, lba, size = hit
        dat = iso.read_bytes(f, lba, size)
        new = build_bytes(dat)
        assert len(new) == size
        for i in range(0, (size + iso.USER_DATA - 1) // iso.USER_DATA):
            f.seek(iso.raw_offset(lba + i))
            f.write(new[i * iso.USER_DATA:(i + 1) * iso.USER_DATA])
    print(f"folded English title start-menu into {track1} (TTL.DAT @LBA {lba})")
    return 0


def verify(ttl_orig, ttl_patched, png_dir=None):
    for name, fn in (("orig", ttl_orig), ("patched", ttl_patched)):
        dat = open(fn, "rb").read()
        hdr = sections(dat)
        pal = sheet_palette_rgb(dat)
        chunks = mg_tree.decode_blob(dat, hdr[SEC_SHEET])
        stream = b"".join(c["pixels"] for c in chunks)
        print(f"{name}: {len(chunks)} chunks, {len(stream):#x} px bytes")
        if png_dir:
            os.makedirs(png_dir, exist_ok=True)
            for off, text, dim in LABELS:
                label_png(stream[off:off + LABEL_W * LABEL_H], pal,
                          os.path.join(png_dir, f"{name}_{off:04x}.png"))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("ttl_in"); b.add_argument("ttl_out")
    b.add_argument("--preview-dir")
    v = sub.add_parser("verify")
    v.add_argument("ttl_orig"); v.add_argument("ttl_patched")
    v.add_argument("--png-dir")
    fo = sub.add_parser("fold")
    fo.add_argument("track1")
    a = ap.parse_args()
    if a.cmd == "build":
        return build(a.ttl_in, a.ttl_out, a.preview_dir)
    if a.cmd == "fold":
        return fold(a.track1)
    return verify(a.ttl_orig, a.ttl_patched, a.png_dir)


if __name__ == "__main__":
    sys.exit(main())
