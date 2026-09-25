#!/usr/bin/env python3
"""pO4_chrome_encode.py — the INVERSE of the battle-chrome VDP1 sprite-atlas codec.

Companion to tools/pO4_chrome_codec.py (the verified DECODER oracle). This encodes a
target 4bpp VDP1-VRAM atlas image back into the on-disc compressed stream that the
resident SH-2 decompressor at HWRAM 0x0601A716 consumes.

FORMAT (cracked this lane — corrects the rc_34 "canonical-Huffman+RLE over 32-bit words"
under-description; it is a Huffman-coded 4bpp *nibble* stream, not 32-bit literal words):

  stream = word0(2, BE) | control-stream(bytes) | codelen(9 bytes) | literal-huffman(bytes)
  word0        : (mode<<14) | ctrl_byte_count ; mode=2 for the chrome/plate streams.
                 lit_off = (word0 & 0x1fff) + 11 ; codelen bytes live at src+lit_off-9.
  control      : a flat nibble stream (4 nibbles / 16-bit BE word, MSB nibble first) of
                 DELTA-coded run tokens. Each token = a ZERO-RUN length (in 4bpp pixels):
                   nib 0..12 : count = prev + (nib-6)
                   nib 13    : read n2; count = prev + (n2-14 if n2<8 else n2-1)
                   nib 14    : read n2,n3; count = (n2<<4)|n3   (ABSOLUTE 8-bit; 0 => END)
                   nib 15    : read n2..n5; count = 16-bit ABSOLUTE
                 'prev' is the previous token's count (updated by every token).
  literal      : after each zero-run, LITERAL pixels are canonical-Huffman codes (MSB-first)
                 over 16 nibble symbols (code lengths from the 9 codelen bytes), terminated
                 by the reserved ESCAPE symbol (idx16) which signals "read next control token".
                 The final control token is END (nib14 + 0x00).
                 *** PIXELS ARE DELTA-FILTERED ***: the emitted pixel nibble is a running
                 subtract of the Huffman symbols: out = (prev - sym) & 0xF, prev carrying
                 (decoder store site 0x0601ABFC is `sub r14,r13`, NOT `mov` — the disasm blob
                 is stale there; confirmed by live trace). A ZERO-RUN token writes 0s WITHOUT
                 touching prev (prev keeps its last literal value across the run). So to output
                 pixel P the encoder emits symbol sym = (prev - P) & 0xF and sets prev = P.
  Whole thing is a flat 4bpp nibble stream packed 8 nibbles / 32-bit output word, MSB-first.

The canonical codes + escape code are read back from the game's OWN table-builder (the ROM
prologue 0x0601A716..0x0601A7F8) executed under pO4_sh2emu — so the tree is authoritative.
Every encoded stream is round-trip-checked against pO4_chrome_codec.decode (the ROM decoder).
"""
import argparse, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_sh2emu as sh2emu
import pO4_chrome_codec as codec

CODE_BLOB = codec.CODE_BLOB
CODE_BASE = codec.CODE_BASE
ENTRY     = codec.ENTRY


# ---------------------------------------------------------------------------
# 1. Get the canonical Huffman codes from the ROM table-builder (authoritative)
# ---------------------------------------------------------------------------
def build_tree(codelen9):
    """Run the ROM prologue with a synthetic header carrying `codelen9` (9 bytes) and
    dump the built 256-entry LUT. Returns (codes, escape) where codes[nibble]=(len,code)
    and escape=(len,code) for the idx16 end-of-literal-run symbol."""
    code = bytearray(open(CODE_BLOB, "rb").read())
    src_hw = 0x060D8B90
    # Minimal synthetic source: word0 then a control byte area then codelen then a little
    # literal. lit_off must place codelen9 correctly. We only run to the LUT-built point,
    # so control content is irrelevant; only word0's lit_off field + the codelen bytes matter.
    ctrl_bytes = 2          # tiny, arbitrary (prologue doesn't consume control before LUT)
    lit_off = 2 + ctrl_bytes + 9
    word0 = (2 << 14) | ctrl_bytes
    src = bytearray(0x400)
    src[0] = (word0 >> 8) & 0xFF; src[1] = word0 & 0xFF
    src[2 + ctrl_bytes: 2 + ctrl_bytes + 9] = bytes(codelen9)
    mem = sh2emu.Mem()
    mem.map(CODE_BASE, code)
    mem.map(0x06001000, bytearray(0x1000))
    mem.map(src_hw, bytes(src))
    mem.map(0x25C00000, bytearray(0x80000))
    lut_base = [None]

    class L(sh2emu.SH2):
        def _exec_at(self, pc, in_delay=False):
            if pc == 0x0601a800 and lut_base[0] is None:
                lut_base[0] = self.R[2]; raise SystemExit
            return super()._exec_at(pc, in_delay)

    cpu = L(mem)
    dst = 0x25C00000 + 0x44000
    regs = [0x20, 0x06017054, 0x06086878, ENTRY, dst, src_hw, src_hw, 0xFE80,
            0x060A093E, 0x8, 0x10000, 0x0602C128, 0x060C7DD0, 0, 0x060AFD58, 0x06001EBC]
    for i, v in enumerate(regs): cpu.R[i] = v
    cpu.PR = 0xABCDE0
    try:
        cpu.run(ENTRY, max_steps=5_000_000, stop_pr=0xABCDE0)
    except SystemExit:
        pass
    base = lut_base[0]
    lut = [mem.r16(base + 2 * i) for i in range(256)]
    # extract shortest prefix per symbol idx
    seen = {}
    for i, v in enumerate(lut):
        idx = (v >> 8) & 0xFF
        L2 = (v >> 4) & 0xF
        valid_bit0 = v & 1
        key = idx
        if key not in seen:
            seen[key] = (i, L2, valid_bit0)
    codes = {}
    escape = None
    for idx, (i, L2, b0) in seen.items():
        if L2 == 0:
            continue
        code = i >> (8 - L2)
        if idx < 16:
            codes[idx] = (L2, code)
        elif idx == 16:
            escape = (L2, code)
    return codes, escape


# ---------------------------------------------------------------------------
# 2. Bit writer (MSB-first) for the literal Huffman stream
# ---------------------------------------------------------------------------
class BitW:
    def __init__(self):
        self.bits = []
    def put(self, value, length):
        for k in range(length - 1, -1, -1):
            self.bits.append((value >> k) & 1)
    def bytes(self):
        out = bytearray()
        b = 0; n = 0
        for bit in self.bits:
            b = (b << 1) | bit; n += 1
            if n == 8:
                out.append(b); b = 0; n = 0
        if n:
            out.append(b << (8 - n))
        return bytes(out)


# ---------------------------------------------------------------------------
# 3. Control-token (zero-run) nibble encoder
# ---------------------------------------------------------------------------
def emit_ctrl(nibs, count, prev):
    """Append the control nibble(s) for a zero-run of `count` given `prev`. Returns
    the new prev (== count)."""
    delta = count - prev
    if -6 <= delta <= 6:
        nibs.append((delta + 6) & 0xF)
    elif 7 <= delta <= 14:
        nibs.append(13); nibs.append(delta + 1)          # n2>=8 branch: delta=n2-1
    elif -14 <= delta <= -7:
        nibs.append(13); nibs.append(delta + 14)         # n2<8 branch: delta=n2-14
    elif 0 <= count <= 0xFF:
        nibs.append(14); nibs.append((count >> 4) & 0xF); nibs.append(count & 0xF)
    elif 0 <= count <= 0xFFFF:
        nibs.append(15)
        nibs.append((count >> 12) & 0xF); nibs.append((count >> 8) & 0xF)
        nibs.append((count >> 4) & 0xF); nibs.append(count & 0xF)
    else:
        raise ValueError(f"zero-run {count} out of range")
    return count


def emit_end(nibs):
    nibs.append(14); nibs.append(0); nibs.append(0)


# ---------------------------------------------------------------------------
# 4. The encoder proper
# ---------------------------------------------------------------------------
def encode(pixels, codelen9, mode=2, zthresh=9):
    """pixels = the 4bpp atlas bytes to reproduce (the decoded VRAM window content,
    e.g. atlas[0x44000:0x4afe0]). Returns the compressed stream bytes."""
    codes, escape = build_tree(codelen9)
    # flatten to nibble stream (hi nibble first per byte)
    nib = []
    for byte in pixels:
        nib.append((byte >> 4) & 0xF)
        nib.append(byte & 0xF)
    N = len(nib)

    ctrl_nibs = []
    lit = BitW()
    prev_run = 0    # previous ZERO-RUN length (delta base for control tokens)
    prev_px = 0     # previous output pixel (delta base for literal symbols)
    i = 0
    ZTHRESH = zthresh  # runs of >= this many zeros become a zero-run token; shorter stay literal
    # tokenize into (zero-run, literal-run) segments. A literal run may itself contain short
    # (< ZTHRESH) zero gaps, which are encoded as delta symbols (P=0).
    while i < N:
        # measure a maximal zero-run for the zero-run TOKEN (only long runs)
        z = 0
        while i < N and nib[i] == 0:
            z += 1; i += 1
        # if the zero-run is short, push it back to be handled as literal pixels
        if z and z < ZTHRESH and i < N:
            # emit a zero-run token of 0 (keeps structure), then the zeros as literals below
            i -= z
            z = 0
        # collect the literal run: pixels until the next LONG zero-run
        lit_nibs = []
        while i < N:
            if nib[i] == 0:
                # look ahead: is this the start of a long zero-run?
                k = i
                while k < N and nib[k] == 0:
                    k += 1
                if (k - i) >= ZTHRESH:
                    break
            lit_nibs.append(nib[i]); i += 1
        prev_run = emit_ctrl(ctrl_nibs, z, prev_run)
        for P in lit_nibs:
            sym = (prev_px - P) & 0xF
            L2, c = codes[sym]
            lit.put(c, L2)
            prev_px = P
        lit.put(escape[1], escape[0])
    emit_end(ctrl_nibs)

    # pack control nibbles -> bytes (2 nibbles/byte, hi first); pad to whole 16-bit words
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


def encode_fit(pixels, codelen9, budget=0x4000, zthreshes=(6, 5, 7, 4, 8, 3, 9)):
    """encode() with a deterministic zthresh search: return the first stream that fits
    `budget`. The stream size depends on the atlas CONTENT at the moment a fold runs, so
    an intermediate chain stage (e.g. pO4b on the still-mostly-JP vanilla atlas) can
    overflow at the fixed zthresh=6 even though the final chain state fits (rc_48
    composition, 2026-07-06: 16411 > 16384 at the pO4b stage). Raises with the size
    table if nothing fits."""
    sizes = {}
    for zt in zthreshes:
        stream = encode(pixels, codelen9, zthresh=zt)
        sizes[zt] = len(stream)
        if len(stream) <= budget:
            if zt != zthreshes[0]:
                print(f"  encode_fit: zthresh={zt} -> {len(stream)} B (default overflowed: {sizes})")
            return stream
    raise SystemExit(f"encode_fit: no zthresh fits budget {budget}: {sizes}")


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------
def _codelen9_from_disc_bytes(src, src_off):
    hdr = codec.read_logical(src, src_off, 16)
    w0 = (hdr[0] << 8) | hdr[1]
    lit_off = (w0 & 0x1fff) + 11
    body = codec.read_logical(src, src_off, lit_off + 4)
    return body[lit_off - 9: lit_off], w0


def _codelen9_from_disc(disc_path, src_off):
    src = open(disc_path, "rb").read()
    hdr = codec.read_logical(src, src_off, 16)
    w0 = (hdr[0] << 8) | hdr[1]
    lit_off = (w0 & 0x1fff) + 11
    body = codec.read_logical(src, src_off, lit_off + 4)
    return body[lit_off - 9: lit_off], w0


def cmd_encode(a):
    atlas = open(a.atlas, "rb").read()
    pixels = atlas[a.win_lo:a.win_hi]
    codelen9, _ = _codelen9_from_disc(a.src, a.src_off)
    stream = encode(pixels, codelen9, zthresh=a.zthresh)
    open(a.out, "wb").write(stream)
    print(f"encoded {a.win_hi-a.win_lo} px bytes -> {len(stream)} stream bytes -> {a.out}")


def _rom_decode_raw(stream, dst_base):
    """Decode an already-logical stream directly via the ROM decompressor (the oracle)."""
    code = bytearray(open(codec.CODE_BLOB, "rb").read())
    src_hw = 0x060D8B90
    mem = sh2emu.Mem()
    mem.map(codec.CODE_BASE, code)
    mem.map(0x06001000, bytearray(0x1000))
    mem.map(src_hw, bytes(stream) + bytes(0x2000))
    mem.map(0x25C00000, bytearray(0x80000))
    cpu = sh2emu.SH2(mem)
    dst = 0x25C00000 + dst_base
    regs = [0x20, 0x06017054, 0x06086878, codec.ENTRY, dst, src_hw, src_hw, 0xFE80,
            0x060A093E, 0x8, 0x10000, 0x0602C128, 0x060C7DD0, 0, 0x060AFD58, 0x06001EBC]
    for i, v in enumerate(regs):
        cpu.R[i] = v
    cpu.PR = 0xABCDE0
    cpu.run(codec.ENTRY, max_steps=200_000_000, stop_pr=0xABCDE0)
    return bytes(mem._find(0x25C00000)[0])


def cmd_verify(a):
    """Round-trip gate: decode the on-disc atlas, re-encode it, decode the re-encoded stream via
    the ROM oracle, assert byte-identical over the window. Zero hardware."""
    disc = open(a.src, "rb").read()
    ref = codec.run_decode(disc, a.src_off, a.dst_base, 0x5000)
    codelen9, _ = _codelen9_from_disc(a.src, a.src_off)
    stream = encode(bytes(ref[a.win_lo:a.win_hi]), codelen9, zthresh=a.zthresh)
    dec = _rom_decode_raw(stream, a.dst_base)
    n = sum(1 for i in range(a.win_lo, a.win_hi) if dec[i] != ref[i])
    tot = a.win_hi - a.win_lo
    print(f"round-trip window {a.win_lo:#x}-{a.win_hi:#x}: {tot-n}/{tot} match "
          f"({'BIT-EXACT PASS' if n == 0 else str(n)+' MISMATCH'}); stream {len(stream)} B")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("encode")
    p.add_argument("--atlas", required=True, help="full 0x80000 VDP1 VRAM image to reproduce")
    p.add_argument("--src", required=True, help="disc Track1.bin (for the original codelen header)")
    p.add_argument("--src-off", type=lambda x: int(x, 0), default=0xEBE910)
    p.add_argument("--win-lo", type=lambda x: int(x, 0), default=0x44000)
    p.add_argument("--win-hi", type=lambda x: int(x, 0), default=0x4afe0)
    p.add_argument("--zthresh", type=int, default=6)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_encode)
    pv = sub.add_parser("verify", help="round-trip the on-disc atlas through encode->ROM-decode")
    pv.add_argument("--src", required=True)
    pv.add_argument("--src-off", type=lambda x: int(x, 0), default=0xEBE910)
    pv.add_argument("--dst-base", type=lambda x: int(x, 0), default=0x44000)
    pv.add_argument("--win-lo", type=lambda x: int(x, 0), default=0x44000)
    pv.add_argument("--win-hi", type=lambda x: int(x, 0), default=0x4afe0)
    pv.add_argument("--zthresh", type=int, default=6)
    pv.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
