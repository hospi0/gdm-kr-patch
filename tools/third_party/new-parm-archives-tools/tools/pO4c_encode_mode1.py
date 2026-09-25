#!/usr/bin/env python3
"""pO4c_encode_mode1.py — MODE-1 variant of the battle-chrome/nameplate VDP1 atlas encoder.

The resident SH-2 decompressor at HWRAM 0x0601A716 selects the LITERAL PIXEL FILTER from a
2-bit `mode` field in the stream header (word0 >> 14). The mode indexes a 16-bit table at
0x0601A9BC whose value is self-written into the code page at 0x0601ABFC (the per-pixel filter
instruction):

    mode 0 : 0x6de3  mov r14,r13   -> P = symbol                (raw, no carry)
    mode 1 : 0x2dea  xor r14,r13   -> P = (prev_px ^ symbol)&0xF (XOR filter, carries)
    mode 2 : 0x3de8  sub r14,r13   -> P = (prev_px - symbol)&0xF (delta filter, carries)  <- pO4_chrome_encode
    mode 3 : 0x0009  nop

`tools/pO4_chrome_encode.py` implements the mode-2 (subtract) path. The party name-plate atlas
(/BATLE/B001.BBG, disc raw 0x29bc4 -> VDP1 VRAM 0x04000) is a MODE-1 (XOR) stream. Re-encoding it
as mode 2 round-trips bit-exact but is ~2 KB larger than the on-disc block budget (orig 24855 B),
so we must re-emit it as mode 1 to fit. This module reuses pO4_chrome_encode's ROM-authoritative
Huffman tree, bit-writer and control-token codecs; ONLY the literal filter differs.

Round-trip is always validated against the ROM decoder oracle (pO4_chrome_codec) before use.
"""
import os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_chrome_encode as enc   # build_tree, BitW, emit_ctrl, emit_end, _rom_decode_raw


def _filter_sym(mode, prev_px, P):
    """Return the Huffman symbol that reproduces output pixel P under `mode`'s filter,
    given the carried previous pixel prev_px. (Inverse of the ROM filter at 0x0601ABFC.)"""
    if mode == 0:
        return P & 0xF
    if mode == 1:
        return (prev_px ^ P) & 0xF
    if mode == 2:
        return (prev_px - P) & 0xF
    raise ValueError(f"mode {mode} has no literal filter (nop)")


def encode(pixels, codelen9, mode=1, zthresh=6):
    """Encode a 4bpp atlas byte image into the compressed stream for the given `mode`.

    Identical tokenization/Huffman/control coding to pO4_chrome_encode.encode; only the
    per-literal symbol filter differs (see _filter_sym). Default mode=1 (XOR)."""
    codes, escape = enc.build_tree(codelen9)
    nib = []
    for byte in pixels:
        nib.append((byte >> 4) & 0xF)
        nib.append(byte & 0xF)
    N = len(nib)

    ctrl_nibs = []
    lit = enc.BitW()
    prev_run = 0
    prev_px = 0
    i = 0
    ZTHRESH = zthresh
    while i < N:
        z = 0
        while i < N and nib[i] == 0:
            z += 1; i += 1
        if z and z < ZTHRESH and i < N:
            i -= z
            z = 0
        lit_nibs = []
        while i < N:
            if nib[i] == 0:
                k = i
                while k < N and nib[k] == 0:
                    k += 1
                if (k - i) >= ZTHRESH:
                    break
            lit_nibs.append(nib[i]); i += 1
        prev_run = enc.emit_ctrl(ctrl_nibs, z, prev_run)
        for P in lit_nibs:
            sym = _filter_sym(mode, prev_px, P)
            L2, c = codes[sym]
            lit.put(c, L2)
            prev_px = P
        lit.put(escape[1], escape[0])
    enc.emit_end(ctrl_nibs)

    while len(ctrl_nibs) % 4 != 0:
        ctrl_nibs.append(0)
    ctrl_bytes = bytearray()
    for k in range(0, len(ctrl_nibs), 2):
        ctrl_bytes.append((ctrl_nibs[k] << 4) | ctrl_nibs[k + 1])

    word0 = (mode << 14) | len(ctrl_bytes)
    out = bytearray()
    out += bytes([(word0 >> 8) & 0xFF, word0 & 0xFF])
    out += ctrl_bytes
    out += bytes(codelen9)
    out += lit.bytes()
    return bytes(out)


if __name__ == "__main__":
    # self-test: round-trip the name-plate atlas through mode-1 encode + ROM decode
    import pO4_chrome_codec as codec
    disc = open(sys.argv[1] if len(sys.argv) > 1 else "output/rc_35/Track1.bin", "rb").read()
    OFF, DST = 0x29bc4, 0x04000
    LO, HI = 0x04000, 0x04000 + 0xFCA0
    ref = codec.run_decode(disc, OFF, DST, 0x12000)
    codelen9, w0 = enc._codelen9_from_disc_bytes(disc, OFF)
    stream = encode(bytes(ref[LO:HI]), codelen9, mode=1, zthresh=6)
    dec = enc._rom_decode_raw(stream, DST)
    mm = sum(1 for k in range(LO, HI) if dec[k] != ref[k])
    print(f"mode-1 round-trip: {(HI-LO)-mm}/{HI-LO} match; stream={len(stream)} B")
