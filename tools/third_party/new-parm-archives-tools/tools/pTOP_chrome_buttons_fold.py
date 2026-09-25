#!/usr/bin/env python3
"""pTOP_chrome_buttons_fold.py — author English into the in-battle STRATEGY submenu TOP
BUTTON cells of the battle-chrome VDP1 sprite atlas (disc 0xEBE910 -> VDP1 VRAM 0x44000),
re-encode via pO4_chrome_encode, and fold the stream back into Track1.bin IN PLACE.

Same atlas + pipeline as pO4/pO4b/pDEF (composes; runs AFTER them, decodes the atlas that
already carries MAGIC/SKL + ring labels + defend bar, adds ONLY the strategy-button cells,
re-encodes the whole 0x44000..0x4afe0 window).

SCOPE (lane pTOP) — the three STRATEGY submenu top buttons. Located by parsing the VDP1
command list at the strat-open state (work/pVDF_01/strat_open.savestate), sprites @ y~40-48:

  middle  作戦設定    = 0x48160(作戦)+0x48260(設定)          -> "Tactics"
  left    個人作戦実行 = 0x489a0(個人)+0x48aa0(作戦)+0x48ba0(実行) -> "Single" + " Tactics"
  right   全体作戦実行 = 0x48ca0(全体)+0x48aa0(作戦)+0x48ba0(実行) -> "Party"  + " Tactics"

The left/right buttons SHARE the 作戦実行 tail cells (0x48aa0/0x48ba0) -- and both English
buttons share the " Tactics" suffix, so the share maps cleanly: author "Single"/"Party" into
the distinguishing cell and " Tactics" once into the shared pair. Each cell is 32x16 4bpp,
contiguous in atlas memory (0x100 B apart). Title Case (tf font) to match the shipped row
labels (個人作戦->"Single" / 全体作戦->"Party") and the canonical G1 STRATEGY screen.

CANONICAL wording: the live original-Grandia STRATEGY screen (DM reuses that engine) reads
"Single Tactics" / "Tactics" / "Party Tactics" (user-supplied reference 2026-07-05). Recorded
in dictionary/exceptions.json. See docs/lanes/pVDF2_strategy-menu.md + pTOP_strategy-buttons.md.
"""
import argparse, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_chrome_codec as codec
import pO4_chrome_encode as enc
import pO4b_chrome_labels_fold as pO4b   # reuse write_logical + de-sector constants
import battle_skillgain_gfx as tf         # proportional Title-Case font (_fit)

CHROME_RAW_OFF = 0xEBE910
DST_BASE = 0x44000
WIN_LO, WIN_HI = 0x44000, 0x4afe0
STREAM_BUDGET = 0x4000
CELL_W, CELL_H = 32, 16

# (list-of-cell-srca spanning the word left-to-right, English text)
BUTTONS = [
    ([0x48160, 0x48260], "Tactics"),   # 作戦設定 (middle, config)
    ([0x489a0],          "Single"),    # 個人 (left distinguishing)
    ([0x48ca0],          "Party"),     # 全体 (right distinguishing)
    ([0x48aa0, 0x48ba0], " Tactics"),  # 作戦実行 (SHARED tail of left+right)
]

# Strategy VALUE presets (マニュアル/正々堂々/準備万全/他力本願/十人十色/安全第一/狂喜乱舞/
# 卑怯千万 -> Manual/Play Fair/Power Up/Withdraw/Each Own/Safety/Go Wild/Meanie, canon G1):
# OWNED BY THE LANE-W2 ATLAS REPACK since rc_47 (tools/pW2_atlas_repack.py, step 8f4, runs
# AFTER this fold). pW2 shrinks the 8 cells 64x16 -> 48x16 and moves them to 0x180-stride
# homes 0x49920..0x4a520 (repointing their geometry triples at disc 0xEAD42E+0x14*i), which
# frees 0x4a520..0x4a920 for the "Moves" 48px + "Endure" cells. This fold must NOT touch
# the 0x49920..0x4a920 region any more (chain idempotency). See docs/lanes/laneW2-atlas-repack.md.


def _write_array(atlas, cells, arr, ink=15):
    """Write an (CELL_H, len(cells)*CELL_W) 0/1 bitmap across `cells` (each CELL_W wide,
    a separate 4bpp region stride=CELL_W//2). Clears+draws every pixel in the span."""
    stride = CELL_W // 2
    for i, srca in enumerate(cells):
        for y in range(CELL_H):
            for x in range(CELL_W):
                nib = ink if arr[y][i * CELL_W + x] else 0
                off = srca + y * stride + x // 2
                b = atlas[off]
                atlas[off] = ((nib << 4) | (b & 0x0F)) if x % 2 == 0 else ((b & 0xF0) | (nib & 0xF))


def _write_flat(atlas, srca, w, h, arr, ink=15):
    """Write an (h, w) 0/1 bitmap into a single contiguous w x h 4bpp cell (stride=w//2)."""
    stride = w // 2
    for y in range(h):
        for x in range(w):
            nib = ink if arr[y][x] else 0
            off = srca + y * stride + x // 2
            b = atlas[off]
            atlas[off] = ((nib << 4) | (b & 0x0F)) if x % 2 == 0 else ((b & 0xF0) | (nib & 0xF))


def _draw(vram):
    for cells, text in BUTTONS:
        arr = tf._fit(text, len(cells) * CELL_W, CELL_H)
        _write_array(vram, cells, arr, ink=15)
    # 作戦変更 (the VALUE-PICKER mode's middle button, discovered lane W2): drawn as
    # [0x48160]+[0x488a0] at the SAME screen cells as the normal mode's [0x48160]+[0x48260]
    # ("Tactics"). 0x488a0 (変更) has exactly one display-list ref (picker header), so mirror
    # the "ics" half there -> the picker header also reads "Tactics".
    vram[0x488a0:0x488a0 + 0x100] = vram[0x48260:0x48260 + 0x100]


def author_atlas(disc):
    vram = bytearray(codec.run_decode(disc, CHROME_RAW_OFF, DST_BASE, 0x5000))
    _draw(vram)
    return vram


def build_stream(disc):
    vram = author_atlas(disc)
    codelen9, _ = enc._codelen9_from_disc_bytes(disc, CHROME_RAW_OFF)
    stream = enc.encode_fit(bytes(vram[WIN_LO:WIN_HI]), codelen9, budget=STREAM_BUDGET)
    return stream, vram


def cmd_fold(track):
    disc = bytearray(open(track, "rb").read())
    cur = bytearray(codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000))
    target = bytearray(cur)
    _draw(target)
    if bytes(cur[WIN_LO:WIN_HI]) == bytes(target[WIN_LO:WIN_HI]):
        print("chrome strategy buttons already English -> skip"); return
    stream, vram = build_stream(disc)
    if len(stream) > STREAM_BUDGET:
        raise SystemExit(f"encoded stream {len(stream)} B > budget {STREAM_BUDGET} B")
    stream = stream + b"\x00" * (STREAM_BUDGET - len(stream))
    pO4b.write_logical(disc, CHROME_RAW_OFF, stream)
    open(track, "wb").write(disc)
    chk = codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000)
    ok = bytes(chk[WIN_LO:WIN_HI]) == bytes(vram[WIN_LO:WIN_HI])
    print(f"folded chrome strategy buttons -> {track}  round-trip={'OK' if ok else 'MISMATCH'} "
          f"(stream {len(stream)} B incl pad)")


def cmd_preview(a):
    disc = bytearray(open(a.src, "rb").read())
    vram = author_atlas(disc)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "wb").write(bytes(vram))
    print(f"authored strategy-button atlas -> {a.out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fold"); pf.add_argument("track")
    pp = sub.add_parser("preview")
    pp.add_argument("--src", default="output/rc_41/Track1.bin")
    pp.add_argument("--out", default="work/pTOP_01/english_button_atlas.bin")
    a = ap.parse_args()
    cmd_fold(a.track) if a.cmd == "fold" else cmd_preview(a)
