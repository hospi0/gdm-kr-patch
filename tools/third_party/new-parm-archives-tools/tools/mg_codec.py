#!/usr/bin/env python3
"""mg_codec.py — Grandia: Digital Museum minigame graphics codec (ST1 Huffman+delta).

Reverse-engineered from the resident engine decompressor at HWRAM 0x06015DF0
(see docs/mgame-format.md "Codec"). The routine is a static-Huffman bit decoder
with a per-stream delta filter and an optional 32-bit additive bias, emitting
big-endian 32-bit words straight to VDP1 VRAM.

Decode algorithm (word-output path, flag byte [0x06014D4C]==0):
  src    = source byte pointer; bits are read MSB-first from big-endian 32-bit
           words. The first mask = init_mask[src & 3] = 0x80000000 >> 8*(src&3)
           (i.e. start at byte (src&3) within the first aligned word). src is
           then word-aligned down.
  tree   = a node table (base r4). A node at byte-offset `node` has two child
           half-words: child0 = u16[base+node+4] (taken when the bit is 0),
           child1 = u16[base+node+6] (bit==1). Walk from root r5 while the
           current node value > THRESHOLD (0x800). When node <= THRESHOLD it is a
           leaf: node==0x800 => END-OF-STREAM; otherwise symbol = node >> 3.
  filter = running 1-byte accumulator `acc`; each output byte =
             mode 0 (copy): acc = symbol
             mode 1 (xor) : acc ^= symbol
             mode 2 (add) : acc  = (acc + symbol) & 0xff
           acc persists across the whole stream (a delta filter).
  output = four filtered bytes are packed big-endian into a 32-bit word, the
           32-bit `bias` (= r7*0x10001 on the word path; r7 is usually 0) is
           added, and the word is stored; repeat until EOS, then any partial
           word is flushed (remaining bytes shifted up, bias added, stored).

Re-encoding keeps the SAME tree (so the game rebuilds an identical decoder):
compress() walks `tree` to derive each symbol's canonical bit-code, applies the
inverse filter to the pixels, and emits the Huffman bitstream + EOS, matching the
decoder bit/word layout exactly.
"""
import struct

THRESHOLD = 0x800
EOS = 0x800


def _init_mask(src_addr):
    return 0x80000000 >> (8 * (src_addr & 3))


def build_decode_tree(tree_bytes, base_off=0):
    """Return dict node_off -> (child0, child1) reading u16 BE at node+4/node+6."""
    # We don't need a dict; decode reads on the fly. Helper kept for analysis.
    return tree_bytes


def decode_ex(src, tree, root, mode=2, bias=0, src_align_phase=0, max_out=None):
    """Like decode() but also returns the number of source bytes consumed
    (word-granular: the offset of the next unread word from the aligned start).
    Useful for threading consecutive chunks that share one source buffer."""
    out, pos = _decode_impl(src, tree, root, mode, bias, src_align_phase, max_out)
    return out, pos


def decode(src, tree, root, mode=2, bias=0, src_align_phase=0, max_out=None):
    out, _ = _decode_impl(src, tree, root, mode, bias, src_align_phase, max_out)
    return out


def decode_end(src, tree, root, mode=2, bias=0, src_align_phase=0, max_out=None):
    """Decode and return (out, cursor) where `cursor` is the BYTE-precise source
    offset the engine leaves in [0x06014D9C] after EOS — i.e. the start of the next
    inline descriptor. The decompressor exit (HWRAM 0x06015EA4-0x06015ECE) backs the
    word pointer up by 0..4 bytes from the final bit mask; that overlap is why each
    chunk's EOS word shares bytes with the following tree-def. `cursor` is relative
    to the aligned start passed in (add (orig_src & ~3) for an absolute file offset).
    """
    # NOTE: decode to the actual EOS leaf (max_out=None). The engine reads the EOS
    # code before backing up the cursor; stopping early at max_out would leave the
    # mask short by the EOS code length and mis-place the next descriptor.
    out, pos, mask = _decode_impl(src, tree, root, mode, bias, src_align_phase,
                                  None, want_mask=True)
    old_b31 = (mask >> 31) & 1
    rot = ((mask << 1) | old_b31) & 0xFFFFFFFF
    if old_b31:
        backup = 4
    elif rot & 0x000000FF:
        backup = 0
    elif rot & 0x0000FF00:
        backup = 1
    elif rot & 0x00FF0000:
        backup = 2
    else:
        backup = 3
    return out, pos - backup


def _decode_impl(src, tree, root, mode=2, bias=0, src_align_phase=0, max_out=None,
                 want_mask=False):
    """Decode one Huffman+delta stream.

    src   : bytes of the compressed stream (starting at the aligned word that
            contains the first bit; src_align_phase = original_src_addr & 3).
    tree  : node table bytes (index 0 == engine tree base r4).
    root  : root node byte-offset (r5).
    mode  : filter (0 copy / 1 xor / 2 add).
    bias  : 32-bit value added to each assembled word.
    """
    mask = 0x80000000 >> (8 * (src_align_phase & 3))
    pos = 0
    word = struct.unpack_from(">I", src, pos)[0]; pos += 4
    acc = 0
    out = bytearray()
    cur = bytearray()  # pending decoded bytes for the current word

    def next_bit():
        nonlocal mask, word, pos
        bit = 1 if (word & mask) else 0
        # rotr the 32-bit mask; on full wrap (mask was 0x1) refill the word
        if mask == 1:
            mask = 0x80000000
            if pos + 4 <= len(src):
                word = struct.unpack_from(">I", src, pos)[0]
            else:
                word = 0
            pos += 4
        else:
            mask >>= 1
        return bit

    while True:
        node = root
        while node > THRESHOLD:
            b = next_bit()
            off = node + (6 if b else 4)
            node = struct.unpack_from(">H", tree, off)[0]
        if node == EOS:
            break
        sym = node >> 3
        if mode == 0:
            acc = sym
        elif mode == 1:
            acc ^= sym
        else:
            acc = (acc + sym) & 0xFF
        cur.append(acc)
        if len(cur) == 4:
            w = (struct.unpack(">I", bytes(cur))[0] + bias) & 0xFFFFFFFF
            out += struct.pack(">I", w)
            cur = bytearray()
        if max_out and len(out) >= max_out:
            break
    # flush partial word: remaining bytes are shifted up (engine: shll8 per missing byte)
    if cur:
        while len(cur) < 4:
            cur.append(0)
        w = (struct.unpack(">I", bytes(cur))[0] + bias) & 0xFFFFFFFF
        out += struct.pack(">I", w)
    if want_mask:
        return bytes(out), pos, mask
    return bytes(out), pos


# --------------------------------------------------------------------------
# Encoder: derive symbol -> bitcode from the same tree, inverse-filter, emit.

def derive_codes(tree, root):
    """Walk the tree; return {symbol: (nbits, code_int)} with MSB-first codes."""
    codes = {}
    # DFS: bit 0 -> child at node+4, bit 1 -> child at node+6
    stack = [(root, 0, 0)]  # (node, depth, code)
    seen = 0
    while stack:
        node, depth, code = stack.pop()
        seen += 1
        if seen > 1 << 20:
            raise RuntimeError("tree walk runaway (cycle?)")
        if node <= THRESHOLD:
            if node == EOS:
                codes['EOS'] = (depth, code)
            else:
                codes[node >> 3] = (depth, code)
            continue
        c0 = struct.unpack_from(">H", tree, node + 4)[0]
        c1 = struct.unpack_from(">H", tree, node + 6)[0]
        stack.append((c0, depth + 1, (code << 1) | 0))
        stack.append((c1, depth + 1, (code << 1) | 1))
    return codes


class _BitWriter:
    def __init__(self, align_phase=0):
        self.bytes = bytearray()
        self.cur = 0          # current 32-bit word being filled
        self.mask = 0x80000000 >> (8 * (align_phase & 3))
        self.started = False

    def put(self, nbits, code):
        for i in range(nbits - 1, -1, -1):
            bit = (code >> i) & 1
            if bit:
                self.cur |= self.mask
            if self.mask == 1:
                self.bytes += struct.pack(">I", self.cur)
                self.cur = 0
                self.mask = 0x80000000
            else:
                self.mask >>= 1

    def finish(self):
        # flush the partial word if any bits were placed in it
        if self.mask != 0x80000000:
            self.bytes += struct.pack(">I", self.cur)
        return bytes(self.bytes)


def leaf_symbols(tree, root):
    """Set of symbol values (0..255) that are encodable leaves of `tree` (excl EOS)."""
    return {s for s in derive_codes(tree, root) if s != 'EOS'}


def snap_to_tree(pixels, tree, root, mode=2, bias=0, palette_rgb=None):
    """Return a delta-safe copy of `pixels` that encode() can compress with this fixed
    tree, nudging each unencodable byte to the in-tree value whose palette colour is
    closest to the target (so authored logo/menu art that introduces new filter-symbols
    still fits the original Huffman forest).

    The fixed tree only has leaves for the filter-SYMBOLS present in the original stream
    (mode 0: raw pixel values; mode 1: consecutive XOR deltas; mode 2: consecutive adds).
    Original/unedited pixels are already in-tree so they pass through unchanged; only the
    edited pixels (and the immediate boundary after them, whose delta references a changed
    neighbour) get snapped. `palette_rgb` = list of 256 (r,g,b); if None, snap by nearest
    symbol numerically. Processed per the codec's byte order with acc reset at the start
    (matching encode())."""
    leaves = leaf_symbols(tree, root)
    if palette_rgb is None:
        palette_rgb = [(v, v, v) for v in range(256)]

    def dist(a, b):
        ra, ga, ba = palette_rgb[a]; rb, gb, bb = palette_rgb[b]
        return (ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2

    out = bytearray(pixels)
    acc = 0
    for i in range(len(out)):
        t = out[i]
        if mode == 0:
            if t not in leaves:
                t = min((v for v in leaves), key=lambda v: dist(v, out[i]))
            out[i] = t; acc = t
        elif mode == 1:
            if (t ^ acc) not in leaves:
                t = min((acc ^ s for s in leaves), key=lambda p: dist(p, out[i]))
            out[i] = t; acc = t
        else:
            if ((t - acc) & 0xFF) not in leaves:
                t = min(((acc + s) & 0xFF for s in leaves), key=lambda p: dist(p, out[i]))
            out[i] = t; acc = t
    return bytes(out)


def encode(pixels, tree, root, mode=2, bias=0, src_align_phase=0):
    """Re-encode `pixels` (the decoded byte stream) with the SAME tree.

    Returns the compressed stream bytes (aligned words). The inverse filter and
    word/bias handling mirror decode(); pixels length should be a multiple of 4
    (VRAM sprites are). EOS is appended.
    """
    codes = derive_codes(tree, root)
    if 'EOS' not in codes:
        raise RuntimeError("tree has no EOS leaf")
    # inverse-filter: recover the symbol stream from output bytes
    # output word had `bias` added before store; undo it to get filtered bytes.
    assert len(pixels) % 4 == 0, "pixel length must be multiple of 4"
    syms = []
    acc = 0
    for i in range(0, len(pixels), 4):
        w = (struct.unpack_from(">I", pixels, i)[0] - bias) & 0xFFFFFFFF
        b = struct.pack(">I", w)
        for by in b:
            if mode == 0:
                sym = by
                acc = by
            elif mode == 1:
                sym = by ^ acc
                acc = by
            else:
                sym = (by - acc) & 0xFF
                acc = by
            syms.append(sym)
    bw = _BitWriter(src_align_phase)
    for s in syms:
        if s not in codes:
            raise RuntimeError(f"symbol {s} not in tree (cannot encode with this tree)")
        bw.put(*codes[s])
    bw.put(*codes['EOS'])
    return bw.finish()


if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser(description="decode/encode ST1 minigame graphics streams")
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("decode")
    d.add_argument("src"); d.add_argument("tree"); d.add_argument("out")
    d.add_argument("--root", type=lambda x: int(x, 0), required=True)
    d.add_argument("--mode", type=int, default=2)
    d.add_argument("--bias", type=lambda x: int(x, 0), default=0)
    d.add_argument("--phase", type=int, default=0)
    d.add_argument("--max", type=lambda x: int(x, 0), default=0)
    a = ap.parse_args()
    if a.cmd == "decode":
        src = open(a.src, "rb").read(); tree = open(a.tree, "rb").read()
        o = decode(src, tree, a.root, a.mode, a.bias, a.phase, a.max or None)
        open(a.out, "wb").write(o)
        print(f"decoded {len(o)} bytes -> {a.out}")
    else:
        ap.print_help()
