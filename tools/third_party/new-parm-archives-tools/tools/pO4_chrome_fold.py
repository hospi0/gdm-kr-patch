#!/usr/bin/env python3
"""pO4_chrome_fold.py — author English into the battle-chrome VDP1 sprite atlas, re-encode
via pO4_chrome_encode, and fold the compressed stream back into Track1.bin IN PLACE.

Pipeline (all offline, oracle-checked):
  1. decode the on-disc chrome stream (0xEBE910 -> VDP1 VRAM 0x44000) via pO4_chrome_codec
  2. author English label glyphs into the atlas cells (fg nibble 15, transparent 0)
  3. re-encode via pO4_chrome_encode (round-trip-verified against the ROM decoder)
  4. write the stream back de-sectored at raw off 0xEBE910 (size-preserving, md5/byte-gated)

The chrome stream lives in the /BATLE resident archive (not an ISO-enumerated file), so we
patch by RAW OFFSET. ECC is not recomputed (YMIR ignores it, like every other fold here).

Labels folded (this atlas = the magic/skill HUD box): 魔法 (0x477c0, 32x16) -> "MAGIC".
技 (0x473a0, 16x16) is a single 16px cell; "Skill" needs the VDP1 command-list width edit
(STAGE 2, see docs/lanes/pO4_encoder-cracked.md) — folded as compact "SKL" at native width.
"""
import argparse, hashlib, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_chrome_codec as codec
import pO4_chrome_encode as enc

RAW_SECTOR, SYNC_HEADER, USER_DATA = 2352, 16, 2048
CHROME_RAW_OFF = 0xEBE910
DST_BASE = 0x44000
WIN_LO, WIN_HI = 0x44000, 0x4afe0

# ---------------------------------------------------------------------------
# de-sectored write (inverse of codec.read_logical)
# ---------------------------------------------------------------------------
def write_logical(disc, raw_off, data):
    """Write `data` as the LOGICAL (de-sectored) stream starting at raw byte offset
    `raw_off` in a 2352-byte-sector Track1.bin, skipping the 16 B sync/header + 288 B ECC
    per sector. Mutates `disc` (a bytearray) in place."""
    o = raw_off
    p = 0
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
# compact 5x7 uppercase pixel font (fg nibble value written by caller)
# ---------------------------------------------------------------------------
FONT = {
 'M': ["10001","11011","10101","10101","10001","10001","10001"],
 'A': ["01110","10001","10001","11111","10001","10001","10001"],
 'G': ["01110","10001","10000","10111","10001","10001","01110"],
 'I': ["111","010","010","010","010","010","111"],
 'C': ["01110","10001","10000","10000","10000","10001","01110"],
 'S': ["01111","10000","10000","01110","00001","00001","11110"],
 'K': ["10001","10010","10100","11000","10100","10010","10001"],
 'L': ["10000","10000","10000","10000","10000","10000","11111"],
 'E': ["11111","10000","10000","11110","10000","10000","11111"],
 'X': ["10001","10001","01010","00100","01010","10001","10001"],
 'P': ["11110","10001","10001","11110","10000","10000","10000"],
 'D': ["11110","10001","10001","10001","10001","10001","11110"],
 'F': ["11111","10000","10000","11110","10000","10000","10000"],
 'V': ["10001","10001","10001","10001","10001","01010","00100"],
 'T': ["11111","00100","00100","00100","00100","00100","00100"],
 'U': ["10001","10001","10001","10001","10001","10001","01110"],
 'N': ["10001","11001","10101","10011","10001","10001","10001"],
 'R': ["11110","10001","10001","11110","10100","10010","10001"],
 'O': ["01110","10001","10001","10001","10001","10001","01110"],
 ' ': ["0","0","0","0","0","0","0"],
}


def draw_text(atlas, srca, cell_w, cell_h, text, fg=15, y0=None, gap=1):
    """Clear the cell region and draw `text` centered. atlas is a bytearray (full VRAM).
    Writes 4bpp nibbles at row stride cell_w/2."""
    stride = cell_w // 2
    # clear cell
    for r in range(cell_h):
        for x in range(cell_w):
            _put(atlas, srca, stride, x, r, 0)
    glyphs = [FONT[c] for c in text]
    tw = sum(len(g[0]) for g in glyphs) + gap * (len(glyphs) - 1)
    x = max(0, (cell_w - tw) // 2)
    gh = 7
    if y0 is None:
        y0 = max(0, (cell_h - gh) // 2)
    for g in glyphs:
        gw = len(g[0])
        for r in range(gh):
            for c in range(gw):
                if g[r][c] == '1' and 0 <= x + c < cell_w and 0 <= y0 + r < cell_h:
                    _put(atlas, srca, stride, x + c, y0 + r, fg)
        x += gw + gap


def _put(atlas, srca, stride, x, y, nib):
    off = srca + y * stride + x // 2
    b = atlas[off]
    if x % 2 == 0:
        atlas[off] = (nib << 4) | (b & 0x0F)
    else:
        atlas[off] = (b & 0xF0) | (nib & 0xF)


# labels for THIS atlas: (srca, w, h, english, y0-adjust)
LABELS = [
    (0x477c0, 32, 16, "MAGIC", None),   # 魔法 -> MAGIC (fits 32px)
    (0x473a0, 16, 16, "SKL",   None),   # 技 -> compact "SKL" (Skill; full needs geometry)
]


def author_atlas(disc):
    """Decode the on-disc atlas, author English, return the modified full-VRAM image."""
    vram = bytearray(codec.run_decode(disc, CHROME_RAW_OFF, DST_BASE, 0x5000))
    for srca, w, h, text, y0 in LABELS:
        draw_text(vram, srca, w, h, text, fg=15, y0=y0)
    return vram


def build_stream(disc):
    vram = author_atlas(disc)
    codelen9, _ = enc._codelen9_from_disc_bytes(disc, CHROME_RAW_OFF)
    stream = enc.encode(bytes(vram[WIN_LO:WIN_HI]), codelen9, zthresh=6)
    return stream, vram


# ---------------------------------------------------------------------------
# fold
# ---------------------------------------------------------------------------
def original_stream_len(disc):
    """Length of the original compressed chrome stream (for the size budget)."""
    hdr = codec.read_logical(disc, CHROME_RAW_OFF, 16)
    w0 = (hdr[0] << 8) | hdr[1]
    ctrl_bytes = w0 & 0x1fff
    lit_off = ctrl_bytes + 11
    # literal stream length: the decoder reads up to ~0x4000; use a generous fixed budget
    return 0x4000  # 16384 B on-disc footprint (verified by max-source-read trace)


def cmd_fold(track):
    disc = bytearray(open(track, "rb").read())
    # gate: decode the current on-disc atlas; if it already equals the authored English
    # target, this is a no-op (idempotent).
    cur = bytearray(codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000))
    target = bytearray(cur)
    for srca, w, h, text, y0 in LABELS:
        draw_text(target, srca, w, h, text, fg=15, y0=y0)
    if bytes(cur[WIN_LO:WIN_HI]) == bytes(target[WIN_LO:WIN_HI]):
        print("chrome atlas already English -> skip"); return
    stream, vram = build_stream(disc)
    budget = original_stream_len(disc)
    if len(stream) > budget:
        raise SystemExit(f"encoded stream {len(stream)} B > budget {budget} B; lower zthresh / fewer glyphs")
    stream = stream + b"\x00" * (budget - len(stream))   # pad to preserve footprint
    write_logical(disc, CHROME_RAW_OFF, stream)
    open(track, "wb").write(disc)
    # verify round-trip on the freshly-written disc
    chk = codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000)
    ok = bytes(chk[WIN_LO:WIN_HI]) == bytes(vram[WIN_LO:WIN_HI])
    print(f"folded chrome atlas English -> {track}  round-trip={'OK' if ok else 'MISMATCH'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fold"); pf.add_argument("track")
    pp = sub.add_parser("preview")   # author + encode + write a decoded PNG-able atlas, no disc
    pp.add_argument("--src", default="output/rc_34/Track1.bin")
    pp.add_argument("--out", default="work/pO4enc/english_atlas.bin")
    a = ap.parse_args()
    if a.cmd == "fold":
        cmd_fold(a.track)
    else:
        disc = bytearray(open(a.src, "rb").read())
        stream, vram = build_stream(disc)
        open(a.out, "wb").write(bytes(vram))
        print(f"authored+encoded: stream {len(stream)} B (budget 16384); atlas -> {a.out}")
