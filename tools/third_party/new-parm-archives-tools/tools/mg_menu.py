#!/usr/bin/env python3
"""mg_menu.py — author an English minigame menu sprite-stack and splice it into a
KNPAN-style container slot, size-preserving + offline-validated.

A menu blob decodes to N stacked 128x32 8bpp sprites (one per item). We render each
English label centered into its own 128x32 cell (reusing the menu's own stroke index
via mg_text), concatenate, then mg_splice.patch_slot re-encodes the blob in place
(byte-exact descriptors, confined to the slot). English block letters compress worse
than kana, so we author at val/scale tuned to stay within the slot's Huffman budget.

  mg_menu.py author DAT BLOB_SRC SLOT_END OUT.dat ITEM[,ITEM...] [--val N --scale N]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mg_text, mg_splice

CELL_W, CELL_H = 128, 32

def author_menu(items, val=16, hi=16, scale=2):
    buf = bytearray()
    for label in items:
        w = len(label) * 6 * scale
        x0 = max(0, (CELL_W - w) // 2)
        y0 = max(0, (CELL_H - 7 * scale) // 2)
        buf += mg_text.render(label, CELL_W, CELL_H, val, hi, scale, x0, y0)
    return bytes(buf)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["author"])
    ap.add_argument("dat"); ap.add_argument("blob_src"); ap.add_argument("slot_end")
    ap.add_argument("out"); ap.add_argument("items")
    ap.add_argument("--val", type=int, default=16)
    ap.add_argument("--scale", type=int, default=2)
    a = ap.parse_args()
    blob_src = int(a.blob_src, 0); slot_end = int(a.slot_end, 0)
    items = a.items.split(",")
    dat = open(a.dat, "rb").read()
    n = len(mg_splice.decode_slot(dat, blob_src))   # chunk count (sanity)
    pix = author_menu(items, val=a.val, scale=a.scale)
    nitems = len(pix) // (CELL_W * CELL_H)
    # map item-stack pixels onto the chunk(s): the blob may be 1 chunk (all items)
    # or multiple. Concatenated decoded pixels == our authored buffer length must match.
    orig = mg_splice.slot_pixels(dat, blob_src)
    if len(pix) != len(orig):
        raise SystemExit(f"size mismatch: authored {len(pix)} vs slot {len(orig)} "
                         f"({len(orig)//4096} items expected)")
    # split authored pixels back across chunks by their decoded sizes
    chunks = mg_splice.decode_slot(dat, blob_src)
    edits = {}; off = 0
    for k, c in enumerate(chunks):
        edits[k] = pix[off:off + c["size"]]; off += c["size"]
    new = mg_splice.patch_slot(dat, blob_src, slot_end, edits)
    open(a.out, "wb").write(new)
    # validate: re-decode == authored
    got = mg_splice.slot_pixels(new, blob_src)
    ok = got == pix
    print(f"authored {nitems} items -> {a.out}  decode-roundtrip={'EXACT' if ok else 'FAIL'}  "
          f"(slot budget {slot_end-blob_src}B)")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
