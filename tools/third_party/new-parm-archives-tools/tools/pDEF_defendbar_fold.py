#!/usr/bin/env python3
"""pDEF_defendbar_fold.py — author English into the in-battle DEFEND-BAR VDP1 sprite-atlas
cells (防御実行 / 防御 / 回避), re-encode via pO4_chrome_encode, and fold the compressed
stream back into Track1.bin IN PLACE.

CONFIRMED SOURCE (rc_37, state user-battle-defend-bar-rc37, disc output/rc_37):
The defend bar is NOT a VDP2 tile-font (blanking all four VDP2 VRAM quarters via
--inject-vram2 left the bar text intact). It is the **VDP1 chrome sprite atlas** — the same
compressed block that carries 魔法/技/ring-labels. The three label textures live in the
decoded chrome window (disc 0xEBE910 -> VDP1 VRAM 0x44000..0x4afe0), each 32x16 4bpp:
  * 0x4a920 = 防御 (Defend)  -- drawn TWICE: centre bar (160,48) AND L-box first half (32,43)
  * 0x4ade0 = 実行 (Execute) -- L-box second half (64,43); together 防御実行 = "Execute Defense"
  * 0x4aee0 = 回避 (Evade)   -- R-box (272,43)
All three decode BYTE-EXACT from disc 0xEBE910 via pO4_chrome_codec (verified vs the live
VDP1 VRAM dump). The 80x24 box frame at 0x4aa20 is a plain rounded-rect graphic (untouched).

DESIGN (0x4a920 is SHARED by the centre label and the L-box, so it must read as one word):
  * 0x4a920 -> "DEFEND"  -> centre bar reads "DEFEND"; L-box first word "DEFEND"
  * 0x4ade0 -> "!"       -> L-box reads "DEFEND!" (= 防御実行, commit/execute the defend)
  * 0x4aee0 -> "EVADE"   -> R-box reads "EVADE"
Canon: menus/battle_text.py (= TrekkiesUnite G1) 防御->Defend, 回避->Evade. 防御実行 has no
single G1 term (DM-specific compound 防御+実行); rendered "DEFEND!" to fit the shared cell and
the fixed 32px width. See docs/lanes/pDEF_defend-bar.md + exceptions.json entry.

This EXTENDS the shipped pO4_chrome_fold / pO4b_chrome_labels_fold pipeline (same 0xEBE910
stream, same 0x44000-0x4afe0 window, same 0x4000 on-disc budget). It CHAINS: it decodes the
CURRENT on-disc atlas (which already carries MAGIC/SKL + the ring labels), draws ONLY the
three defend-bar cells, and re-encodes the whole window (so all prior English is preserved
verbatim). Build order: pO4_chrome_fold -> pO4b_chrome_labels_fold -> pDEF_defendbar_fold.
"""
import argparse, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_chrome_codec as codec
import pO4_chrome_encode as enc
import pO4_chrome_fold as cf   # reuse _put, write_logical, budget
import battle_skillgain_gfx as tf   # Title-Case proportional font (_fit) -- G1 canon casing

CHROME_RAW_OFF = 0xEBE910
DST_BASE = 0x44000
WIN_LO, WIN_HI = 0x44000, 0x4afe0
STREAM_BUDGET = 0x4000        # 16384 B on-disc footprint (shared with pO4_chrome_fold)

# CANONICAL Grandia (Title Case), per the user's original-Grandia reference: Defend / Evasion.
# 回避 -> "Evasion" (canon; fits the 32px R cell squeezed-but-legible). 防御 -> "Defend".
#
# ✅ rc_46's "Endure" wall is RESOLVED by the lane-W2 ATLAS REPACK (tools/pW2_atlas_repack.py,
# build step 8f4, runs AFTER this fold): the L-box first cell is repointed OFF the shared/scaled
# 0x4a920 (which stays "Defend", drawn only by the scaled centre) to a new 32x16 home @0x4a6a0,
# and "Endure" is authored 64px wide across 0x4a6a0 + 0x4ade0. The 0x4ade0 (実行) cell is
# therefore OWNED BY pW2 now — this fold must NOT touch it (chain idempotency). Defend
# display-list geometry table: HWRAM 0x060c9afe / disc 0xead4de (centre entry w7@0xead4ec=
# 0x0d24, w8@0xead4ee=0x0410; SRCA_word = 0x8800 + w7). See docs/lanes/laneW2-atlas-repack.md.
LABELS = [
    (0x4a920, 32, 16, "Defend"),   # 防御  (centre scaled bar; L-box repointed away by pW2)
    # 回避/"Evasion" is OWNED BY pW2 since the lane-W3 re-fit: the R-box element was
    # repointed to a 48x16 home @0x4a7a0 (pW2_atlas_repack authors it there and blanks the
    # old 0x4aee0 cell). This fold must NOT touch either cell (chain idempotency).
]


def _draw(vram, srca, w, h, text):
    """Clear the 4bpp cell and draw `text` centred, Title Case via tf._fit (squeeze-to-fit)."""
    stride = w // 2
    arr = tf._fit(text, w, h)
    for y in range(h):
        for x in range(w):
            cf._put(vram, srca, stride, x, y, 15 if arr[y][x] else 0)


def author_atlas(disc):
    """Decode the CURRENT on-disc atlas (keeps prior English) and draw the defend-bar cells."""
    vram = bytearray(codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000))
    for srca, w, h, text in LABELS:
        _draw(vram, srca, w, h, text)
    return vram


def _is_english(vram):
    """True if the atlas already carries our defend-bar English (idempotency gate)."""
    target = bytearray(vram)
    for srca, w, h, text in LABELS:
        _draw(target, srca, w, h, text)
    return bytes(vram[WIN_LO:WIN_HI]) == bytes(target[WIN_LO:WIN_HI])


def cmd_fold(track):
    disc = bytearray(open(track, "rb").read())
    cur = bytearray(codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000))
    if _is_english(cur):
        print("defend bar already English -> skip"); return
    vram = author_atlas(disc)
    codelen9, _ = enc._codelen9_from_disc_bytes(bytes(disc), CHROME_RAW_OFF)
    stream = enc.encode_fit(bytes(vram[WIN_LO:WIN_HI]), codelen9, budget=STREAM_BUDGET)
    if len(stream) > STREAM_BUDGET:
        raise SystemExit(f"encoded stream {len(stream)} B > budget {STREAM_BUDGET} B")
    stream = stream + b"\x00" * (STREAM_BUDGET - len(stream))
    cf.write_logical(disc, CHROME_RAW_OFF, stream)
    open(track, "wb").write(disc)
    chk = codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000)
    ok = bytes(chk[WIN_LO:WIN_HI]) == bytes(vram[WIN_LO:WIN_HI])
    print(f"folded defend bar (Defend) -> {track}  round-trip={'OK' if ok else 'MISMATCH'}")


def cmd_atlas(src, out):
    """Write the authored FULL VDP1-VRAM image (for the --inject-vram1 oracle / PNG check)."""
    disc = bytearray(open(src, "rb").read())
    vram = author_atlas(disc)
    open(out, "wb").write(bytes(vram))
    codelen9, _ = enc._codelen9_from_disc_bytes(bytes(disc), CHROME_RAW_OFF)
    stream = enc.encode_fit(bytes(vram[WIN_LO:WIN_HI]), codelen9, budget=STREAM_BUDGET)
    print(f"authored atlas -> {out}  (encoded {len(stream)} B / budget {STREAM_BUDGET})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fold"); pf.add_argument("track")
    pa = sub.add_parser("atlas")
    pa.add_argument("--src", default="output/rc_37/Track1.bin")
    pa.add_argument("--out", default="work/pDEF_01/english_atlas.bin")
    a = ap.parse_args()
    if a.cmd == "fold":
        cmd_fold(a.track)
    else:
        cmd_atlas(a.src, a.out)
