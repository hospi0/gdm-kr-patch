#!/usr/bin/env python3
"""pO4_chrome_codec.py — the battle-chrome VDP1 sprite-atlas CODEC, CRACKED (decoder).

Lane O4/O1. This is the decompressor that was the historic wall behind the JP in-battle
chrome (技/魔法/防御/ring labels), the party name-plates, and the Combo/Critical popups.

WHAT THIS IS
------------
The chrome atlas is decompressed by a resident SH-2 routine at **HWRAM 0x0601A716**
(NOT the mgame mg_codec, and NOT SCU DMA — the prior "un-watchable DMA" claim was WRONG:
it is plain SH-2 stores. A write-watch on the UNCACHED VRAM mirror 0x25C4xxxx DOES fire,
at store PCs 0x0601A8CE / 0x0601A8E4 / 0x0601AC0A). Rather than hand-port the
codec (a canonical-Huffman + RLE over 32-bit pixel words, 2-bit mode header + 18 4-bit
code-lengths), we EXECUTE the real routine via the SH-2 interpreter (tools/pO4_sh2emu.py)
on the on-disc compressed stream. Output is bit-exact vs the live VDP1 VRAM dump
(verified 16384/16384 in the 0x44000-0x48000 window; see `verify`).

The compressed streams live VERBATIM on the disc (Track1.bin, raw byte offsets) inside the
SYS.IDX-indexed /BATLE resident archive (loaded to HWRAM 0x060D0000+ at battle start):
  * chrome block  -> disc 0x00EBE910  (~702 B) -> VDP1 VRAM 0x44000..0x4afe0 (28640 B); holds 技 @0x473a0
  * name-plates   -> disc 0x00EBDFA4         -> VDP1 VRAM 0x40000
  * 3rd stream    -> disc 0x00EB4B1C         -> VRAM 0x25E04000 (work fb)

USAGE
  pO4_chrome_codec.py decode --src Track1.bin --src-off 0xEBE910 --dst-base 0x44000 --out atlas.bin
  pO4_chrome_codec.py verify --src Track1.bin --src-off 0xEBE910 --live work/.../vdp1-vram.bin

decode writes the FULL 0x80000-byte VDP1 VRAM image (zero-filled except the decoded window)
so `atlas.bin[0x473a0:...]` etc. are directly comparable to a --dump-wram vdp1-vram.bin.
"""
import argparse, os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import pO4_sh2emu as sh2emu

CODE_BLOB = os.path.join(os.path.dirname(TOOLS), "docs", "lanes", "pO4_decomp_code.bin")
CODE_BASE = 0x0601A000
ENTRY     = 0x0601A716

RAW_SECTOR, SYNC_HEADER, USER_DATA = 2352, 16, 2048

def read_logical(disc, raw_off, nbytes):
    """Reconstruct `nbytes` of the LOGICAL (de-sectored) stream starting at raw byte
    offset `raw_off` in a 2352-byte-sector Track1.bin. Strips the 16 B sync+header and
    288 B ECC per sector so the result matches the HWRAM-loaded copy the game decodes."""
    out = bytearray()
    o = raw_off
    while len(out) < nbytes:
        sec = o // RAW_SECTOR
        ino = o % RAW_SECTOR
        if ino < SYNC_HEADER:
            ino = SYNC_HEADER
        data_end = sec * RAW_SECTOR + SYNC_HEADER + USER_DATA
        chunk = disc[sec * RAW_SECTOR + ino: data_end]
        out += chunk
        o = (sec + 1) * RAW_SECTOR + SYNC_HEADER
    return bytes(out[:nbytes])

def run_decode(src_bytes, src_off, dst_base, comp_len=0x1000):
    """Decode one stream. dst_base = VDP1 VRAM byte offset (e.g. 0x44000).
    Returns the full 0x80000 VDP1 VRAM image with the decoded window filled."""
    code = bytearray(open(CODE_BLOB, "rb").read())      # 0x0601A000..0x0601B000 (code + scratch)
    src_hw = 0x060D8B90                                 # arbitrary HWRAM addr to host the source
    stream = read_logical(src_bytes, src_off, comp_len)  # de-sector to the logical stream
    mem = sh2emu.Mem()
    mem.map(CODE_BASE, code)                             # decompressor code + self-modified LUT
    mem.map(0x06001000, bytearray(0x1000))              # stack page (r15=0x06001EBC)
    mem.map(src_hw, bytearray(stream) + bytearray(0x2000))                  # compressed source
    mem.map(0x25C00000, bytearray(0x80000))            # dest VDP1 VRAM (uncached)
    cpu = sh2emu.SH2(mem)
    # entry regs: r4=dest VRAM abs, r5=r6=source; r7/r9/r10 constants observed at the live entry.
    dst_abs = 0x25C00000 + dst_base
    regs = [0x20, 0x06017054, 0x06086878, ENTRY, dst_abs, src_hw, src_hw,
            0xFE80, 0x060A093E, 0x8, 0x10000, 0x0602C128, 0x060C7DD0, 0, 0x060AFD58, 0x06001EBC]
    for i, v in enumerate(regs):
        cpu.R[i] = v
    SENT = 0x00ABCDE0
    cpu.PR = SENT
    cpu.run(ENTRY, max_steps=80_000_000, stop_pr=SENT)
    return bytes(mem._find(0x25C00000)[0])

def cmd_decode(a):
    src = open(a.src, "rb").read()
    vram = run_decode(src, a.src_off, a.dst_base, a.len)
    open(a.out, "wb").write(vram)
    nz = sum(1 for b in vram if b)
    print(f"decoded stream @disc {a.src_off:#x} -> VRAM {a.dst_base:#x}; {nz} nonzero bytes -> {a.out}")

def cmd_verify(a):
    src = open(a.src, "rb").read()
    vram = run_decode(src, a.src_off, a.dst_base, a.len)
    live = open(a.live, "rb").read()
    lo, hi = a.win_lo, a.win_hi
    n = sum(1 for i in range(lo, hi) if vram[i] != live[i])
    print(f"verify window {lo:#x}-{hi:#x}: {(hi-lo)-n}/{hi-lo} bytes match "
          f"({'BIT-EXACT PASS' if n == 0 else str(n)+' MISMATCH'})")
    print(f"  waza 0x473a0 decoded: {vram[0x473a0:0x473a0+16].hex()}")
    print(f"  waza 0x473a0 live   : {live[0x473a0:0x473a0+16].hex()}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("decode", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--src", required=True)
        p.add_argument("--src-off", type=lambda x: int(x, 0), default=0xEBE910)
        p.add_argument("--dst-base", type=lambda x: int(x, 0), default=0x44000)
        p.add_argument("--len", type=lambda x: int(x, 0), default=0x5000)
        if name == "decode":
            p.add_argument("--out", required=True); p.set_defaults(fn=cmd_decode)
        else:
            p.add_argument("--live", required=True)
            p.add_argument("--win-lo", type=lambda x: int(x, 0), default=0x44000)
            p.add_argument("--win-hi", type=lambda x: int(x, 0), default=0x48000)
            p.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
