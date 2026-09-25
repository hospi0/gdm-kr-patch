#!/usr/bin/env python3
"""mg_explore.py — decode every chunk-bearing slot of a KNPAN-style .DAT and render
each to PNG so we can visually identify the title-logo slot.

For each odd "gfx" slot we decode via mg_tree.decode_blob (offline static tree),
concatenate the chunk pixels into one linear 8bpp buffer, and render it as a bitmap
using the immediately-preceding 512B palette slot. Width is guessed from the decoded
size (352 for big bg/title sprites, else 128).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import mg_stb
import mg_tree
import mg_gfx


def is_gfx_slot(data, start, end):
    """Heuristic: a chunk-stream slot begins with a plausible BE16 chunk count
    (1..16) followed by a tree-def. Palette slots are 512B BGR555 (no such count)."""
    size = end - start
    if size == 512:
        return False
    cnt = struct.unpack_from(">H", data, start)[0]
    return 1 <= cnt <= 16


def main():
    path = sys.argv[1]
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    data = open(path, "rb").read()
    spans = mg_stb.blob_spans(data)
    # map slot->span
    span_by_slot = {s: (st, en) for s, st, en in spans}
    name = os.path.splitext(os.path.basename(path))[0]
    for slot, start, end in spans:
        if not is_gfx_slot(data, start, end):
            continue
        try:
            chunks = mg_tree.decode_blob(data, start)
        except Exception as e:
            print(f"slot {slot}: decode FAIL {e}")
            continue
        pix = b"".join(c["pixels"] for c in chunks)
        total = len(pix)
        # palette = preceding 512B slot if present
        pal_slot = slot - 1
        pal_off = span_by_slot.get(pal_slot, (None, None))[0]
        cnt = struct.unpack_from(">H", data, start)[0]
        modes = [c["mode"] for c in chunks]
        print(f"slot {slot}: chunks={cnt} decoded={total}B modes={modes} pal_slot={pal_slot}@{pal_off}")
        # guess width
        for W in (352, 128, 256, 64):
            if total % W == 0:
                H = total // W
                if 8 <= H <= 256:
                    width = W
                    break
        else:
            width = 352
            H = (total + width - 1) // width
        pixfile = os.path.join(outdir, f"{name}_s{slot:02d}.pix")
        open(pixfile, "wb").write(pix)
        out_png = os.path.join(outdir, f"{name}_s{slot:02d}_{width}x{H}.png")
        argv = [pixfile, out_png, "--bpp", "8", "--bitmap", str(width), str(H), "--zoom", "2"]
        if pal_off is not None:
            # write palette to a temp file
            palfile = os.path.join(outdir, f"{name}_s{pal_slot:02d}.pal")
            open(palfile, "wb").write(data[pal_off:pal_off + 512])
            argv += ["--pal", palfile, "--pal-be"]
        mg_gfx.main(argv)


if __name__ == "__main__":
    main()
