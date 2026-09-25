#!/usr/bin/env python3
"""mg_field_codec.py — ENCODER for the resident FIELD-SPRITE codec (entry 0x0601A716).

This is the third codec in the game (distinct from the KNPAN inline-chunk Huffman
0x06015DF0 and the theater RLE): the resident routine at HWRAM 0x0601A716 that the
field engine calls per-frame for NPC sprites and that game 6 (Big-Eater Grandia Cup,
HAYAG.BIN) uses for its TITLE LOGO in /FIELD/HYABG.BIN slot 4 (+0x260).

Format (lifted from the SH-2 disassembly, verified byte-exact by emulating the real
decoder with tools/sh2emu.py — see work/pD_nav/g6re/):

  blob = [u16BE header][stream A: L bytes][9 bytes code lengths][stream B bitstream]
  header: bits15-14 = delta mode (0=mov,1=xor,2=sub,3=nop on prev pixel nibble)
          bit13     = start mode (1 = literal-first, 0 = zero-run-first)
          bits12-0  = L = stream A byte length
  output = nibbles packed 2/byte big-endian (8 per u32 word written to dst)

  stream B (MSB-first bitstream, starts at byte offset L+11, decoder loads the
  surrounding aligned u32s and skips the misalignment): Huffman codes over 17
  symbols (0..16), max code length 8, decoded via a 256-entry LUT built from the
  9-byte nibble code-length table (sym i length = nibble i; sym17 pad).
  Symbols 0..15 = literal nibble (through the delta filter); 16 = ESCAPE to a
  zero-run event.

  Canonical code assignment (from the LUT fill loop): symbols sorted by
  (length DESC, index ASC) get consecutive LUT ranges of 2^(8-len) entries from 0;
  code = top `len` bits of range start. Kraft sum MUST be exactly 256 or the
  builder hangs. This encoder uses a FIXED complete code: sym0..15 len 5
  (code = '0'+nibble), sym16 len 1 (code = '1').

  stream A (nibbles packed in BE u16s from +2): one group per escape, consumed in
  escape order. Group forms (v = first nibble):
    v 0..12          run = prev_run + v - 6
    13, n (n<8)      run = prev_run + n - 14
    13, n (n>=8)     run = prev_run + n - 1
    14, n1, n2       run = (n1<<4)|n2   absolute; 0 = END OF STREAM
    15, n1..n4       run = 16-bit absolute
  A run emits `run` zero nibbles. This encoder only emits the absolute forms.

Public API: encode(img_bytes) -> blob bytes.
CLI: mg_field_codec.py encode IMG.bin OUT.blob [--pad N]
"""
import argparse
import struct


def encode(img: bytes, run_threshold: int = 6) -> bytes:
    nibs = []
    for b in img:
        nibs.append(b >> 4)
        nibs.append(b & 15)
    N = len(nibs)
    bits = []
    runs = []
    i = 0
    while i < N:
        if nibs[i] == 0:
            j = i
            while j < N and nibs[j] == 0:
                j += 1
            z = j - i
            if z >= run_threshold:
                while z > 0:  # split runs beyond the 16-bit absolute form
                    part = min(z, 0xFFFF)
                    bits.append(1)
                    runs.append(part)
                    z -= part
                i = j
                continue
        bits.append(0)
        n = nibs[i]
        for k in (3, 2, 1, 0):
            bits.append((n >> k) & 1)
        i += 1
    bits.append(1)          # escape ...
    runs.append(0)          # ... run 0 = end of stream

    an = []
    for z in runs:
        if z == 0:
            an += [14, 0, 0]
        elif z <= 255:
            an += [14, (z >> 4) & 15, z & 15]
        else:
            an += [15, (z >> 12) & 15, (z >> 8) & 15, (z >> 4) & 15, z & 15]
    while len(an) % 4:      # pad to whole u16 words
        an.append(0)
    sa = bytearray()
    for k in range(0, len(an), 2):
        sa.append((an[k] << 4) | an[k + 1])
    L = len(sa)
    if L > 0x1FFF:
        raise ValueError(f"stream A too long ({L})")

    hdr = 0x2000 | L        # mode 0 (mov), literal-first
    lens = bytes([0x55] * 8 + [0x10])  # sym0..15 len5, sym16 len1, sym17 unused

    sb = bytearray()
    acc = cnt = 0
    for b in bits:
        acc = (acc << 1) | b
        cnt += 1
        if cnt == 8:
            sb.append(acc)
            acc = cnt = 0
    if cnt:
        sb.append(acc << (8 - cnt))
    sb += b"\0" * 8         # 64-bit window prefetch margin

    return struct.pack(">H", hdr) + bytes(sa) + lens + bytes(sb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["encode"])
    ap.add_argument("img")
    ap.add_argument("out")
    ap.add_argument("--pad", type=int, default=0, help="zero-pad blob to this size")
    a = ap.parse_args()
    img = open(a.img, "rb").read()
    blob = encode(img)
    if a.pad:
        if len(blob) > a.pad:
            raise SystemExit(f"blob {len(blob)}B exceeds slot {a.pad}B")
        blob += b"\0" * (a.pad - len(blob))
    open(a.out, "wb").write(blob)
    print(f"encoded {len(img)}B image -> {len(blob)}B blob")


if __name__ == "__main__":
    main()
