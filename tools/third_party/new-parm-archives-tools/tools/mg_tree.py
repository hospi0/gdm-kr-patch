#!/usr/bin/env python3
"""mg_tree.py — STATIC Huffman-forest builder for the minigame ST1 codec.

The minigame title screens are decompressed chunk-by-chunk; each chunk is preceded
by an inline tree-def that the resident engine turns into a node table (consumed by
tools/mg_codec.py). For the deck-swab screen those node tables were captured *live*
from HWRAM (work/mgame/tree_h8..h13.bin), which required reaching the screen in the
emulator. The other minigames are coin-gated, so live capture is impractical.

This module removes that dependency: it builds the node table OFFLINE by executing
the *real* engine routines on the inline tree-def, via the minimal SH-2 interpreter
in tools/sh2emu.py and an HWRAM image with the resident code. The two engine
routines are:
  * 0x0601401A — read the inline tree-def -> per-symbol code-length table at
                 tree[sym*8]; returns the chunk's delta-filter mode in r0.
  * 0x060144EE — build the internal Huffman nodes from those lengths; returns the
                 root node offset in r0.
The chunk-loop caller (0x06013F90) threads one source cursor [0x06014D9C] through
the whole blob: BE16 chunk count, then per chunk {0x0601401A, 0x060144EE, decode}.

Validated byte-exact: decoding KNPAN.DAT's 6 chunks with statically-built trees
reproduces the live-captured ground truth 100% (see __main__ self-test).

The HWRAM image (resident engine code) defaults to work/mgame/hwram.bin.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import sh2emu
import mg_codec

HWRAM_PATH = os.path.join(ROOT, "work/mgame/hwram.bin")

# Engine entry points (resident @ HWRAM, captured save-5 build).
FN_LENGTHS = 0x0601401A   # tree-def -> code-length table; returns filter mode
FN_NODES = 0x060144EE     # code-lengths -> internal nodes; returns root offset
VAR_CURSOR = 0x06014D9C   # the shared source cursor variable

# Disjoint scratch bases (outside the 0x06000000..0x06100000 HWRAM window so they
# don't collide with the resident image). Node values are stored as 16-bit offsets,
# so the tree base is irrelevant to the produced table.
_TREE = 0x10000000
_BLOB = 0x11000000
_STK = 0x12000000

_hwram_cache = None


def _hwram(path=None):
    global _hwram_cache
    if _hwram_cache is None or path:
        with open(path or HWRAM_PATH, "rb") as f:
            _hwram_cache = f.read()
    return _hwram_cache


def build_chunk(blob, treedef_off, hwram=None):
    """Run the engine on the inline tree-def at `treedef_off` in `blob`.

    Returns (tree_bytes, mode, root, cursor_after) where cursor_after is the byte
    offset in `blob` just past the consumed tree-def (= the chunk's bitstream start).
    """
    hw = hwram if hwram is not None else _hwram()
    m = sh2emu.Mem()
    m.map(0x06000000, hw)
    m.map(_TREE, bytes(0x4000))
    m.map(_BLOB, blob)
    m.map(_STK, bytes(0x40000))
    cpu = sh2emu.SH2(m)
    m.w32(VAR_CURSOR, _BLOB + treedef_off)
    cpu.R[4] = _TREE
    cpu.R[15] = _STK + 0x30000
    cpu.run(FN_LENGTHS)
    mode = cpu.R[0] & 0xFF
    cpu.R[4] = _TREE
    cpu.R[15] = _STK + 0x30000
    cpu.run(FN_NODES)
    root = cpu.R[0] & 0xFFFF
    cursor_after = m.r32(VAR_CURSOR) - _BLOB
    return bytes(m.region(_TREE)), mode, root, cursor_after


def decode_blob(blob, blob_src, hwram=None, max_chunks=64):
    """Decode a whole title-screen blob the way the engine does: read the BE16 chunk
    count, then thread the cursor through {build tree-def, build nodes, decode} for
    each chunk. Returns a list of dicts per chunk with keys: treedef_off, bitstream,
    mode, root, pixels, size.
    """
    hw = hwram if hwram is not None else _hwram()
    count = struct.unpack_from(">H", blob, blob_src)[0]
    cursor = blob_src + 2
    out = []
    for _ in range(min(count, max_chunks)):
        tree, mode, root, after = build_chunk(blob, cursor, hwram=hw)
        bs = after  # bitstream start
        pixels, end = mg_codec.decode_end(blob[bs & ~3:], tree, root, mode=mode,
                                          src_align_phase=bs & 3)
        out.append({"treedef_off": cursor, "bitstream": bs, "mode": mode,
                    "root": root, "pixels": pixels, "size": len(pixels), "tree": tree})
        cursor = (bs & ~3) + end
    return out


# --------------------------------------------------------------------------
def _selftest():
    """Validate against the live-captured KNPAN ground truth."""
    knpan = open(os.path.join(ROOT, "work/mgame/KNPAN.DAT"), "rb").read()
    # Ground truth: mg_knpan CHUNKS (live trees tree_h8..h13).
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import mg_knpan
    gt_full = mg_knpan.decode_screen(knpan)
    ok = True
    # slot 1 (bg/logo, chunks 0-4) @0x22C ; slot 3 (menu, chunk5) @0x4E18
    for blob_src, chunk_ids in [(0x22C, [0, 1, 2, 3, 4]), (0x4E18, [5])]:
        chunks = decode_blob(knpan, blob_src)
        for k, ci in enumerate(chunk_ids):
            src, end, dst, root, mode, hit, sz = mg_knpan.CHUNKS[ci]
            got = chunks[k]
            gtpix = gt_full[dst:dst + sz]
            match = got["pixels"][:sz] == gtpix
            ok = ok and match and got["mode"] == mode and got["root"] == root
            print(f"chunk{ci}: static mode={got['mode']} root={got['root']:#x} "
                  f"size={got['size']} vs gt(mode={mode},root={root:#x},sz={sz}) "
                  f"pixels={'EXACT' if match else 'DIFFER'}")
    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "selftest":
        sys.exit(0 if _selftest() else 1)
    elif len(sys.argv) >= 3 and sys.argv[1] == "blob":
        blob = open(sys.argv[2], "rb").read()
        src = int(sys.argv[3], 0)
        for i, c in enumerate(decode_blob(blob, src)):
            print(f"chunk{i}: treedef@{c['treedef_off']:#x} bitstream@{c['bitstream']:#x} "
                  f"mode={c['mode']} root={c['root']:#x} size={c['size']}")
    else:
        print(__doc__)
        print("usage: mg_tree.py selftest | blob FILE BLOB_SRC_OFF")
