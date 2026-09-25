#!/usr/bin/env python3
"""mg_knpan.py — KNPAN.DAT container parser/splicer for the deck-swab title screen.

The deck-swab (甲板掃除REMIX) title+menu screen is decompressed by the engine
caller at HWRAM 0x06013F90 as ONE interleaved stream of 6 chunks. Each chunk is
preceded inline by a per-chunk Huffman tree-def (rebuilt by 0x0601401A into the
forest at 0x06028800) + a root descriptor, then the bitstream consumed by the
decompressor 0x06015DF0 (see tools/mg_codec.py + docs/mgame-format.md).

The framing below was captured empirically with the YMIR harness (breakpoint the
decompressor from save 5, log the src/dst cursors at 0x06014D9C/0x06014DA0 and the
per-chunk built tree at 0x06028800). All 6 chunks decode 100% byte-exact vs the
save-4 VDP1 VRAM ground truth. The trees are committed under work/mgame/tree_h*.bin
(deterministic from the verbatim descriptors, so re-encoding keeps them valid).

Layout (file offsets into KNPAN.DAT, src = bitstream start, end = word-aligned EOS):
  chunk0 src=0x263  end=0x1CB0 dst=0x14000 root=0xFB0 mode=1 16384B  bg+logo (1/5)
  chunk1 src=0x1CE5 end=0x352C dst=0x18000 root=0xF98 mode=1 16384B  bg+logo (2/5)
  chunk2 src=0x354D end=0x3D50 dst=0x1C000 root=0x808 mode=0 16384B  bg+logo (3/5)
  chunk3 src=0x3D71 end=0x4574 dst=0x20000 root=0x808 mode=0 16384B  bg+logo (4/5)
  chunk4 src=0x4595 end=0x4C18 dst=0x24000 root=0x808 mode=0 13312B  bg+logo (5/5)
  chunk5 src=0x4E4E end=0x5580 dst=0x27400 root=0x890 mode=1 12288B  3 menu sprites
bg+logo = one 352x224 8bpp VDP1 sprite (dst 0x14000..0x27400).
menu     = 3x (128x32 8bpp) sprites at dst 0x27400/0x28400/0x29400.

Re-encode is size-preserving: descriptors are kept byte-verbatim (engine rebuilds
identical trees), only bitstreams are swapped, and the group-B region end (0x5584,
where the next resource begins) is held fixed by padding the final chunk.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mg_codec

TREE_DIR = os.path.join(ROOT, "work/mgame")

# src, end, dst, root, mode, tree-hit (work/mgame/tree_hN.bin)
CHUNKS = [
    (0x263,  0x1CB0, 0x14000, 0xFB0, 1, 8,  16384),
    (0x1CE5, 0x352C, 0x18000, 0xF98, 1, 9,  16384),
    (0x354D, 0x3D50, 0x1C000, 0x808, 0, 10, 16384),
    (0x3D71, 0x4574, 0x20000, 0x808, 0, 11, 16384),
    (0x4595, 0x4C18, 0x24000, 0x808, 0, 12, 13312),
    (0x4E4E, 0x5580, 0x27400, 0x890, 1, 13, 12288),
]
GROUP_B_END = 0x5584  # next resource (slot-4 palette) — must stay put
BG_DST = 0x14000
MENU_DST = 0x27400
MENU_ITEM = 4096  # 128x32 8bpp

# The title screen is decompressed by THREE separate engine calls (chunk-loop caller
# 0x06013F90), one per offset-table slot — confirmed by breakpointing the caller and
# reading R4 (blob source): slot1@0x22C -> bg/logo (chunks 0-4, dst 0x14000), and
# slot3@0x4E18 -> the shared menu (chunk 5, dst 0x27400). (A third, slot5@0x5784, is a
# different minigame's playfield.) The two blobs are INDEPENDENT and each is confined
# to its slot; chunk 5 is NOT threaded after chunk 4. Each blob: a header (tree-defs +
# BE16 chunk count + first chunk's root), then chunks threaded by the engine cursor.
#   (chunk_ids, blob_src, slot_end)
BLOBS = [
    ([0, 1, 2, 3, 4], 0x22C, 0x4C18),  # slot 1: bg + logo
    ([5],            0x4E18, 0x5584),  # slot 3: shared START/RANK/QUIT menu
]
# Fixed verbatim descriptor byte-length preceding each chunk (the blob header for the
# first chunk of a blob, else the inter-chunk inline tree-def). From the pristine file.
PRE_LEN = {0: 55, 1: 52, 2: 35, 3: 35, 4: 35, 5: 54}


def _tree(hit):
    with open(os.path.join(TREE_DIR, f"tree_h{hit}.bin"), "rb") as f:
        return f.read()


def decode_screen(knpan):
    """Return the full decoded VDP1 pixel buffer (0..0x2A400) for the title screen."""
    full = bytearray(0x2A400)
    for src, end, dst, root, mode, hit, sz in CHUNKS:
        out = mg_codec.decode(knpan[src & ~3:], _tree(hit), root, mode=mode,
                              src_align_phase=src & 3, max_out=sz)
        assert len(out) == sz, f"chunk dst {dst:#x}: {len(out)} != {sz}"
        full[dst:dst + sz] = out
    return bytes(full)


def _blob_descs(knpan, chunk_ids):
    """For a blob's chunk list, return {chunk_id: verbatim inline descriptor} where the
    descriptor precedes that chunk (the engine reads it just before decompressing). The
    descriptor overlaps the PRIOR chunk's EOS word; for the first chunk it is the blob
    header (tree-defs + count + root)."""
    out = {}
    for k, ci in enumerate(chunk_ids):
        src = CHUNKS[ci][0]
        if k == 0:
            continue  # header handled separately
        psrc, _, _, proot, pmode, phit, psz = CHUNKS[chunk_ids[k - 1]]
        _, cur = mg_codec.decode_end(knpan[psrc & ~3:], _tree(phit), proot, mode=pmode,
                                     src_align_phase=psrc & 3)
        out[ci] = knpan[(psrc & ~3) + cur:src]
    return out


def _rebuild_blob(knpan, full, edits, chunk_ids, blob_src, slot_end):
    """Rebuild one self-contained blob's slot region [blob_src, slot_end) with the
    engine-cursor threading + descriptor overlap-merge, zero-padded to slot_end."""
    descs = _blob_descs(knpan, chunk_ids)
    first_src = CHUNKS[chunk_ids[0]][0]
    out = bytearray(knpan[blob_src:first_src])  # blob header, abs [blob_src:first_src]
    for k, ci in enumerate(chunk_ids):
        src, end, dst, root, mode, hit, sz = CHUNKS[ci]
        abs_v = blob_src + len(out)
        phase = abs_v & 3                       # engine recomputes cursor&3 at entry
        out_base = (abs_v & ~3) - blob_src
        tree = _tree(hit)
        enc = mg_codec.encode(edits.get(ci, full[dst:dst + sz]), tree, root,
                              mode=mode, src_align_phase=phase)
        _, cur = mg_codec.decode_end(enc, tree, root, mode=mode, src_align_phase=phase)
        enc = enc[:(cur + 3) & ~3]              # whole words through the EOS byte
        while len(out) < out_base + len(enc):
            out.append(0)
        for j, b in enumerate(enc):
            out[out_base + j] |= b              # OR preserves descriptor overlap bytes
        if k + 1 < len(chunk_ids):
            desc = descs[chunk_ids[k + 1]]
            start = out_base + cur              # next descriptor starts at the engine cursor
            while len(out) < start + len(desc):
                out.append(0)
            for j, b in enumerate(desc):
                out[start + j] |= b
    region = slot_end - blob_src
    if len(out) > region:
        raise ValueError(f"blob @{blob_src:#x} overflow: {len(out)} > {region} "
                         f"({len(out) - region} bytes too big for the slot)")
    out += b"\x00" * (region - len(out))
    return out


def decode_threaded(knpan):
    """Decode the title screen the way the engine does: each blob from its own slot
    source, chunks threaded by the byte-precise cursor (mg_codec.decode_end), with the
    fixed verbatim descriptor byte-lengths (PRE_LEN). Works on PATCHED files whose chunk
    offsets have shifted within a slot. Authoritative deterministic validator."""
    full = bytearray(0x2A400)
    for chunk_ids, blob_src, slot_end in BLOBS:
        cur = blob_src + PRE_LEN[chunk_ids[0]]  # first chunk's bitstream start
        for k, ci in enumerate(chunk_ids):
            src, end, dst, root, mode, hit, sz = CHUNKS[ci]
            out, cend = mg_codec.decode_end(knpan[cur & ~3:], _tree(hit), root,
                                            mode=mode, src_align_phase=cur & 3)
            full[dst:dst + sz] = out[:sz]
            if k + 1 < len(chunk_ids):
                cur = ((cur & ~3) + cend) + PRE_LEN[chunk_ids[k + 1]]
    return bytes(full)


def patch(knpan, edits):
    """Return a new KNPAN.DAT with chunk pixel edits applied. Each title-screen blob
    (bg/logo = slot 1, menu = slot 3) is rebuilt INDEPENDENTLY and confined to its
    offset-table slot, so edits never move the other blob (or the inter-slot palettes).
    Within a blob, chunks are threaded with the engine's byte-precise cursor and the
    inline tree-def descriptors are kept verbatim (OR-merged onto each EOS-word). Raises
    if a blob's re-encode overflows its slot."""
    full = decode_screen(knpan)
    buf = bytearray(knpan)
    for chunk_ids, blob_src, slot_end in BLOBS:
        if not any(ci in edits for ci in chunk_ids):
            continue
        buf[blob_src:slot_end] = _rebuild_blob(knpan, full, edits, chunk_ids,
                                               blob_src, slot_end)
    return bytes(buf)


def cmd_decode(knpan_path, out_path):
    knpan = open(knpan_path, "rb").read()
    open(out_path, "wb").write(decode_screen(knpan))
    print(f"decoded title screen -> {out_path} (0x2A400 bytes)")


def cmd_verify(knpan_path):
    """Round-trip: re-encode every chunk with its ORIGINAL pixels and confirm the
    rebuilt file DECODES to the identical title screen, keeps the same total size,
    and leaves the next resource (>=0x5584) byte-identical. (The unused trailing
    bits of each chunk's EOS word may differ; the engine stops at the EOS leaf, so
    that is functionally irrelevant — what must match is the decoded pixels.)"""
    knpan = open(knpan_path, "rb").read()
    full = decode_screen(knpan)
    # Full re-encode of EVERY chunk with its ORIGINAL pixels through the threading
    # reassembler. With correct engine-cursor descriptor placement this must
    # byte-reproduce the whole group-B region (..0x5584); the suffix is copied.
    edits = {i: full[c[2]:c[2] + c[6]] for i, c in enumerate(CHUNKS)}
    rebuilt = patch(knpan, edits)
    same_size = len(rebuilt) == len(knpan)
    byte_identical = rebuilt == knpan
    same_screen = decode_screen(rebuilt) == full
    ok = same_size and same_screen
    if byte_identical:
        print("round-trip: BYTE-IDENTICAL (group-B region reproduced exactly) -> PASS")
    else:
        fd = next((i for i in range(min(len(rebuilt), len(knpan)))
                   if rebuilt[i] != knpan[i]), None)
        print(f"round-trip: decode-identical={same_screen} size-preserved={same_size} "
              f"first byte diff at {fd:#x} (EOS-word unused bits ok) -> "
              f"{'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "decode":
        cmd_decode(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "verify":
        sys.exit(0 if cmd_verify(sys.argv[2]) else 1)
    else:
        print(__doc__)
        print("usage: mg_knpan.py decode KNPAN.DAT screen.bin | verify KNPAN.DAT")
