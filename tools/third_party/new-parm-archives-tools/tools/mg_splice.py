#!/usr/bin/env python3
"""mg_splice.py — GENERIC KNPAN-style blob re-encoder/splicer (any minigame .DAT).

mg_knpan.py hardcodes the deck-swab KNPAN chunk table. This module does the same
threaded, size-preserving, descriptor-OR-merge re-encode for ANY KNPAN-style blob,
driving everything off tools/mg_tree.decode_blob (which statically rebuilds each
chunk's Huffman tree + mode + root offline). So we can translate the per-game menus
and logos and splice them back into RFROG.DAT / OBONG.DAT / MGSUE.BIN / ... in place.

A "blob" is one offset-table slot whose bytes begin with a BE16 chunk count followed
by inline per-chunk tree-defs (see docs/mgame-format.md). decode_blob(dat, blob_src)
returns, per chunk: treedef_off, bitstream (start), mode, root, tree, pixels.

patch_slot(dat, blob_src, slot_end, edits) re-encodes the blob with edits={chunk_idx:
new_pixels}, keeping every inline descriptor byte-verbatim (the engine rebuilds an
identical tree, so root/mode stay valid) and OR-merging each next descriptor onto the
prior chunk's overlapping EOS word — exactly mg_knpan._rebuild_blob, but generic.
Confined to [blob_src, slot_end) and zero-padded; raises if it overflows the slot.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import mg_codec
import mg_tree


def decode_slot(dat, blob_src):
    """Return the list of per-chunk dicts (from mg_tree.decode_blob) for a blob."""
    return mg_tree.decode_blob(dat, blob_src)


def slot_pixels(dat, blob_src):
    """Concatenated decoded pixels of a blob (all chunks)."""
    return b"".join(c["pixels"] for c in decode_slot(dat, blob_src))


def _rebuild_blob(dat, blob_src, slot_end, chunks, edits, snap=False, palette_rgb=None):
    """Threaded, size-preserving re-encode of one blob. `chunks` = decode_slot output.
    edits = {chunk_idx: new_pixels}. Returns the new slot bytes [blob_src, slot_end).
    If snap=True, each edited chunk's pixels are first nudged to be encodable with the
    chunk's fixed Huffman tree (mg_codec.snap_to_tree, palette-aware via palette_rgb)."""
    first_bs = chunks[0]["bitstream"]
    # header = count + first tree-def, verbatim, abs [blob_src, first_bs)
    out = bytearray(dat[blob_src:first_bs])
    for k, c in enumerate(chunks):
        tree, root, mode = c["tree"], c["root"], c["mode"]
        pixels = edits.get(k, c["pixels"])
        if snap and k in edits:
            pixels = mg_codec.snap_to_tree(pixels, tree, root, mode=mode,
                                           palette_rgb=palette_rgb)
        abs_v = blob_src + len(out)
        phase = abs_v & 3                       # engine recomputes cursor&3 at entry
        out_base = (abs_v & ~3) - blob_src
        enc = mg_codec.encode(pixels, tree, root, mode=mode, src_align_phase=phase)
        _, cur = mg_codec.decode_end(enc, tree, root, mode=mode, src_align_phase=phase)
        enc = enc[:(cur + 3) & ~3]              # whole words through the EOS byte
        while len(out) < out_base + len(enc):
            out.append(0)
        for j, b in enumerate(enc):
            out[out_base + j] |= b              # OR preserves descriptor overlap bytes
        if k + 1 < len(chunks):
            nxt = chunks[k + 1]
            desc = dat[nxt["treedef_off"]:nxt["bitstream"]]  # verbatim inline tree-def
            start = out_base + cur                            # engine cursor = EOS byte
            while len(out) < start + len(desc):
                out.append(0)
            for j, b in enumerate(desc):
                out[start + j] |= b
    region = slot_end - blob_src
    if len(out) > region:
        raise ValueError(f"blob @{blob_src:#x} overflow: {len(out)} > {region} "
                         f"({len(out) - region} bytes too big for the slot)")
    out += b"\x00" * (region - len(out))
    return bytes(out)


def patch_slot(dat, blob_src, slot_end, edits, snap=False, palette_rgb=None):
    """Return a new .DAT with the blob at [blob_src, slot_end) re-encoded with `edits`
    ({chunk_idx: new_pixels}). Size-preserving; other slots untouched. snap/palette_rgb
    forwarded to _rebuild_blob (delta-safe authoring against the fixed tree)."""
    chunks = decode_slot(dat, blob_src)
    new = _rebuild_blob(dat, blob_src, slot_end, chunks, edits, snap=snap,
                        palette_rgb=palette_rgb)
    buf = bytearray(dat)
    buf[blob_src:slot_end] = new
    return bytes(buf)


def roundtrip_ok(dat, blob_src, slot_end, verbose=True):
    """Re-encode the blob with its ORIGINAL pixels; confirm it decodes identically and
    stays inside the slot. Returns True/False."""
    chunks = decode_slot(dat, blob_src)
    orig_pix = [c["pixels"] for c in chunks]
    rebuilt = patch_slot(dat, blob_src, slot_end, {})  # {} = original pixels
    new_chunks = decode_slot(rebuilt, blob_src)
    new_pix = [c["pixels"] for c in new_chunks]
    same = orig_pix == new_pix
    byte_same = rebuilt[blob_src:slot_end] == dat[blob_src:slot_end]
    if verbose:
        print(f"  blob@{blob_src:#x}: {len(chunks)} chunks, "
              f"pixels={'EXACT' if same else 'DIFFER'} "
              f"slot-bytes={'IDENTICAL' if byte_same else 'changed(ok if pixels exact)'}")
    return same


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "roundtrip":
        dat = open(sys.argv[2], "rb").read()
        ok = roundtrip_ok(dat, int(sys.argv[3], 0), int(sys.argv[4], 0))
        sys.exit(0 if ok else 1)
    elif len(sys.argv) >= 5 and sys.argv[1] == "decode":
        dat = open(sys.argv[2], "rb").read()
        pix = slot_pixels(dat, int(sys.argv[3], 0))
        open(sys.argv[4], "wb").write(pix)
        print(f"decoded blob -> {sys.argv[4]} ({len(pix)} bytes)")
    else:
        print(__doc__)
        print("usage: mg_splice.py roundtrip DAT BLOB_SRC SLOT_END | "
              "decode DAT BLOB_SRC OUT.pix")
