#!/usr/bin/env python3
"""pW4_monst_stats_author.py — regenerate patches/viewer/pW4_stats_labels.bin (Lane W4 / O5).

Authors the English monster-book stat-panel labels into the DICDT.DAT page tile store and
emits the compact edit list consumed by tools/pW4_monst_stats_fold.py. Deterministic: given
the same vanilla track + screenmap + wording, the output is byte-identical.

Inputs
  --track   a track whose /FIELD/DICDT.DAT window @0xCFA0 is VANILLA-JP (e.g. a fresh rc build
            before the 7d fold, or the original JP Track1). md5-checked.
  patches/viewer/pW4_screenmap.npz — the empirically decoded screen(y,x) -> blob-offset map
            (16 bit-plane LWRAM-inject harness runs; 0.00% reconstruction mismatch; see
            docs/lanes/laneW4-stats-panel.md for the regeneration recipe).

Method
  * JP label pixels use blob bytes 187 (dark ink) and 186 (light emboss) EXCLUSIVELY
    (0 occurrences outside the 8 label bands) -> erase = replace every 186/187 byte with its
    8x8 cell's background mode byte.
  * Stamp Title-Case English with the house proportional 5x7 font
    (tools/battle_skillgain_gfx._G): ink 187 + JP-style emboss 186 at (+1,0)/(0,+1)/(+1,+1).
  * Wording (dictionary-guided, docs/menus/monster-stats-labels-en.json; deviations logged in
    dictionary/exceptions.json): Status / Level / Endurance / Attack / Defense / Agility /
    Move / Exp.
"""
import argparse, hashlib, os, struct, sys, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import iso  # noqa: E402
from battle_skillgain_gfx import _render  # noqa: E402  (proportional 5x7 title-case font)

WIN_OFF, WIN_LEN = 0xCFA0, 0xF4C0
MD5_VANILLA = "89f957de6f7bd2bbe93f1ab4b717e9bb"
INK, HI = 187, 186
SCREENMAP = os.path.join(HERE, "..", "patches", "viewer", "pW4_screenmap.npz")
OUT = os.path.join(HERE, "..", "patches", "viewer", "pW4_stats_labels.bin")

# (text, y_top, x_left or ('center', cx)) — screen coords, measured off the JP ink bands
LABELS = [
    ("Status",     88, ('center', 91)),
    ("Level",      96, 40),
    ("Endurance", 104, 40),
    ("Attack",    112, 40),
    ("Defense",   120, 40),
    ("Agility",   128, 40),
    ("Move",      136, 40),
    ("Exp",       144, 40),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, help="track with a VANILLA-JP DICDT.DAT window")
    a = ap.parse_args()

    with open(a.track, "rb") as f:
        rec = iso.find_record(f, "DICDT.DAT")
        data = iso.read_bytes(f, rec["lba"], rec["size"])
    orig = data[WIN_OFF:WIN_OFF + WIN_LEN]
    if hashlib.md5(orig).hexdigest() != MD5_VANILLA:
        raise SystemExit("DICDT.DAT window is not vanilla-JP — refuse to author from it")

    m = np.load(SCREENMAP)
    addr, valid = m["addr"], m["valid"]
    blob = bytearray(orig)

    # 1. erase JP labels (bytes 186/187 -> per-cell background mode)
    cellbg = {}
    for o, v in enumerate(orig):
        if v in (INK, HI):
            c = o // 64
            if c not in cellbg:
                cnt = collections.Counter(b for b in orig[c*64:(c+1)*64] if b not in (INK, HI))
                cellbg[c] = cnt.most_common(1)[0][0] if cnt else orig[c*64 - 64]
            blob[o] = cellbg[c]

    # 2. stamp English (emboss first, ink on top)
    for text, y0, xs in LABELS:
        g = _render(text, tracking=1)
        h, w = g.shape
        x0 = xs if isinstance(xs, int) else xs[1] - w // 2
        for dy, dx, val in ((1, 0, HI), (0, 1, HI), (1, 1, HI), (0, 0, INK)):
            for gy in range(h):
                for gx in range(w):
                    if not g[gy, gx]:
                        continue
                    y, x = y0 + gy + dy, x0 + gx + dx
                    if not valid[y, x]:
                        raise SystemExit(f"'{text}' pixel ({y},{x}) off the decoded map")
                    blob[addr[y, x]] = val

    edits = [(o, blob[o]) for o in range(WIN_LEN) if blob[o] != orig[o]]
    b = bytearray(b"PW4L") + struct.pack(">I", len(edits))
    for o, v in edits:
        b += struct.pack(">HB", o, v)
    open(OUT, "wb").write(bytes(b))
    print(f"wrote {OUT}: {len(edits)} edits; english window md5 "
          f"{hashlib.md5(bytes(blob)).hexdigest()}")


if __name__ == "__main__":
    main()
