#!/usr/bin/env python3
"""pO4b_chrome_labels_fold.py — author English into the REMAINING battle-chrome VDP1
sprite-atlas LABEL cells (the command-ring option labels), re-encode via
pO4_chrome_encode, and fold the compressed stream back into Track1.bin IN PLACE.

This EXTENDS the shipped pO4_chrome_fold pipeline (which did 魔法->MAGIC @0x477c0,
技->SKL @0x473a0). It is a SEPARATE tool (pO4_chrome_fold is depended on elsewhere and
must not be edited) that runs AFTER pO4_chrome_fold in the build: it decodes the current
on-disc atlas (which already carries MAGIC/SKL), draws ONLY the ring-label cells, and
re-encodes the whole 0x44000..0x4afe0 window (so MAGIC/SKL are preserved verbatim).

SCOPE (lane pO4b) — the command-ring option labels, all 56x16 cells contiguous in the
chrome atlas (disc 0xEBE910 -> VDP1 VRAM 0x44000), located by parsing the VDP1 command
list at each ring rotation (cmd @0x07a0, screen pos (180,90)):

  0x441c0  ＼コンボ      -> Combo      (terms.json canon)
  0x44380  ＼クリティカル -> Critical   (terms.json canon)
  0x44540  ＼ぼうぎょ     -> Defend     (防御, terms.json canon)
  0x44700  ＼みる         -> Look       (見る; DM ring cmd; review-flagged)
  0x448c0  ＼とうそう     -> Flee       (逃走; DM ring cmd; review-flagged)
  0x44a80  ＼さくせん     -> Strategy   (作戦; DM ring cmd; review-flagged)
  0x44c40  ＼どうぐ       -> Item       (道具, terms.json canon)

Each JP cell is "＼<label>" (a leading connector tick + katakana/kanji). We clear the
whole cell and centre uppercase English (house style: matches the shipped MAGIC/SKL caps
and the CMDMN.BIN command verbs). The connector tick is cosmetic and dropped for the
long labels' width; centred English still reads as the ring's label at the fixed offset.

Not in this lane (separate layers / other owners): defend bar 防御実行/防御/回避,
strategy option kanji 個人作戦/全体作戦/マニュアル, item-panel title 道具, party
name-plates (0x45220 etc.), the Combo/Critical centre POPUPS, しゅうとくスキル header.
See docs/lanes/pO4b_chrome-labels.md.
"""
import argparse, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_chrome_codec as codec
import pO4_chrome_encode as enc
import battle_skillgain_gfx as tf   # Title-Case proportional font (_fit) — matches G1 canon casing

CHROME_RAW_OFF = 0xEBE910
DST_BASE = 0x44000
WIN_LO, WIN_HI = 0x44000, 0x4afe0
RAW_SECTOR, SYNC_HEADER, USER_DATA = 2352, 16, 2048
STREAM_BUDGET = 0x4000   # 16384 B on-disc footprint (same as pO4_chrome_fold)


# ---------------------------------------------------------------------------
# de-sectored write (identical to pO4_chrome_fold.write_logical / inverse of read_logical)
# ---------------------------------------------------------------------------
def write_logical(disc, raw_off, data):
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
# complete 5x7 uppercase pixel font (superset of pO4_chrome_fold's FONT; adds B,H,J,Q,W,Y,Z)
# ---------------------------------------------------------------------------
FONT = {
 'A': ["01110","10001","10001","11111","10001","10001","10001"],
 'B': ["11110","10001","10001","11110","10001","10001","11110"],
 'C': ["01110","10001","10000","10000","10000","10001","01110"],
 'D': ["11110","10001","10001","10001","10001","10001","11110"],
 'E': ["11111","10000","10000","11110","10000","10000","11111"],
 'F': ["11111","10000","10000","11110","10000","10000","10000"],
 'G': ["01110","10001","10000","10111","10001","10001","01110"],
 'H': ["10001","10001","10001","11111","10001","10001","10001"],
 'I': ["111","010","010","010","010","010","111"],
 'J': ["00111","00010","00010","00010","00010","10010","01100"],
 'K': ["10001","10010","10100","11000","10100","10010","10001"],
 'L': ["10000","10000","10000","10000","10000","10000","11111"],
 'M': ["10001","11011","10101","10101","10001","10001","10001"],
 'N': ["10001","11001","10101","10011","10001","10001","10001"],
 'O': ["01110","10001","10001","10001","10001","10001","01110"],
 'P': ["11110","10001","10001","11110","10000","10000","10000"],
 'Q': ["01110","10001","10001","10001","10101","10010","01101"],
 'R': ["11110","10001","10001","11110","10100","10010","10001"],
 'S': ["01111","10000","10000","01110","00001","00001","11110"],
 'T': ["11111","00100","00100","00100","00100","00100","00100"],
 'U': ["10001","10001","10001","10001","10001","10001","01110"],
 'V': ["10001","10001","10001","10001","10001","01010","00100"],
 'W': ["10001","10001","10001","10101","10101","11011","10001"],
 'X': ["10001","10001","01010","00100","01010","10001","10001"],
 'Y': ["10001","10001","01010","00100","00100","00100","00100"],
 'Z': ["11111","00001","00010","00100","01000","10000","11111"],
 ' ': ["0","0","0","0","0","0","0"],
}
GH = 7


def _put(atlas, srca, stride, x, y, nib):
    off = srca + y * stride + x // 2
    b = atlas[off]
    if x % 2 == 0:
        atlas[off] = (nib << 4) | (b & 0x0F)
    else:
        atlas[off] = (b & 0xF0) | (nib & 0xF)


def draw_text(atlas, srca, cell_w, cell_h, text, fg=15, gap=1):
    """Clear the cell and draw `text` centred via the tf proportional 5x7 font
    (squeeze-to-fit). 4bpp, stride=cell_w/2. Casing follows G1 PER SURFACE (rc_47 user
    decision 1): the G1 command ring + MAGIC-LV plates are ALL-CAPS (pREF-battle-cmdring-*)."""
    stride = cell_w // 2
    arr = tf._fit(text, cell_w, cell_h)
    for y in range(cell_h):
        for x in range(cell_w):
            _put(atlas, srca, stride, x, y, fg if arr[y][x] else 0)


# ring-label cells: (srca, w, h, english)
# Wording = canonical Grandia command-ring labels (official localisation per LP Archive
# Grandia #7 + Grandia wiki Action Menu; FLEE->Escape, STRATEGY->Tactics as before).
# Casing = ALL-CAPS: lane X2, rc_47 user decision 1 "battle chrome = ALL-CAPS matching G1
# per surface" — the G1 Saturn fan patch renders the whole command ring in 8x8 CAPS
# (docs/lanes/pREF/pREF-battle-cmdring-labels-montage.png: COMBO/CRITICAL/DEFEND/LOOK/
# ESCAPE/TACTICS/ITEMS/MOVES/MAGIC). We keep DM's singular wording (ITEM; the merged
# crystal-ball slot stays MAGIC) — see docs/lanes/laneX2-allcaps.md.
# NOTE cells 0x441c0/0x44380/0x44540 double as the centre COMBO/CRITICAL/DEFEND popups
# (pO1d) — G1's popup style is caps too ("2 HITS!"), so the share stays consistent.
LABELS = [
    (0x441c0, 56, 16, "COMBO"),      # ＼コンボ
    (0x44380, 56, 16, "CRITICAL"),   # ＼クリティカル
    (0x44540, 56, 16, "DEFEND"),     # ＼ぼうぎょ (防御)
    (0x44700, 56, 16, "LOOK"),       # ＼みる (見る)
    (0x448c0, 56, 16, "ESCAPE"),     # ＼とうそう (逃走) -- G1 canon "Escape" (was "FLEE")
    (0x44a80, 56, 16, "TACTICS"),    # ＼さくせん (作戦) -- G1 canon "Tactics" (was "STRATEGY")
    (0x44c40, 56, 16, "ITEM"),       # ＼どうぐ (道具)
    (0x44e00, 56, 16, "MAGIC"),      # わざ・まほう (skill+magic ring slot, crystal-ball icon).
                                     # DM merges 技(Moves)+魔法(Magic) into one slot -> "MAGIC".
    # MAGIC-LV submenu HUD header plate: G1's L/R plates read "MAGIC Lv3" (CAPS word,
    # pREF-battle-moves-menu.png) -> "MAGIC" (the LV art beside it is untouched).
    (0x477c0, 32, 16, "MAGIC"),      # 魔法 (MAGIC LV1-3 header) -> "MAGIC"
]


def author_atlas(disc):
    """Decode the on-disc atlas (already carries MAGIC/SKL from pO4_chrome_fold), draw the
    ring labels, return the modified full-VRAM image."""
    vram = bytearray(codec.run_decode(disc, CHROME_RAW_OFF, DST_BASE, 0x5000))
    for srca, w, h, text in LABELS:
        draw_text(vram, srca, w, h, text, fg=15)
    return vram


def build_stream(disc):
    vram = author_atlas(disc)
    codelen9, _ = enc._codelen9_from_disc_bytes(disc, CHROME_RAW_OFF)
    stream = enc.encode_fit(bytes(vram[WIN_LO:WIN_HI]), codelen9, budget=STREAM_BUDGET)
    return stream, vram


def cmd_fold(track):
    disc = bytearray(open(track, "rb").read())
    # idempotency gate: decode current atlas; if the ring cells already == English target, skip.
    cur = bytearray(codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000))
    target = bytearray(cur)
    for srca, w, h, text in LABELS:
        draw_text(target, srca, w, h, text, fg=15)
    if bytes(cur[WIN_LO:WIN_HI]) == bytes(target[WIN_LO:WIN_HI]):
        print("chrome ring labels already English -> skip"); return
    stream, vram = build_stream(disc)
    if len(stream) > STREAM_BUDGET:
        raise SystemExit(f"encoded stream {len(stream)} B > budget {STREAM_BUDGET} B; "
                         f"lower zthresh / fewer glyphs")
    stream = stream + b"\x00" * (STREAM_BUDGET - len(stream))
    write_logical(disc, CHROME_RAW_OFF, stream)
    open(track, "wb").write(disc)
    chk = codec.run_decode(bytes(disc), CHROME_RAW_OFF, DST_BASE, 0x5000)
    ok = bytes(chk[WIN_LO:WIN_HI]) == bytes(vram[WIN_LO:WIN_HI])
    print(f"folded chrome ring labels -> {track}  round-trip={'OK' if ok else 'MISMATCH'} "
          f"(stream {len(stream)} B incl pad)")


def cmd_preview(a):
    disc = bytearray(open(a.src, "rb").read())
    stream, vram = build_stream(disc)
    # ROM-decode oracle round-trip on the re-encoded stream (zero hardware)
    dec = enc._rom_decode_raw(stream, DST_BASE)
    n = sum(1 for i in range(WIN_LO, WIN_HI) if dec[i] != vram[i])
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "wb").write(bytes(vram))
    tot = WIN_HI - WIN_LO
    print(f"authored+encoded ring labels: stream {len(stream)} B (budget {STREAM_BUDGET}); "
          f"round-trip {tot-n}/{tot} ({'BIT-EXACT' if n == 0 else str(n)+' MISMATCH'}); "
          f"atlas -> {a.out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fold"); pf.add_argument("track")
    pp = sub.add_parser("preview")
    pp.add_argument("--src", default="output/rc_35/Track1.bin")
    pp.add_argument("--out", default="work/pO4b_labels/english_ring_atlas.bin")
    a = ap.parse_args()
    if a.cmd == "fold":
        cmd_fold(a.track)
    else:
        cmd_preview(a)
