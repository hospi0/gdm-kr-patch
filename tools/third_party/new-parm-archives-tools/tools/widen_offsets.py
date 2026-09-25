#!/usr/bin/env python3
"""Widen the 16-bit script-piece OFS offset to a WORD offset (x2 -> 128KB reach).

The SCNRL piece resolver (@0x0601E596) computes  piece_addr = script_base + (entry & 0xFFFF).
We patch it to  piece_addr = script_base + ((entry & 0xFFFF) << 1)  using the free rts delay slot:
  0x0601E59E (file 0x259E): add r3,r0 (303C) -> shll r0   (4000)
  0x0601E5A2 (file 0x25A2): nop      (0009) -> add r3,r0  (303C)
Then every OFS offset is stored halved (off//2). All vanilla offsets are EVEN (max 60518), so
halving is lossless; the resolver's <<1 restores the true byte offset. With 16-bit halves the true
reach is 2*65535 = 131070 B, enough for full-English 2000 (~84KB). The terminator off==0xFFFF is a
sentinel checked BEFORE scaling, so it is left as-is.

SCNRL.BIN on disc is XOR("OHATA")-encoded; decoded image loads at 0x0601C000.
"""
import struct

KEY = b"OHATA"
SCNRL_LOAD = 0x0601C000
# (file_offset, old_decoded_word, new_decoded_word)
PATCH = [(0x259E, 0x303C, 0x4000),   # add r3,r0  -> shll r0
         (0x25A2, 0x0009, 0x303C)]   # nop        -> add r3,r0

# TrekkiesUnite's Grandia-1 full-length-names patch, ported to DM by EN-vs-JP SCNRL diff (see
# docs/grandia1-scnrl-fontbox-patches.md). Applied only when GDM_8X16 is set.
# IMPORTANT (DM, found 2026-06-28): TU's two `nop` patches (0x1BB4/0x1BBE) and the box-width patch
# (0x20FA) are DM-INCOMPATIBLE — the nops sit in code DM's room scripts use, so they make the Library
# (and other c000/e001 area-banner rooms) render the banner in 16x16 (kana garbage) and WARP/desync the
# scene. Verified live: reverting the nops fixes the Library (8x16, no warp). 8x16 is already
# half-width so names fit WITHOUT the box-width patch (dialogue precedent). So we apply ONLY the
# default-font patch. (Residual: a c000/e001 banner box is over-sized for short 8x16 text -> a pink
# tail tile; cosmetic, refine via name padding.)
FONT_BOX_PATCH = [(0x22B0, 0xC901, 0xE001)]   # default font -> 8x16 (and #1 -> mov #1,r0)
# Contiguous decoded bytes 0x0601E59E..0x0601E5A3 after patch (middle word 0x000B rts unchanged):
PATCH_ADDR = 0x0601E59E
PATCH_DECODED = bytes([0x40, 0x00, 0x00, 0x0B, 0x30, 0x3C])  # shll r0 ; rts ; add r3,r0


def _decode(raw: bytes) -> bytearray:
    return bytearray(b ^ KEY[i % 5] for i, b in enumerate(raw))


def _encode(dec: bytes) -> bytes:
    return bytes(b ^ KEY[i % 5] for i, b in enumerate(dec))


def patch_scnrl(raw: bytes) -> bytes:
    """Return a patched, re-encoded SCNRL.BIN (resolver -> word-scaled offsets). With env GDM_8X16 set,
    also apply TrekkiesUnite's font/box patches so names render full-length 8x16 (global default-font
    flip; see docs/grandia1-scnrl-fontbox-patches.md)."""
    import os
    dec = _decode(raw)
    patches = list(PATCH)
    if os.environ.get("GDM_8X16"):
        patches += FONT_BOX_PATCH
    for off, old, new in patches:
        got = struct.unpack_from(">H", dec, off)[0]
        if got != old:
            raise ValueError(f"SCNRL @0x{off:04X}: expected 0x{old:04X}, found 0x{got:04X} "
                             f"(wrong SCNRL or already patched)")
        struct.pack_into(">H", dec, off, new)
    return _encode(dec)


def halve_ofs(ofs: bytes) -> bytes:
    """Halve every real offset in an OFS pointer table (id16, off16) pairs; keep 0xFFFF terminators."""
    out = bytearray(ofs)
    for i in range(0, len(out) - 3, 4):
        off = struct.unpack_from(">H", out, i + 2)[0]
        if off != 0xFFFF:
            if off & 1:
                raise ValueError(f"OFS entry {i//4}: odd offset 0x{off:04X} can't be halved losslessly")
            struct.pack_into(">H", out, i + 2, off >> 1)
    return bytes(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "patch-scnrl":
        raw = open(sys.argv[2], "rb").read()
        open(sys.argv[3], "wb").write(patch_scnrl(raw))
        print(f"patched SCNRL -> {sys.argv[3]}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "halve-ofs":
        open(sys.argv[3], "wb").write(halve_ofs(open(sys.argv[2], "rb").read()))
        print(f"halved OFS -> {sys.argv[3]}")
    else:
        print(__doc__)
