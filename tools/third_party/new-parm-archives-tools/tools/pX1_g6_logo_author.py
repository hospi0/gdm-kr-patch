#!/usr/bin/env python3
"""Lane X1, game 6 (Big-Eater Grandia Cup): JP kanji art restored + English subtitle,
re-encoded for the resident field-sprite codec (0x0601A716) into HYABG.BIN @0x29E9C.

The vanilla stream fills its 9724-byte slot EXACTLY, so mg_field_codec's fixed 5-bit
code cannot carry the JP art. This authoring uses a real canonical Huffman (the same
code space the decoder's 256-entry LUT rebuilds: 17 syms, max len 8, Kraft sum == 256,
canonical fill by (len DESC, index ASC)) + the absolute zero-run events of stream A.

Composite: JP kanji rows kept verbatim; the separable JP sub-line row
(〜グランディア杯〜, rows 83..103) is cleared and replaced with the English name.
"""
import struct
import sys
from collections import Counter
from heapq import heappush, heappop
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mg_text  # noqa: E402

W, H = 256, 104
SLOT = 0x25FC
OFF = 0x29E9C
WHITE = 0x01                  # (248,248,240)
SHADOW = 0xF7                 # (80,80,80) dark grey — encodes 74B cheaper than 0xFF


# ------------------------------------------------------------- length-limited Huffman
def code_lengths(freq, maxlen=8):
    """Optimal-ish lengths, every sym gets a code, Kraft sum forced to exactly 256."""
    syms = list(range(len(freq)))
    # plain Huffman
    heap = []
    for s in syms:
        heappush(heap, (max(freq[s], 1), s, (s,)))
    n = len(heap)
    lens = [0] * len(freq)
    if n == 1:
        lens[0] = 1
    else:
        depth = {s: 0 for s in syms}
        while len(heap) > 1:
            f1, _, g1 = heappop(heap)
            f2, t, g2 = heappop(heap)
            for s in g1 + g2:
                depth[s] += 1
            heappush(heap, (f1 + f2, t, g1 + g2))
        lens = [depth[s] for s in syms]
    # clamp to maxlen
    lens = [min(l, maxlen) for l in lens]
    kraft = sum(1 << (maxlen - l) for l in lens)
    # over-subscribed: lengthen cheapest (lowest-freq) short codes
    order = sorted(syms, key=lambda s: freq[s])
    while kraft > (1 << maxlen):
        for s in order:
            if lens[s] < maxlen:
                kraft -= 1 << (maxlen - lens[s])
                lens[s] += 1
                kraft += 1 << (maxlen - lens[s])
                break
        else:
            raise ValueError("cannot satisfy Kraft")
    # under-subscribed: shorten most frequent syms while it still fits exactly
    order = sorted(syms, key=lambda s: -freq[s])
    changed = True
    while kraft < (1 << maxlen) and changed:
        changed = False
        for s in order:
            if lens[s] > 1:
                gain = (1 << (maxlen - lens[s] + 1)) - (1 << (maxlen - lens[s]))
                if kraft + gain <= (1 << maxlen):
                    lens[s] -= 1
                    kraft += gain
                    changed = True
    # final exactness: bump longest-code low-freq syms shorter one step of 1 unit
    while kraft < (1 << maxlen):
        # add 1 unit by shortening an len==maxlen symbol to maxlen-1 adds 1 unit
        for s in sorted(syms, key=lambda s: freq[s]):
            if lens[s] == maxlen:
                lens[s] -= 1
                kraft += 1
                break
        else:
            raise ValueError("cannot complete Kraft")
    assert sum(1 << (maxlen - l) for l in lens) == (1 << maxlen)
    return lens


def canonical_codes(lens, maxlen=8):
    """LUT fill order: (len DESC, index ASC); code = top `len` bits of range start."""
    pos = 0
    codes = {}
    for s in sorted(range(len(lens)), key=lambda s: (-lens[s], s)):
        l = lens[s]
        codes[s] = (pos >> (maxlen - l), l)
        pos += 1 << (maxlen - l)
    assert pos == (1 << maxlen)
    return codes


# ------------------------------------------------------------- encoder
def encode_huff(img: bytes, run_threshold=4) -> bytes:
    nibs = []
    for b in img:
        nibs.append(b >> 4)
        nibs.append(b & 15)
    N = len(nibs)
    toks = []           # ('lit', nib) | ('run', z)
    i = 0
    while i < N:
        if nibs[i] == 0:
            j = i
            while j < N and nibs[j] == 0:
                j += 1
            z = j - i
            if z >= run_threshold:
                while z > 0:
                    part = min(z, 0xFFFF)
                    toks.append(('run', part))
                    z -= part
                i = j
                continue
        toks.append(('lit', nibs[i]))
        i += 1
    toks.append(('run', 0))    # EOS

    freq = [0] * 17
    for t, v in toks:
        if t == 'lit':
            freq[v] += 1
        else:
            freq[16] += 1
    lens = code_lengths(freq)
    codes = canonical_codes(lens)

    # stream A: run events — relative forms when the delta to the previous run
    # is small (1-2 nibbles), absolute otherwise. EOS = absolute byte 0.
    an = []
    prev_run = 0
    for t, z in toks:
        if t != 'run':
            continue
        d = z - prev_run
        if z == 0:                      # EOS must be the absolute-0 form
            an += [14, 0, 0]
        elif -6 <= d <= 6:
            an += [d + 6]
        elif -14 <= d <= -7:
            an += [13, d + 14]
        elif 7 <= d <= 14:
            an += [13, d + 1]
        elif z <= 255:
            an += [14, (z >> 4) & 15, z & 15]
        else:
            an += [15, (z >> 12) & 15, (z >> 8) & 15, (z >> 4) & 15, z & 15]
        prev_run = z
    while len(an) % 4:
        an.append(0)
    sa = bytearray()
    for k in range(0, len(an), 2):
        sa.append((an[k] << 4) | an[k + 1])
    L = len(sa)
    if L > 0x1FFF:
        raise ValueError(f"stream A too long ({L})")

    hdr = 0x2000 | L    # mode 0 (mov), literal-first
    lt = [lens[i] for i in range(17)] + [0]
    lensb = bytes([(lt[2 * i] << 4) | lt[2 * i + 1] for i in range(9)])

    sb = bytearray()
    acc = cnt = 0
    for t, v in toks:
        c, l = codes[v if t == 'lit' else 16]
        for k in range(l - 1, -1, -1):
            acc = (acc << 1) | ((c >> k) & 1)
            cnt += 1
            if cnt == 8:
                sb.append(acc)
                acc = cnt = 0
    if cnt:
        sb.append(acc << (8 - cnt))
    sb += b"\0" * 8

    return struct.pack(">H", hdr) + bytes(sa) + lensb + bytes(sb)


# ------------------------------------------------------------- composite
def text_w(s, scale, gap=1):
    return len(s) * (5 + gap) * scale - gap * scale


def stamp(buf, text, scale, x0, y0, core, outline, gap=1):
    for pas in (0, 1):
        cx = x0
        for ch in text.upper():
            g = mg_text.FONT.get(ch, mg_text.FONT[' '])
            for ry, row in enumerate(g):
                for rx, c in enumerate(row):
                    if c != '1':
                        continue
                    for sy in range(scale):
                        for sx in range(scale):
                            X = cx + rx * scale + sx
                            Y = y0 + ry * scale + sy
                            if pas == 0:
                                # bottom-right drop shadow: a full outline does not
                                # fit the 9724B slot (vanilla packs it to the byte)
                                for dx, dy in ((1, 0), (0, 1), (1, 1)):
                                    xx, yy = X + dx, Y + dy
                                    if 0 <= xx < W and 0 <= yy < H:
                                        buf[yy * W + xx] = outline
                            elif 0 <= X < W and 0 <= Y < H:
                                buf[Y * W + X] = core
            cx += (5 + gap) * scale


def main():
    jp = bytearray(Path(ROOT / "work/pX1_author/g6_jp.pix").read_bytes())
    # clear the separable JP sub-line rows (〜グランディア杯〜) ...
    for y in range(83, H):
        for x in range(W):
            jp[y * W + x] = 0
    # ... including its topmost glyph tips at rows 79-82 (x windows chosen to spare
    # the kanji stroke descenders at x33-35 / x84-95 / x121-146)
    for y in range(79, 83):
        for x in list(range(50, 80)) + list(range(150, 230)):
            jp[y * W + x] = 0
    line = "BIG-EATER GRANDIA CUP"
    tw = text_w(line, 2)
    stamp(jp, line, 2, (W - tw) // 2, 86, WHITE, SHADOW)
    img = bytes(jp)
    Path(ROOT / "work/pX1_author/g6_new.pix").write_bytes(img)

    best = None
    for thr in (3, 4, 5, 6, 8):
        blob = encode_huff(img, thr)
        print(f"run_threshold={thr}: {len(blob)}B (budget {SLOT})")
        if best is None or len(blob) < len(best):
            best = blob
    if len(best) > SLOT:
        raise SystemExit(f"TOO BIG: {len(best)} > {SLOT}")
    blob = best + b"\0" * (SLOT - len(best))

    base = bytearray((ROOT / "work/mg_english_assets/HYABG.BIN").read_bytes())
    base[OFF:OFF + SLOT] = blob
    out = ROOT / "work/pX1_author/HYABG.BIN"
    out.write_bytes(bytes(base))
    print(f"wrote {out} (size preserved: {len(base) == 231852})")


if __name__ == "__main__":
    main()
