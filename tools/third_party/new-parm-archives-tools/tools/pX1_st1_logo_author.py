#!/usr/bin/env python3
"""Lane X1: author JP-art + EN-subtitle title slots for mg1-mg5 (ST1 games).

Per user picks (docs/reviews/rc47-user-answers.md): restore the ORIGINAL JP title
art and stamp the English name as a subtitle (embossed house 5x7 font, palette-
native core/outline indices, exactly Lane W6's approved column-c composites);
mg1 + mg5 get the subtitle MOVED LOWER than W6's draft.

Base file = work/mg_english_assets/<f> (the rc46 English asset: keeps the authored
English MENU slots); only the title slot is re-spliced with the composite.
JP pixels come verbatim from work/pW6_files/van/<f>.
"""
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mg_splice  # noqa: E402
import mg_text    # noqa: E402

VAN = ROOT / "work/pW6_files/van"
BASE = ROOT / "work/mg_english_assets"
OUT = ROOT / "work/pX1_author"
OUT.mkdir(exist_ok=True)

sys.path.insert(0, str(OUT))


def write_png(path, w, h, rgb, scale=2):
    import zlib
    sw, sh = w * scale, h * scale
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = bytearray()
    for y in range(sh):
        raw.append(0)
        row = rgb[(y // scale) * w * 3:(y // scale + 1) * w * 3]
        for x in range(sw):
            sxo = (x // scale) * 3
            raw += row[sxo:sxo + 3]
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", sw, sh, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    Path(path).write_bytes(png)


def pal_from_be(buf, off, n=256):
    out = []
    for i in range(n):
        o = off + i * 2
        v = struct.unpack(">H", buf[o:o + 2])[0] if o + 2 <= len(buf) else 0
        out.append(((v & 0x1f) << 3, ((v >> 5) & 0x1f) << 3, ((v >> 10) & 0x1f) << 3))
    return out


def to_rgb(pix, w, h, pal, bg=(24, 24, 32)):
    rgb = bytearray()
    for i in range(w * h):
        p = pix[i] if i < len(pix) else 0
        rgb += bytes(bg if p == 0 else pal[p])
    return rgb


def text_w(s, scale, gap=1):
    return len(s) * (5 + gap) * scale - gap * scale


def stamp(buf, W, H, text, scale, x0, y0, core, outline, gap=1):
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
                                for dx in (-1, 0, 1):
                                    for dy in (-1, 0, 1):
                                        xx, yy = X + dx, Y + dy
                                        if 0 <= xx < W and 0 <= yy < H:
                                            buf[yy * W + xx] = outline
                            elif 0 <= X < W and 0 <= Y < H:
                                buf[Y * W + X] = core
            cx += (5 + gap) * scale


def pick_indices(pix, pal):
    cnt = Counter(p for p in pix if p != 0)
    used = [i for i, c in cnt.items() if c >= 30]
    if not used:
        used = list(cnt)
    lum = {i: pal[i][0] * 3 + pal[i][1] * 6 + pal[i][2] for i in used}
    core = max(used, key=lambda i: lum[i])
    outline = min(used, key=lambda i: lum[i])
    return core, outline


def auto_band_y0(buf, W, H, total_h):
    """W6's band chooser: minimise art pixels under the band, prefer lower."""
    occ = [sum(1 for x in range(W) if buf[y * W + x]) for y in range(H)]
    best, best_score = None, None
    for y0 in range(0, H - total_h + 1):
        cover = sum(occ[y0:y0 + total_h])
        score = cover - y0 * 0.5
        if best_score is None or score < best_score:
            best, best_score = y0, score
    return best


def composite(jp_pix, W, H, pal, lines, scale, y0=None, clear_pad=None,
              force_idx=None):
    """clear_pad: None = stamp over the art (W6 draft look); an int = first clear
    a transparent box (text bbox + pad px) so the encode sheds art bytes and the
    subtitle sits on a clean window (index 0 = transparent -> game bg shows)."""
    buf = bytearray(jp_pix[:W * H].ljust(W * H, b"\x00"))
    core, outline = force_idx if force_idx else pick_indices(buf, pal)
    line_h = 7 * scale + 2 * scale
    total_h = line_h * len(lines) + 2
    if y0 is None:
        y0 = auto_band_y0(buf, W, H, total_h)
    if clear_pad is not None:
        wmax = max(text_w(ln, scale) for ln in lines)
        x_lo = max(0, (W - wmax) // 2 - clear_pad)
        x_hi = min(W, (W + wmax) // 2 + clear_pad)
        y_lo = max(0, y0 + 1 - clear_pad)
        y_hi = min(H, y0 + 1 + total_h - 2 + clear_pad)
        for y in range(y_lo, y_hi):
            for x in range(x_lo, x_hi):
                buf[y * W + x] = 0
    y = y0 + 1
    for ln in lines:
        x = (W - text_w(ln, scale)) // 2
        stamp(buf, W, H, ln, scale, x, y, core, outline)
        y += line_h
    return bytes(buf), y0, total_h, core, outline


# id, file, blob_src, slot_end, W, H, pal_off, lines, scale, y0 (None = W6 auto),
# pads (clear_pad ladder), idx ("art" = W6 pick from art; int chunk = pick from that
# chunk's mode-0 tree leaves so the stamp survives the fixed Huffman tree)
GAMES = [
    ("mg1_frogs", "RFROG.DAT", 0x34B48, 0x3846C, 296, 96, 0x34948,
     ["LEEN HATES FROGS!"], 2, 79,          # user: move LOWER than W6's top draft
     (None, 2, 4, 6, 8, 12), "art"),
    ("mg2_sue", "MGSUE.BIN", 0x258, 0x5418, 320, 136, 0x58,
     ["SUE! GANTZ'S BRIDE PLOT"], 2, 80,    # one line, low but inside chunk 1
     (None, 2, 4, 6, 8, 12), "art"),        # (chunk 2 is ~96% empty: any stamp there
                                            # costs ~2.5KB of long codes, cannot fit)
    ("mg3_feena", "FI_DT.DAT", 0x264, 0x32D8, 296, 88, 0x64,
     ["FEENA'S PANTIES"], 3, None,
     (None, 2, 4, 6, 8, 12), "art"),
    ("mg4_bonk", "OBONG.DAT", 0x23C, 0x3FC0, 296, 112, 0x3C,
     ["BONK-A-TRAY!"], 3, None,
     (None, 2, 4, 6, 8, 12), "art"),
    ("mg5_hotblooded", "BY100.DAT", 0x288, 0x4D68, 288, 120, 0x88,
     ["HOT-BLOODED SHOWDOWN!"], 2, 93,      # LOWER; fully inside chunk 1 (rows <=113)
     (2, 4, 6, 8, 12), "art"),              # forced window: text over the gold JP
                                            # glyphs is illegible without it
]


def main():
    only = sys.argv[1:] or None
    import mg_codec
    for iid, fname, src, end, W, H, paloff, lines, scale, y0, pads, idx in GAMES:
        if only and iid not in only:
            continue
        van = (VAN / fname).read_bytes()
        base = (BASE / fname).read_bytes()
        pal = pal_from_be(van, paloff)
        jp = mg_splice.slot_pixels(van, src)
        chunks = mg_splice.decode_slot(base, src)
        orig_len = sum(len(c["pixels"]) for c in chunks)
        force_idx = None
        if isinstance(idx, int):
            c = chunks[idx]
            lv = sorted(mg_codec.leaf_symbols(c["tree"], c["root"]))
            lv = [v for v in lv if v != 0]
            lum = {i: pal[i][0] * 3 + pal[i][1] * 6 + pal[i][2] for i in lv}
            force_idx = (max(lv, key=lambda i: lum[i]), min(lv, key=lambda i: lum[i]))
            print(f"{iid}: chunk{idx} mode-0 leaves -> core={force_idx[0]} "
                  f"rgb{pal[force_idx[0]]} outline={force_idx[1]} rgb{pal[force_idx[1]]}")
        new = mix = None
        for clear_pad in pads:
            mix, used_y0, th, core, outline = composite(
                jp[:W * H], W, H, pal, lines, scale, y0, clear_pad, force_idx)
            pix = mix[:orig_len].ljust(orig_len, b"\x00")
            edits, off = {}, 0
            for k, c in enumerate(chunks):
                n = len(c["pixels"])
                edits[k] = pix[off:off + n]
                off += n
            try:
                new = mg_splice.patch_slot(base, src, end, edits, snap=True,
                                           palette_rgb=pal)
                print(f"{iid}: lines={lines} scale={scale} band y={used_y0}.."
                      f"{used_y0+th} core={core} outline={outline} "
                      f"clear_pad={clear_pad} -> FITS")
                break
            except ValueError as e:
                print(f"{iid}: clear_pad={clear_pad} -> {e}")
                new = None
        if new is None:
            print(f"{iid}: FAILED to fit at any clear_pad")
            continue
        assert len(new) == len(base)
        got = mg_splice.slot_pixels(new, src)[:W * H]
        diff = sum(1 for a, b in zip(got, mix[:W * H]) if a != b)
        print(f"  spliced OK, decoded-vs-intended mismatch {diff}/{W*H} px "
              f"({100*diff/(W*H):.2f}% snap loss)")
        (OUT / fname).write_bytes(new)
        write_png(OUT / f"{iid}_new.png", W, H, to_rgb(got, W, H, pal), 2)
        print(f"  -> {OUT/fname}  preview {OUT}/{iid}_new.png")


if __name__ == "__main__":
    main()
