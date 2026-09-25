#!/usr/bin/env python3
"""pO4c_nameplate_fold.py — author English party NAME-PLATES into the battle-HUD sprite atlas
and fold the re-encoded (MODE-1) stream back into every /BATLE/*.BBG copy on the disc IN PLACE.

The party battle name-plates ジャスティン / スー / フィーナ (top of screen, over the HP bars) are
4bpp VDP1 sprite textures inside a battle-HUD sprite atlas decoded at battle LOAD:
  * one decode of 0xFCA0 bytes -> VDP1 VRAM 0x04000  (covers 0x04000..0x13ca0)
  * codec = the resident SH-2 routine 0x0601A716, MODE 1 (XOR pixel filter; w0=0x66d9)
  * source on disc = /BATLE/B001.BBG, first copy at raw off 0x29bc4 (35 byte-identical copies)

Name cells (VDP1 VRAM abs offset; in-atlas = -0x04000):
  * 0x05950 = Justin (48x14)   * 0x05bc0 = Sue (48x12)   * 0x05aa0 = Feena (48x12)

Pipeline (all offline, ROM-decoder-oracle-checked):
  1. decode the on-disc atlas (0x29bc4 -> VRAM 0x04000) via pO4_chrome_codec (real routine)
  2. author "JUSTIN"/"SUE"/"FEENA" into the 3 cells (bright fill nib 14 + dark outline nib 1,
     matching the JP glyph ink/style; 48px cells fit the short names — NO geometry edit)
  3. re-encode MODE-1 via pO4c_encode_mode1 (round-trip-verified vs the ROM decoder)
  4. write the stream de-sectored at EVERY copy's raw offset (never grows the block; the English
     stream 24529 B <= original block 24855 B, so the following BBG data is never touched)

Idempotent (SIG_EN copies are skipped), byte-deterministic (fixed English stream, md5-stamped),
and round-trip self-checked on the written disc. Model: tools/pO4_chrome_fold.py.
"""
import argparse, hashlib, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_chrome_codec as codec
import pO4_chrome_encode as enc
import pO4c_encode_mode1 as m1

RAW_SECTOR, SYNC_HEADER, USER_DATA = 2352, 16, 2048
DST_BASE = 0x04000
WIN_LO, WIN_HI = 0x04000, 0x04000 + 0xFCA0     # the 0xFCA0-byte atlas window
FIRST_OFF = 0x29bc4                              # first on-disc copy (locator anchor)
ORIG_BLOCK_LEN = 24855                           # original mode-1 stream span (0x6117); hard budget
ZTHRESH = 4                                      # any value that fits works (never padded)

# name cells (VDP1 VRAM abs offset, w, h, English text)
LABELS = [
    (0x05950, 48, 14, "JUSTIN"),
    (0x05bc0, 48, 12, "SUE"),
    (0x05aa0, 48, 12, "FEENA"),
]

# ---------------------------------------------------------------------------
# de-sectored read/write (matches codec.read_logical)
# ---------------------------------------------------------------------------
def write_logical(disc, raw_off, data):
    o, p = raw_off, 0
    while p < len(data):
        sec = o // RAW_SECTOR
        ino = o % RAW_SECTOR
        if ino < SYNC_HEADER:
            ino = SYNC_HEADER
        data_end = sec * RAW_SECTOR + SYNC_HEADER + USER_DATA
        space = data_end - (sec * RAW_SECTOR + ino)
        n = min(space, len(data) - p)
        disc[sec * RAW_SECTOR + ino: sec * RAW_SECTOR + ino + n] = data[p:p + n]
        p += n
        o = (sec + 1) * RAW_SECTOR + SYNC_HEADER


# ---------------------------------------------------------------------------
# compact 5x7 uppercase font (reuse pO4_chrome_fold's, + J)
# ---------------------------------------------------------------------------
import pO4_chrome_fold as _cf
FONT = dict(_cf.FONT)
FONT['J'] = ["00111", "00010", "00010", "00010", "10010", "10010", "01100"]


def author_cell(atlas, srca, w, h, text, fill=14, outline=1, gap=1):
    """Draw `text` centered in the cell with a bright fill + 1px dark outline, matching the
    JP glyph style. Clears the cell first. atlas = full-VRAM bytearray, 4bpp @ stride w/2."""
    stride = w // 2
    grid = [[0] * w for _ in range(h)]
    glyphs = [FONT[c] for c in text]
    gw_total = sum(len(g[0]) for g in glyphs) + gap * (len(glyphs) - 1)
    x0 = max(0, (w - gw_total) // 2)
    gh = 7
    y0 = max(0, (h - gh) // 2 - (1 if h >= 13 else 0))
    x = x0
    for g in glyphs:
        gw = len(g[0])
        for r in range(gh):
            for c in range(gw):
                if g[r][c] == '1':
                    yy, xx = y0 + r, x + c
                    if 0 <= yy < h and 0 <= xx < w:
                        grid[yy][xx] = fill
        x += gw + gap
    out = [[grid[y][x] for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            if grid[y][x] == 0:
                nb = False
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < h and 0 <= xx < w and grid[yy][xx] == fill:
                            nb = True
                if nb:
                    out[y][x] = outline
    for y in range(h):
        for x in range(w):
            off = srca + y * stride + x // 2
            nib = out[y][x]
            b = atlas[off]
            if x % 2 == 0:
                atlas[off] = (nib << 4) | (b & 0x0F)
            else:
                atlas[off] = (b & 0xF0) | (nib & 0xF)
    return out


# ---------------------------------------------------------------------------
# author + encode
# ---------------------------------------------------------------------------
def author_atlas(disc, raw_off=FIRST_OFF):
    vram = bytearray(codec.run_decode(bytes(disc), raw_off, DST_BASE, 0x12000))
    for srca, w, h, text in LABELS:
        author_cell(vram, srca, w, h, text)
    return vram


def build_stream(disc, raw_off=FIRST_OFF):
    """Author English + re-encode MODE-1. Returns (stream, authored_vram)."""
    vram = author_atlas(disc, raw_off)
    codelen9, _ = enc._codelen9_from_disc_bytes(bytes(disc), raw_off)
    stream = m1.encode(bytes(vram[WIN_LO:WIN_HI]), codelen9, mode=1, zthresh=ZTHRESH)
    return stream, vram


def _find(disc, sig):
    out, s = [], 0
    while True:
        j = disc.find(sig, s)
        if j < 0:
            break
        out.append(j); s = j + 1
    return out


# ---------------------------------------------------------------------------
# fold
# ---------------------------------------------------------------------------
def cmd_fold(track):
    disc = bytearray(open(track, "rb").read())
    # idempotency gate: if the on-disc atlas already decodes to the English name cells, skip.
    cur = codec.run_decode(bytes(disc), FIRST_OFF, DST_BASE, 0x12000)
    tgt = bytearray(cur)
    for srca, w, h, text in LABELS:
        author_cell(tgt, srca, w, h, text)
    if bytes(cur[WIN_LO:WIN_HI]) == bytes(tgt[WIN_LO:WIN_HI]):
        print("name-plate atlas already English -> skip"); return
    stream, vram = build_stream(disc)
    if len(stream) > ORIG_BLOCK_LEN:
        raise SystemExit(f"encoded stream {len(stream)} B > block budget {ORIG_BLOCK_LEN} B")

    # oracle round-trip gate (offline, no HW): decode the fresh stream, compare to the target
    dec = enc._rom_decode_raw(stream, DST_BASE)
    mm = sum(1 for k in range(WIN_LO, WIN_HI) if dec[k] != vram[k])
    if mm:
        raise SystemExit(f"round-trip FAILED: {mm} px mismatch — refusing to fold")

    sig_jp = codec.read_logical(bytes(disc), FIRST_OFF, 32)   # original JP header+control
    sig_en = stream[:32]                                       # folded English header+control
    jp = _find(disc, sig_jp)
    en = _find(disc, sig_en)
    if not jp:
        print(f"no JP name-plate copies found (already folded? {len(en)} EN copies) -> skip")
        return
    for off in jp:
        write_logical(disc, off, stream)
    open(track, "wb").write(disc)

    # verify on the freshly-written disc: every JP copy is now the English atlas, bit-exact
    disc2 = open(track, "rb").read()
    okc = 0
    for off in jp:
        chk = codec.run_decode(disc2, off, DST_BASE, 0x12000)
        if bytes(chk[WIN_LO:WIN_HI]) == bytes(vram[WIN_LO:WIN_HI]):
            okc += 1
    md5 = hashlib.md5(stream).hexdigest()
    print(f"folded {len(jp)} name-plate copies -> {track}")
    print(f"  stream {len(stream)} B (budget {ORIG_BLOCK_LEN}); md5={md5}; round-trip OK={okc}/{len(jp)}")


def cmd_preview(a):
    disc = bytearray(open(a.src, "rb").read())
    stream, vram = build_stream(disc)
    open(a.out, "wb").write(bytes(vram))
    md5 = hashlib.md5(stream).hexdigest()
    print(f"authored+encoded MODE-1: stream {len(stream)} B (budget {ORIG_BLOCK_LEN}); "
          f"md5={md5}; atlas -> {a.out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fold"); pf.add_argument("track")
    pp = sub.add_parser("preview")
    pp.add_argument("--src", default="output/rc_35/Track1.bin")
    pp.add_argument("--out", default="work/pO4c/english_nameplate_atlas.bin")
    a = ap.parse_args()
    if a.cmd == "fold":
        cmd_fold(a.track)
    else:
        cmd_preview(a)
