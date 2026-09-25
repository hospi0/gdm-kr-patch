#!/usr/bin/env python3
"""viewer_mtout_gfx.py — English re-author of the design-viewer category-page BAKED art.

MTOUT.DAT slot 2 sub-blob 6 (slot2+0x7f0, 29168 B) is ONE compressed stream
(the resident field-sprite codec, func 0x0601A716 — decoder oracle
src/theater/gfx_plate.py, encoder family tools/mg_field_codec.py) that decodes
51456 B (0xC900, per the u32 at slot2 sub0) of 8bpp UI textures to VDP1 0x1000:

  +0x0000  puzzle-piece sprites / zoom frames (kept verbatim)
  +0x1680  the 設定資料集 banner, 144x24 (yellow lozenge + dark-blue JP text)
  +0x9300  SIX selected-label text strips, 144x16 each, 2-value masks
           (0x83 = dark-blue text on 0 = transparent; drawn over the white bar)

This tool decodes the block with the sh2emu oracle, redraws the banner text as
"DESIGN MATERIALS" (erasing the JP strokes row-wise to the lozenge fill) and the
six strips from the SAME in-game 16x16 font the page uses for the unselected
labels (LWRAM 0x200a00 XOR-RLE font, decoded via the real glyph routine
0x06030ADE — see docs/museum-viewers-format.md, Lane K), then re-encodes with a
per-stream OPTIMAL canonical Huffman (XOR-delta mode, RLE zero-run escapes) and
splices the blob back at slot2+0x7f0 padded to the original 29168 B — MTOUT stays
byte-identical in size and layout.

Needs RAM images with the viewer resident (default: work/pK/base/wram-{hi,lo}.bin,
the registered user-design-viewer-rc23 dump) for the decoder/font oracles.

CLI:
  build  MTOUT.DAT OUTDIR   -> OUTDIR/MTOUT.DAT (banner+strips English)
         [--hwram H --lwram L] [--labels "A,B,..."] [--banner "TEXT"]
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src" / "theater"))

import dicdt  # noqa: E402
import gfx_plate  # noqa: E402
import sh2emu  # noqa: E402

HWRAM_DEF = ROOT / "work/pK/base/wram-hi.bin"
LWRAM_DEF = ROOT / "work/pK/base/wram-lo.bin"

SUB6_OFF = 0x13610 + 0x7F0     # file offset of the compressed block
SUB6_SIZE = 29168
DEC_SIZE = 0xC900              # decoded bytes (slot2 sub0 u32)
LWRAM_MTOUT = 0x210000         # where the viewer loads MTOUT.DAT
BANNER_OFF, BAN_W, BAN_H = 0x1680, 144, 24
STRIPS_OFF, STRIP_W, STRIP_H = 0x9300, 144, 16
TEXT_VAL = 0x83                # strip text colour index
GLYPH_FN = 0x06030ADE          # in-overlay glyph decoder (r4=dst, r5=tbl code)

LABELS = ["ART 1", "ART 2", "MONSTERS", "CAST 1", "CAST 2", "CAST 3"]
ALIGN_RIGHT = {1}              # strip 1 (美術設定２) is right-aligned in vanilla
BANNER_TEXT = "DESIGN MATERIALS"


# ---------------------------------------------------------------- glyphs
def glyph_mask(hwram: bytes, lwram: bytes, code: int) -> list:
    """16x16 boolean mask for one tbl code, via the real glyph decoder."""
    m = sh2emu.Mem()
    m.map(0x06000000, hwram)
    m.map(0x00200000, lwram)
    m.map(0x25C00000, bytes(0x1000))
    m.map(0x30000000, bytes(0x10000))
    cpu = sh2emu.SH2(m)
    cpu.R[4] = 0x25C00000
    cpu.R[5] = code
    cpu.R[15] = 0x30008000
    cpu.run(GLYPH_FN, max_steps=200000)
    t = m.region(0x25C00000)[:0x100]
    rows = []
    for r in range(16):
        row = []
        for b in t[r * 8:(r + 1) * 8]:
            row += [(b >> 4) != 0, (b & 15) != 0]
        rows.append(row)
    return rows


def render_strip(hwram, lwram, text: str, align_right: bool) -> bytes:
    codes = []
    enc = dicdt.encode(text, halfwidth=False)
    i = 0
    while i < len(enc):
        b = enc[i]
        if b >= 0x20:
            codes.append(b)
            i += 1
        else:  # 2-byte kanji code (not used by our labels, but be correct)
            codes.append((enc[i] << 8) | enc[i + 1])
            i += 2
    w = len(codes) * 16
    if w > STRIP_W:
        raise SystemExit(f"strip text too wide: {text!r} = {w}px > {STRIP_W}")
    x0 = STRIP_W - w if align_right else 0
    # REVERSE VIDEO (matches the vanilla in-game look): the strip is a solid
    # 0x83 bar spanning the label's glyph cells, with the glyph strokes CARVED
    # OUT (value 0 = transparent). The engine draws the white glyph sprites at
    # the same position underneath, so the holes show as white text on the bar.
    out = bytearray(STRIP_W * STRIP_H)
    for y in range(STRIP_H):
        for x in range(x0, x0 + w):
            out[y * STRIP_W + x] = TEXT_VAL
    for k, c in enumerate(codes):
        mask = glyph_mask(hwram, lwram, c)
        for y in range(16):
            for x in range(16):
                if mask[y][x]:
                    out[y * STRIP_W + x0 + k * 16 + x] = 0
    return bytes(out)


# ---------------------------------------------------------------- banner
def redraw_banner(ban: bytearray, cram: bytes, text: str) -> None:
    """Erase the JP strokes inside the lozenge and draw `text` in the stroke colour.

    JP text = the BLUE-dominant palette indices (0x5f body, 0x66/0x70 shading);
    the lozenge itself is yellows + a brown border, never blue — so erasing
    "blue anywhere" is safe. Fill value = the same-row pixel at a clean sample
    column (x=24, between the rounded end and the first glyph), preserving the
    vertical gradient and the top/bottom border lines.
    """
    def rgb(i):
        wv = struct.unpack(">H", cram[(0x200 + i) * 2:(0x200 + i) * 2 + 2])[0]
        return ((wv & 31) << 3, ((wv >> 5) & 31) << 3, ((wv >> 10) & 31) << 3)

    def is_text(i):  # blue-dominant = JP stroke / stroke shading / AA blends
        r, g, b = rgb(i)
        return b > r  # lozenge yellows/browns always have r > b; strokes b > r

    XL, XR = 26, 119   # clean sample columns left/right of the JP text
    # 1) blue strokes can appear slightly outside the band -> erase them anywhere
    for y in range(BAN_H):
        fill = ban[y * BAN_W + XL]
        for x in range(BAN_W):
            if is_text(ban[y * BAN_W + x]):
                ban[y * BAN_W + x] = fill
    # 2) the JP text's pale ANTI-ALIAS halo shares palette entries with the
    #    lozenge yellows -> rebuild the whole text band unconditionally,
    #    dither-lerping between the clean left/right sample columns so the
    #    lozenge's horizontal shading survives (keeps gradient + border lines)
    for y in range(BAN_H):
        lv = ban[y * BAN_W + XL]
        rv = ban[y * BAN_W + XR]
        bayer = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
        for x in range(XL + 1, XR):
            t = (x - XL) / (XR - XL)
            thr = (bayer[y % 4][x % 4] + 0.5) / 16.0    # Bayer 4x4 ordered dither
            ban[y * BAN_W + x] = rv if t > thr else lv
    # draw text: body 0x5f (bright blue), +1/+1 shadow 0x70 (dark blue)
    from PIL import Image, ImageDraw, ImageFont
    BODY, SHADOW = 0x5F, 0x70
    X0, X1, Y0, Y1 = 14, 130, 4, 20
    img = Image.new("L", (BAN_W, BAN_H), 0)
    dr = ImageDraw.Draw(img)
    for size in range(14, 6, -1):
        font = ImageFont.load_default(size=size)
        bb = dr.textbbox((0, 0), text, font=font)
        if bb[2] - bb[0] <= (X1 - X0) and bb[3] - bb[1] <= (Y1 - Y0):
            break
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    dr.text(((BAN_W - tw) // 2 - bb[0], (BAN_H - th) // 2 - bb[1]), text,
            fill=255, font=font)
    px = img.load()
    for y in range(BAN_H - 1):
        for x in range(BAN_W - 1):
            if px[x, y] >= 128 and px[x + 1, y + 1] < 128:
                ban[(y + 1) * BAN_W + x + 1] = SHADOW
    for y in range(BAN_H):
        for x in range(BAN_W):
            if px[x, y] >= 128:
                ban[y * BAN_W + x] = BODY


# ---------------------------------------------------------------- encoder
def encode_block(img: bytes) -> bytes:
    """Field-sprite codec encoder: XOR-less mode 0, zero-run escapes, OPTIMAL
    per-stream canonical Huffman over the 17 symbols (max code len 8)."""
    nibs = []
    for b in img:
        nibs.append(b >> 4)
        nibs.append(b & 15)
    N = len(nibs)
    syms = []          # 0..15 literal, 16 escape
    runs = []
    i = 0
    while i < N:
        if nibs[i] == 0:
            j = i
            while j < N and nibs[j] == 0:
                j += 1
            z = j - i
            if z >= 4:
                while z > 0:
                    part = min(z, 0xFFFF)
                    syms.append(16)
                    runs.append(part)
                    z -= part
                i = j
                continue
        syms.append(nibs[i])
        i += 1
    syms.append(16)
    runs.append(0)      # end-of-stream escape

    # ---- optimal length-limited Huffman (max 8 bits), Kraft sum == 256
    freq = [0] * 17
    for s in syms:
        freq[s] += 1
    lens = _limited_huffman(freq, 8)
    # canonical assignment mirroring the engine LUT fill: (length DESC, index ASC)
    order = sorted(range(17), key=lambda s: (-lens[s], s))
    codes = {}
    pos = 0
    for s in order:
        if lens[s] == 0:
            continue
        span = 1 << (8 - lens[s])
        codes[s] = (pos >> (8 - lens[s]), lens[s])
        pos += span
    assert pos == 256, f"Kraft fill = {pos}"

    # ---- stream A (run nibbles; prefer the short relative-to-previous forms)
    an = []
    prev = 0
    for z in runs:
        if z == 0:
            an += [14, 0, 0]        # absolute 0 = end of stream
        elif 0 <= z - prev + 6 <= 12:
            an += [z - prev + 6]    # v 0..12: run = prev + v - 6
        elif -6 <= z - prev + 14 - 8 and 0 <= z - prev + 14 < 8:
            an += [13, z - prev + 14]           # 13,n (n<8): run = prev + n - 14
        elif 8 <= z - prev + 1 <= 15:
            an += [13, z - prev + 1]            # 13,n (n>=8): run = prev + n - 1
        elif z <= 255:
            an += [14, (z >> 4) & 15, z & 15]
        else:
            an += [15, (z >> 12) & 15, (z >> 8) & 15, (z >> 4) & 15, z & 15]
        prev = z
    while len(an) % 4:
        an.append(0)
    sa = bytearray()
    for k in range(0, len(an), 2):
        sa.append((an[k] << 4) | an[k + 1])
    if len(sa) > 0x1FFF:
        raise ValueError(f"stream A too long ({len(sa)})")
    hdr = 0x2000 | len(sa)      # mode 0 (mov), literal-first

    lens_b = bytearray()
    for k in range(0, 18, 2):
        l0 = lens[k] if k < 17 else 0
        l1 = lens[k + 1] if k + 1 < 17 else 0
        lens_b.append((l0 << 4) | l1)

    # ---- stream B bitstream
    acc = cnt = 0
    sb = bytearray()
    for s in syms:
        c, ln = codes[s]
        for k in range(ln - 1, -1, -1):
            acc = (acc << 1) | ((c >> k) & 1)
            cnt += 1
            if cnt == 8:
                sb.append(acc)
                acc = cnt = 0
    if cnt:
        sb.append(acc << (8 - cnt))
    sb += b"\0" * 8
    return struct.pack(">H", hdr) + bytes(sa) + bytes(lens_b) + bytes(sb)


def _limited_huffman(freq, maxlen):
    """Package-merge optimal length-limited code lengths (0 for unused syms)."""
    items = [(f, s) for s, f in enumerate(freq) if f > 0]
    if len(items) == 1:
        lens = [0] * len(freq)
        lens[items[0][1]] = 1
        return lens
    pkgs = []
    lens = [0] * len(freq)
    coins = []
    level = [(f, (s,)) for f, s in items]
    level.sort()
    for _ in range(maxlen):
        coins = level if not coins else _merge(level, _package(coins))
    need = 2 * (len(items) - 1)
    for f, symset in coins[:need]:
        for s in symset:
            lens[s] += 1
    return lens


def _package(coins):
    out = []
    for k in range(0, len(coins) - 1, 2):
        out.append((coins[k][0] + coins[k + 1][0], coins[k][1] + coins[k + 1][1]))
    return out


def _merge(a, b):
    return sorted(a + b, key=lambda x: x[0])


# ---------------------------------------------------------------- build
def build(mtout_path: str, outdir: str, hwram_path=None, lwram_path=None,
          labels=None, banner=None) -> None:
    hwram = Path(hwram_path or HWRAM_DEF).read_bytes()
    lwram = Path(lwram_path or LWRAM_DEF).read_bytes()
    mtout = bytearray(Path(mtout_path).read_bytes())
    labels = labels or LABELS
    banner = banner or BANNER_TEXT

    # 1. decode the original block (oracle needs it resident at LWRAM_MTOUT)
    lw_img = bytearray(lwram)
    lw_img[LWRAM_MTOUT - 0x200000:LWRAM_MTOUT - 0x200000 + len(mtout)] = mtout
    dec = bytearray(gfx_plate.decode_plate(
        hwram, bytes(lw_img), 0x200000 + LWRAM_MTOUT - 0x200000 + SUB6_OFF,
        SUB6_SIZE, 256, (DEC_SIZE + 255) // 256, dst_vram_off=0x1000)[:DEC_SIZE])

    # 2. redraw
    cram = Path(str(ROOT / "work/pK/base/cram-final.bin")).read_bytes()
    ban = bytearray(dec[BANNER_OFF:BANNER_OFF + BAN_W * BAN_H])
    redraw_banner(ban, cram, banner)
    dec[BANNER_OFF:BANNER_OFF + BAN_W * BAN_H] = ban
    for i, text in enumerate(labels):
        strip = render_strip(hwram, lwram, text, i in ALIGN_RIGHT)
        off = STRIPS_OFF + i * STRIP_W * STRIP_H
        dec[off:off + STRIP_W * STRIP_H] = strip

    # 3. re-encode + verify round-trip via the engine oracle
    blob = encode_block(bytes(dec))
    if len(blob) > SUB6_SIZE:
        raise SystemExit(f"encoded blob {len(blob)} B > slot {SUB6_SIZE} B")
    blob = blob.ljust(SUB6_SIZE, b"\x00")
    mtout[SUB6_OFF:SUB6_OFF + SUB6_SIZE] = blob
    lw_img[LWRAM_MTOUT - 0x200000:LWRAM_MTOUT - 0x200000 + len(mtout)] = mtout
    rt = gfx_plate.decode_plate(hwram, bytes(lw_img), LWRAM_MTOUT + SUB6_OFF,
                                SUB6_SIZE, 256, (DEC_SIZE + 255) // 256,
                                dst_vram_off=0x1000)[:DEC_SIZE]
    if bytes(rt) != bytes(dec):
        bad = next(i for i, (a, b) in enumerate(zip(rt, dec)) if a != b)
        raise SystemExit(f"round-trip mismatch at +{bad:#x}")
    Path(outdir).mkdir(parents=True, exist_ok=True)
    out = Path(outdir) / "MTOUT.DAT"
    out.write_bytes(mtout)
    print(f"OK: blob {len(blob)} B (fits {SUB6_SIZE}), round-trip byte-exact -> {out}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("mtout")
    ap.add_argument("outdir")
    ap.add_argument("--hwram")
    ap.add_argument("--lwram")
    ap.add_argument("--labels")
    ap.add_argument("--banner")
    a = ap.parse_args()
    build(a.mtout, a.outdir, a.hwram, a.lwram,
          a.labels.split(",") if a.labels else None, a.banner)
