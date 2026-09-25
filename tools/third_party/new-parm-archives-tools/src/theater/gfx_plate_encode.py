#!/usr/bin/env python3
"""Encoder for the theater plate codec (DORAM slot 8 [6]) — inverse of gfx_plate.decode_plate.

REVERSE-ENGINEERED & PROVEN (2026-06-30) against the real engine decoder (func 0x0601A716) via
the sh2emu oracle.  `decode(encode_block(pixels)) == pixels` is **byte-exact over the entire
0x15000-byte plate block** (header + empty + Gumbo + the other plates) — see
gfx_plate_roundtrip.py.

KEY FACTS (corrected vs. the earlier head-start, which had the body misaligned):

* Slot 8 sub-blob [6] (DORAM file off 0x26500) is ONE stream that decodes the WHOLE plate block
  contiguously to VDP1 VRAM 0x299c0.  The decoded block is 0x15000 = 86016 bytes (size comes from
  slot-8 directory entry [0] = `0001 5000 ...`): header 144x40 @0x299c0, empty 152x48 @0x2b040,
  Gumbo 152x48 @0x2ccc0, then the remaining drama plates, all back-to-back.
* Stream layout:  word0 (u16 BE) at [6]+0.  `(word0>>14)&3` selects the running-accumulator mode
  (0=mov/absolute, 1=XOR, 2=sub, 3=nop); the plates use **mode 1 = XOR** (`acc ^= delta`).
  `low13 = word0 & 0x1fff`.  The 18 code-length nibbles (9 bytes) live at [6]+low13+2; the body
  bitstream starts byte-aligned at **[6]+low13+11** (for the header plate low13=0x10 → body @0x1b).
* CODEBOOK: per-stream canonical Huffman built from those code-lengths.  For the plate block it is
  exactly the documented book below (confirmed by dumping the engine's built table @0x0601A9E4).
  Symbols 0x0..0xf are 4-bit deltas; symbol 0x10 = RLE escape (`000001`, table entry leaf-bit set).
* BODY PACKING: plain MSB-first into bytes (== big-endian 32-bit words read sequentially from
  [6]+low13+8, consumed MSB-first).  No bit reversal.
* OUTPUT SKIP: the symbol stream encodes the block starting at output byte **0x0a** (the first 10
  bytes — leading transparent border of the header plate — are NOT symbol-coded; VRAM is 0 there).
  So the body encodes `pixels[10:]`.
* Each emitted nibble is `delta = acc ^ nib` (XOR mode), Huffman-coded, MSB-first; two nibbles per
  8bpp pixel, FIRST nibble = HIGH nibble (`px = (n0<<4)|n1`).

LITERAL PATH (this module): every nibble is coded literally (runs of background → repeated delta-0
`00001`).  This reproduces the pixels byte-exact but yields a body ~the same size as the original
(the codec barely compresses this art).

CLEAN TERMINATION (SOLVED 2026-06-30).  The engine decode is *input-driven* — no output count.
Function 0x0601A716 has a run-length sub-routine at 0x0601A872 entered (a) ONCE at setup (for the
implicit leading run) and (b) on every main-stream RLE escape (`000001`).  It reads a variable-
length run-length code from a SECOND cursor (16-bit words from [6]+2, MSB-first, 4 nibbles/word).
The first secondary nibble `q` selects the path (traced live over 0x0601A872..0x0601A9B8):
  * q < 13         -> direct leading run = q + r12 - 6 nibbles (r12 = previous run value, 0 at
                      setup).  `q == 6` at setup => a ZERO leading run, then fall straight into
                      the main literal loop.
  * q == 14 (0xe)  -> "extend" path: pulls following nibbles into r11 and, when r11's top 16 bits
                      become 0, runs `cmp/eq #0,r0 ; rts` -> the CLEAN EXIT (0x0601a968/0x0601a96c).
So the whole block is coded as: a single ZERO leading run (secondary nibble 0x6), every pixel as a
literal XOR-delta, then ONE final main-stream escape whose secondary read is `0xe` followed by
zeros.  The terminator secondary stream is therefore `0x6e00 0x0000` at [6]+2 (`6` = leading run 0,
`e` = extend-trigger for the final escape, then zeros -> top16==0 -> rts).  encode_block() writes
that secondary stream and appends the terminating escape, so the result round-trips BYTE-EXACT and
exits NORMALLY (no over-read) for the original and English-edited blocks — see gfx_plate_roundtrip.py
and docs/theater-gfx.md "Encoder status".
"""
from __future__ import annotations

# delta -> MSB-first bit code.  Confirmed identical to the engine's built table (0x0601A9E4) for
# the plate block (canonical Huffman over the [6] code-lengths).
CODEBOOK: dict[int, str] = {
    0x0: "00001", 0x1: "000000", 0x2: "00010", 0x3: "00011", 0x4: "00100",
    0x5: "00101", 0x6: "0100", 0x7: "0101", 0x8: "00110", 0x9: "0110",
    0xa: "11", 0xb: "0111", 0xc: "1000", 0xd: "00111", 0xe: "1001", 0xf: "101",
}
RLE_ESCAPE = "000001"          # symbol 0x10 (engine table entry 0x1061, leaf bit set)
OUTPUT_SKIP = 0x0a             # legacy: first 10 output bytes not symbol-coded (leading transparent)
DECODE_SIZE = 0x15000          # whole plate block (from slot-8 directory [0])

# Secondary run-length stream ([6]+2, MSB-first 16-bit words) for a clean-terminating literal body:
#   nibble 0x6 -> ZERO leading run (setup falls straight into the literal loop; skip=0),
#   nibble 0xe -> extend-trigger for the final escape, then zeros -> top16==0 -> rts (clean exit).
TERM_SECONDARY = b"\x6e\x00\x00\x00"   # words 0x6e00 0x0000 written at [6]+2


def _body_start(stream6: bytes) -> int:
    """Byte offset within [6] where the body bitstream starts (= low13 + 11)."""
    word0 = int.from_bytes(stream6[:2], "big")
    return (word0 & 0x1FFF) + 11


def _nibbles(pixels: bytes):
    for px in pixels:
        yield (px >> 4) & 0xF
        yield px & 0xF


def encode_body(pixels: bytes, skip: int = 0, terminate: bool = True) -> bytes:
    """Encode the plate-block pixels -> body bytes (XOR-delta canonical-Huffman, MSB-first packed).

    `skip`      = leading output bytes the stream does NOT symbol-code (0 for the terminating build;
                  the leading run is 0 so all pixels are literal-coded).
    `terminate` = append the final RLE escape (`000001`) that, paired with the TERM_SECONDARY
                  stream, drives the engine to a clean `rts` after the last pixel.
    Runs are coded as repeated delta-0; byte-exact on decode, just not compact.
    """
    bits = []
    acc = 0
    for nib in _nibbles(pixels[skip:]):
        d = acc ^ nib
        acc = nib
        bits.append(CODEBOOK[d])
    if terminate:
        bits.append(RLE_ESCAPE)
    s = "".join(bits)
    if len(s) % 8:
        s += "0" * (8 - len(s) % 8)
    return bytes(int(s[i:i + 8], 2) for i in range(0, len(s), 8))


def encode_block(pixels: bytes, orig_stream6: bytes) -> bytes:
    """Re-encode the full plate block into a clean-terminating [6] stream.

    pixels       : the decoded 0x15000-byte plate block, with your English edits applied.
    orig_stream6 : the original slot-8 [6] bytes (provides word0 + the code-length table the engine
                   parses to rebuild the codebook + running-mode; reused verbatim EXCEPT the
                   secondary run-length region [2:low13+2], which is overwritten with TERM_SECONDARY).

    Returns the new [6] bytes (prefix + literal body + terminating escape).  The result round-trips
    byte-exact AND exits normally (no over-read) through the real engine decoder.
    """
    word0 = int.from_bytes(orig_stream6[:2], "big")
    low13 = word0 & 0x1FFF
    bs = low13 + 11                       # body start (== _body_start)
    prefix = bytearray(orig_stream6[:bs])
    # Rewrite the secondary run-length region [2 : low13+2] with the terminating stream (leading
    # run 0 + extend-trigger + zero tail).  word0 [0:2] and the code-lengths [low13+2 : bs] are kept.
    sec_start, sec_end = 2, low13 + 2
    for i in range(sec_start, sec_end):
        prefix[i] = 0
    prefix[sec_start:sec_start + len(TERM_SECONDARY)] = TERM_SECONDARY
    return bytes(prefix) + encode_body(pixels, skip=0, terminate=True)


# Backwards-compat shim for the head-start API (header24 + body); prefer encode_block.
HEADER_LEN = 0x18


def encode_plate(pixels: bytes, header24: bytes) -> bytes:  # pragma: no cover - legacy
    raise NotImplementedError(
        "encode_plate(header24) was based on a wrong 24-byte body offset. Use encode_block("
        "full_block_pixels, orig_stream6): the body starts at low13+11, not 0x18, and the block "
        "is ONE stream of size 0x15000."
    )


# --- pure-Python reference decoder (no-RLE path) — offline self-validation only ---
_DECODE = {v: k for k, v in CODEBOOK.items()}


def ref_decode_body(body: bytes, n_pixels: int, skip: int = 0) -> bytes:
    bitstr = "".join(f"{b:08b}" for b in body)
    px = bytearray(b"\x00" * skip)
    acc = 0
    hi = None
    i = 0
    cur = ""
    while len(px) < n_pixels and i < len(bitstr):
        cur += bitstr[i]
        i += 1
        if cur == RLE_ESCAPE:      # terminator (or any escape) — stop; pixels are complete
            break
        if cur in _DECODE:
            acc ^= _DECODE[cur]
            cur = ""
            if hi is None:
                hi = acc
            else:
                px.append((hi << 4) | acc)
                hi = None
    return bytes(px)


def _selftest() -> None:
    import random
    random.seed(1)
    for _ in range(200):
        n = random.randint(2, 400) * 1
        pixels = bytes(random.randint(0, 255) for _ in range(n))
        body = encode_body(pixels, skip=0, terminate=True)  # literal body + terminating escape
        back = ref_decode_body(body, len(pixels))
        assert back == pixels, "round-trip mismatch"
    codes = list(CODEBOOK.values()) + [RLE_ESCAPE]
    for a in codes:
        for b in codes:
            if a is not b:
                assert not b.startswith(a), f"prefix collision {a} {b}"
    print("gfx_plate_encode self-test PASSED (200 reference round-trips + prefix-free codebook)")


if __name__ == "__main__":
    _selftest()
