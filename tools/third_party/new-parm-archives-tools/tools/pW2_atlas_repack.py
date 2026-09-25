#!/usr/bin/env python3
"""pW2_atlas_repack.py — battle-chrome VDP1 atlas REPACK (lane W2): relocate co-resident
cells to create >=0x180-byte homes inside the decoded window (0x44000..0x4afe0), repoint
every moved cell's geometry triple (w6/w7/w8) on disc, and author the three width-walled
labels the repack unblocks:

  * 技         -> "Moves"  in a NEW 48x16 home @0x4a520 (was 16x16 "SKL" @0x473a0 — the
                  pO4d width wall; canon per rc_45/46 is "Moves", G1 command header).
  * 防御実行   -> "Endure" (canon, user-supplied G1 defend-bar reference): the L-box first
                  cell was SHARED with the SCALED centre-bar sprite (CMDCTRL 0x1001,
                  the rc_46 trap) — repointed to a NEW 32x16 home @0x4a6a0; "Endure" is
                  authored 64px wide split across 0x4a6a0 (left) + 0x4ade0 (right, the
                  formerly-blanked 実行 cell). The scaled centre keeps its own 0x4a920
                  cell ("Defend") UNTOUCHED — no scaled-sprite repoint.
  * strategy VALUES (the space donors): the 8 preset cells shrink 64x16 -> 48x16 and move
                  to 0x180-stride homes 0x49920..0x4a520, freeing 0x400 bytes
                  (0x4a520..0x4a920) = the new homes above + 0x180 spare @0x4a7a0.
  * 回避       -> "Evasion" RE-FIT (lane W3, rc_47+ polish): rc_46 shipped it squeezed
                  into the 32x16 R-box cell @0x4aee0. The R-box element @0xEAD546 (single
                  disc copy, raw+logical scan) is repointed to the 0x180 spare @0x4a7a0 as
                  a roomy 48x16 texture; rect widened 32->48, still centred in the 80px
                  R-box frame (x0 0xf8->0xf0, x1 0x118->0x120). Old 0x4aee0 cell blanked
                  (unreferenced after the repoint). pDEF no longer authors Evasion.

THE GEOMETRY AUTHORITY (verified this lane, rc_46):
Every chrome sprite is emitted by the display-list interpreter (pO4d: 0x0603320e /
emitter 0x06033760) from table entries whose tail is a triple  w6 w7 w8  with
  w6 = 2*w7  (must be kept consistent — the rc_46 "scrambled centre" trap was a w7-only
              patch leaving w6 stale),
  w7 = (VDP1_VRAM - 0x44000) >> 3   (SRCA word = 0x8800 + w7),
  w8 = CMDSIZE ((w/8)<<8 | h).
Whole-disc scans (raw + de-sectored logical) prove each patched triple exists EXACTLY once
(3x 技, 1x L-box1 [the 2nd 0x4a920 ref; the 1st @0xEAD4EA is the scaled centre, untouched],
8x values), all inside the /BATLE resident archive (HWRAM = logical(raw 0xEA0000) +
0x060BE170, verified vs live battle wram). The per-BBG LWRAM tables (0x0140-prefixed) use
a DIFFERENT cell grid (0x49a60/0x180, 24x20 @0x473c8) and never appear in live battle VDP1
cmd lists across skill/strategy/defend states — a different VRAM epoch, not this atlas.

PIPELINE POSITION: build step 8f4, AFTER pO4 -> pO4b -> pDEF -> pTOP. This tool now OWNS
the strategy VALUE cells (removed from pTOP) and the defend L-box 2nd cell content
(removed from pDEF), so the whole 4+1 fold chain stays idempotent on the repacked atlas.
Size-preserving (stream re-encoded into the same 0x4000 footprint), byte-gated, round-trip
self-checked, deterministic. See docs/lanes/laneW2-atlas-repack.md.
"""
import argparse, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_chrome_codec as codec
import pO4_chrome_encode as enc
import pO4_chrome_fold as cf            # write_logical + _put
import battle_skillgain_gfx as tf       # Title-Case proportional font (_fit)

CHROME_RAW_OFF = 0xEBE910
DST_BASE = 0x44000
WIN_LO, WIN_HI = 0x44000, 0x4afe0
STREAM_BUDGET = 0x4000
ARCHIVE_RAW_BASE = 0xEA0000             # /BATLE resident archive on disc (raw)
ARCHIVE_HWRAM_BASE = 0x060BE170         # ... loaded here at battle start (verified live)
RAW_SECTOR, SYNC_HEADER, USER_DATA = 2352, 16, 2048

# ---------------------------------------------------------------------------
# Geometry patches: (raw disc offset of w6, old (w6,w7,w8), new (w6,w7,w8))
# ---------------------------------------------------------------------------
def _t(w7, w8):
    return (2 * w7, w7, w8)

_VAL_OLD_W7 = [0x0b24, 0x0b64, 0x0ba4, 0x0be4, 0x0c24, 0x0c64, 0x0ca4, 0x0ce4]
_VAL_NEW_W7 = [0x0b24, 0x0b54, 0x0b84, 0x0bb4, 0x0be4, 0x0c14, 0x0c44, 0x0c74]

GEOM = (
    # 技 (skill/magic HUD header) — 3 table copies, all -> new 48x16 Moves home 0x4a520
    [(off, _t(0x0674, 0x0210), _t(0x0ca4, 0x0610))
     for off in (0xEABC3C, 0xEABD78, 0xEAC09E)]
    # defend-bar L-box FIRST cell (2nd 0x4a920 ref) -> new 32x16 Endure-left home 0x4a6a0.
    # (The 1st ref @0xEAD4EA is the SCALED centre — deliberately NOT here.)
    + [(0xEAD522, _t(0x0d24, 0x0410), _t(0x0cd4, 0x0410))]
    # 8 strategy VALUE presets: 64x16 @0x200 stride -> 48x16 @0x180 stride
    + [(0xEAD42E + 0x14 * i, _t(_VAL_OLD_W7[i], 0x0810), _t(_VAL_NEW_W7[i], 0x0610))
       for i in range(8)]
    # defend-bar R-box (回避 -> "Evasion", lane W3): 32x16 @0x4aee0 -> 48x16 @0x4a7a0 spare
    + [(0xEAD546, _t(0x0ddc, 0x0410), _t(0x0cf4, 0x0610))]
)

# On-screen RECT patches (single 16-bit words). These chrome sprites are ALL scaled
# (CMDCTRL 0x1001): the dst rect does NOT follow CMDSIZE — it comes from the element's
# coordinate words. Element stream format (cracked this lane; the pO4d "w8 drives the
# render width" claim was a misread — w8 only drives CMDSIZE/texture):
#   [w6 w7 w8] 2081 <mode> x0 y0 x1 y1     (rect w = x1-x0, h = y1-y0; screen = coord+40
#                                           for mode 0000; mode 0008 = runtime-positioned)
# So a texture-size change MUST be paired with an x1 (and optionally x0) edit or the new
# texture is squeezed into the old rect (observed live before this fix).
RECTS = (
    # 技 -> Moves: rect 16 -> 48 wide (x1 = x0 + 0x30) in all 3 display-list copies
    [(0xEABC3C + 14, 0x0068, 0x0088),
     (0xEABD78 + 14, 0x001c, 0x003c),
     (0xEAC09E + 14, 0x0104, 0x0124)]
    # values: rect 64 -> 48 wide, centred in the old box (x0 += 8, x1 -= 8)
    + [p for i in range(8) for p in
       ((0xEAD42E + 0x14 * i + 10, 0x0000, 0x0008),
        (0xEAD42E + 0x14 * i + 14, 0x0040, 0x0038))]
    # Evasion (lane W3): rect 32 -> 48 wide, centred in the 80px R-box frame
    + [(0xEAD546 + 10, 0x00f8, 0x00f0),
       (0xEAD546 + 14, 0x0118, 0x0120)]
    # Endure L-box / centre rects unchanged (same 32x16)
)

# ---------------------------------------------------------------------------
# Atlas pixel layout (all inside the freed / repacked regions)
# ---------------------------------------------------------------------------
# canon G1 wording (pTOP rc_43/44); ALL-CAPS casing per rc_47 user decision 1 — G1's
# tactics screen renders the VALUE presets in caps (MANUAL / PLAY FAIR,
# docs/lanes/pREF/pREF-battle-tactics-screen.png) while the buttons/row labels stay
# Title Case (unchanged here). All 8 fit 48px natively in the tf font (PLAY FAIR = 48px).
VALUES = ["MANUAL", "PLAY FAIR", "POWER UP", "WITHDRAW",
          "EACH OWN", "SAFETY", "GO WILD", "MEANIE"]
VAL_BASE, VAL_STRIDE, VAL_W, VAL_H = 0x49920, 0x180, 48, 16
MOVES_SRCA, MOVES_W, MOVES_H = 0x4a520, 48, 16           # 技 -> "Moves" (canon)
ENDURE_L, ENDURE_R = 0x4a6a0, 0x4ade0                    # 防御実行 -> "Endure" (canon), 2x32x16
OLD_WAZA_SRCA, OLD_WAZA_LEN = 0x473a0, 0x80              # unreferenced after repoint: blanked
EVASION_SRCA, EVASION_W, EVASION_H = 0x4a7a0, 48, 16     # 回避 -> "Evasion" re-fit (lane W3)
OLD_EVASION_SRCA, OLD_EVASION_LEN = 0x4aee0, 0x100       # unreferenced after repoint: blanked


def _draw(vram, srca, w, h, arr):
    stride = w // 2
    for y in range(h):
        for x in range(w):
            cf._put(vram, srca, stride, x, y, 15 if arr[y][x] else 0)


def _clear(vram, srca, nbytes):
    vram[srca:srca + nbytes] = b"\x00" * nbytes


def author_atlas_from(vram):
    """Apply the repack pixel layout to a decoded full-VRAM image (in place)."""
    _clear(vram, OLD_WAZA_SRCA, OLD_WAZA_LEN)            # old 技 cell: unreferenced now
    _clear(vram, VAL_BASE, 0x1000)                       # whole 0x49920..0x4a920 region
    for i, text in enumerate(VALUES):
        _draw(vram, VAL_BASE + i * VAL_STRIDE, VAL_W, VAL_H, tf._fit(text, VAL_W, VAL_H))
    _draw(vram, MOVES_SRCA, MOVES_W, MOVES_H, tf._fit("Moves", MOVES_W, MOVES_H))
    arr = tf._fit("Endure", 64, 16)
    _clear(vram, ENDURE_R, 0x100)
    _draw(vram, ENDURE_L, 32, 16, [row[0:32] for row in arr])
    _draw(vram, ENDURE_R, 32, 16, [row[32:64] for row in arr])
    # 回避 -> "Evasion" at 48x16 in the (formerly spare) 0x4a7a0 home; old cell blanked
    _draw(vram, EVASION_SRCA, EVASION_W, EVASION_H,
          tf._fit("Evasion", EVASION_W, EVASION_H))
    _clear(vram, OLD_EVASION_SRCA, OLD_EVASION_LEN)
    return vram


def author_atlas(disc):
    vram = bytearray(codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000))
    return author_atlas_from(vram)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------
def _rd_triple(disc, raw):
    return tuple(int.from_bytes(disc[raw + 2 * i: raw + 2 * i + 2], "big") for i in range(3))


def _wr_triple(disc, raw, t):
    for i, v in enumerate(t):
        disc[raw + 2 * i: raw + 2 * i + 2] = v.to_bytes(2, "big")


def word_patches():
    """Flatten GEOM triples + RECT words into (raw, oldword, newword) 16-bit patches."""
    out = []
    for raw, old, new in GEOM:
        for i in range(3):
            out.append((raw + 2 * i, old[i], new[i]))
    out.extend(RECTS)
    # drop no-op patches (e.g. value0 "Manual" keeps its w6/w7 home) — they would make
    # the old/new gate read "mixed" forever
    return [(raw, old, new) for raw, old, new in out if old != new]


def geom_state(disc):
    """'old' / 'new' / 'mixed' / raises on unknown words."""
    st = set()
    for raw, old, new in word_patches():
        cur = int.from_bytes(disc[raw:raw + 2], "big")
        if cur == old:
            st.add("old")
        elif cur == new:
            st.add("new")
        else:
            raise SystemExit(f"geometry word @raw {raw:#x} is neither vanilla nor repacked: "
                             f"{cur:#06x} (expected {old:#06x} or {new:#06x})")
    return st.pop() if len(st) == 1 else "mixed"


def raw_to_logical(raw):
    """Logical (de-sectored) offset of `raw` relative to ARCHIVE_RAW_BASE."""
    o, log = ARCHIVE_RAW_BASE, 0
    while True:
        sec, ino = o // RAW_SECTOR, o % RAW_SECTOR
        if ino < SYNC_HEADER:
            ino = SYNC_HEADER
            o = sec * RAW_SECTOR + ino
        end = sec * RAW_SECTOR + SYNC_HEADER + USER_DATA
        if o <= raw < end:
            return log + (raw - o)
        log += end - o
        o = (sec + 1) * RAW_SECTOR + SYNC_HEADER


def hwram_addr(raw):
    return ARCHIVE_HWRAM_BASE + raw_to_logical(raw)


# ---------------------------------------------------------------------------
# fold
# ---------------------------------------------------------------------------
def cmd_fold(track):
    disc = bytearray(open(track, "rb").read())
    gs = geom_state(disc)
    cur = bytearray(codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000))
    target = author_atlas_from(bytearray(cur))
    atlas_done = bytes(cur[WIN_LO:WIN_HI]) == bytes(target[WIN_LO:WIN_HI])
    if gs == "new" and atlas_done:
        print("atlas repack already applied -> skip")
        return
    # geometry (triples + rect words)
    for raw, old, new in word_patches():
        disc[raw:raw + 2] = new.to_bytes(2, "big")
    # atlas
    codelen9, _ = enc._codelen9_from_disc_bytes(bytes(disc), CHROME_RAW_OFF)
    stream = enc.encode_fit(bytes(target[WIN_LO:WIN_HI]), codelen9, budget=STREAM_BUDGET)
    if len(stream) > STREAM_BUDGET:
        raise SystemExit(f"encoded stream {len(stream)} B > budget {STREAM_BUDGET} B")
    stream = stream + b"\x00" * (STREAM_BUDGET - len(stream))
    cf.write_logical(disc, CHROME_RAW_OFF, stream)
    open(track, "wb").write(disc)
    chk = codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000)
    ok = bytes(chk[WIN_LO:WIN_HI]) == bytes(target[WIN_LO:WIN_HI])
    assert geom_state(bytearray(open(track, "rb").read())) == "new"
    print(f"folded atlas REPACK (Moves 48px + Endure + Evasion 48px + values@48px) -> {track}  "
          f"round-trip={'OK' if ok else 'MISMATCH'} (stream {len(stream)} B incl pad, "
          f"geometry was {gs})")
    if not ok:
        raise SystemExit("round-trip MISMATCH after fold")


def cmd_atlas(a):
    disc = bytearray(open(a.src, "rb").read())
    vram = author_atlas(disc)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "wb").write(bytes(vram))
    codelen9, _ = enc._codelen9_from_disc_bytes(bytes(disc), CHROME_RAW_OFF)
    stream = enc.encode_fit(bytes(vram[WIN_LO:WIN_HI]), codelen9, budget=STREAM_BUDGET)
    dec = enc._rom_decode_raw(stream, DST_BASE)
    n = sum(1 for i in range(WIN_LO, WIN_HI) if dec[i] != vram[i])
    print(f"authored repacked atlas -> {a.out}  (encoded {len(stream)} B / {STREAM_BUDGET}; "
          f"round-trip {'BIT-EXACT' if n == 0 else str(n) + ' MISMATCH'})")


def cmd_hwram(a):
    """Emit HWRAM inject bins for the live oracle: the two patched table spans, built from
    the disc logical stream (== the battle-resident copy) with the GEOM patches applied."""
    disc = bytearray(open(a.src, "rb").read())
    for raw, old, new in word_patches():
        if int.from_bytes(disc[raw:raw + 2], "big") == old:
            disc[raw:raw + 2] = new.to_bytes(2, "big")
    spans = [("geomA_waza", 0xEABC3C, 0xEAC0B0),      # covers the 3 技 triples + rect words
             ("geomB_valdef", 0xEAD42E, 0xEAD55E)]    # values + defend-table triples + rects
                                                      # (extended past 0xEAD54E for the W3
                                                      #  Evasion element rect words)
    os.makedirs(a.outdir, exist_ok=True)
    for name, lo, hi in spans:
        data = codec.read_logical(bytes(disc), lo, raw_to_logical(hi) - raw_to_logical(lo))
        p = os.path.join(a.outdir, name + ".bin")
        open(p, "wb").write(data)
        print(f"{p}  inject at HWRAM {hwram_addr(lo):#010x}  ({len(data)} B)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fold"); pf.add_argument("track")
    pa = sub.add_parser("atlas")
    pa.add_argument("--src", default="output/rc_46/Track1.bin")
    pa.add_argument("--out", default="work/pW2_01/english_atlas.bin")
    ph = sub.add_parser("hwram")
    ph.add_argument("--src", default="output/rc_46/Track1.bin")
    ph.add_argument("--outdir", default="work/pW2_01")
    a = ap.parse_args()
    if a.cmd == "fold":
        cmd_fold(a.track)
    elif a.cmd == "atlas":
        cmd_atlas(a)
    else:
        cmd_hwram(a)
