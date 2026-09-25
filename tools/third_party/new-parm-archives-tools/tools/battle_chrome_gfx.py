#!/usr/bin/env python3
"""battle_chrome_gfx.py — battle-menu CHROME atlas (VDP1 sprite) RE toolkit + oracle.

Lane O4/O1 (== the same wall): the in-battle chrome labels (技 "Skill", 魔法LV
headers, しゅうとくスキル, defend bar 防御実行/防御/回避, strategy 作戦, item 道具,
ring labels) plus the party name-plates and Combo/Critical/Defend centre popups are
drawn as VDP1 sprites from a *compressed* per-character archive set
(/BATLE/P{1,2,3}{WIN,MG0-3,DEF,ITM,A_H,A_Q}.BIN + /BATLE/K_SYS.BIN). The decoded
glyph atlas lives in VDP1 VRAM 0x40000-0x48000.

STATUS: **codec NOT cracked -> no disc fold exists yet.** This module is the RE
scaffold + the *validation oracle* that a future codec-crack lane plugs into:

  * `archdump  P1WIN.BIN`      — parse+print the 3-entry archive header/sub-tables.
  * `atlas VDP1VRAM.bin OUT`   — carve the ground-truth 0x40000-0x48000 atlas to a PNG
                                 montage (so authored English can be pixel-matched to
                                 the JP cell geometry).
  * `glyph "SK" OUT.bin --w 16 --h 16`
                               — author an English label as a 4bpp VDP1 texture using
                                 the mg_text house font, ready for --inject-vram1.
  * `oracle-cmd 0x473a0 SK.bin`
                               — print the exact jinloop-harness --inject-vram1 line
                                 that renders the authored texture in place of the JP
                                 sprite (the accepted "inject at the resident VDP addr"
                                 validation route, same as Lane TILEFONT surface (a)).

The atlas is CACHED in VDP1 VRAM (decoded once at submenu-OPEN, NOT re-decoded per
frame — proven: a marker written to 0x473a0 survives 8 idle frames AND a menu-close).
So the eventual disc fix (patch the compressed archive) takes effect on the NEXT
submenu-open from a fresh session, exactly like the name-plate atlas (surface (c)).

See docs/lanes/laneTILEFONT.md surface (b)/(c) for the full decoded recipe + the two
remaining sub-walls: (i) the archive decompressor is a *separate* routine (NOT the
mgame ST1 mg_codec — byte-tested: mgame tree parser yields garbage on these streams),
(ii) width/geometry: 技 is one 16x16 cell, kanji->"Skill" needs a wider sprite ->
VDP1 command-list geometry edit (except 魔法LV which is baked into a 72x24 box that
already fits "Magic Lv1" as a texture-only redraw once the codec is cracked).
"""
import argparse
import os
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import mg_text  # house 5x7 font


# ---------------------------------------------------------------------------
# Archive header parsing (P*.BIN 3-entry archive, K_SYS.BIN pointer table).

def parse_archive(data):
    """Parse a P*.BIN 3-entry archive. Returns dict with entry list + entry0 sub-table."""
    n_words = struct.unpack_from(">I", data, 0)[0]
    # header = list of entry offsets; first word is the offset of entry0 (0xc typ.)
    ents = list(struct.unpack_from(">3I", data, 0))
    e0 = ents[0]
    sub = list(struct.unpack_from(">8I", data, e0))       # 8 sub-offsets (rel to e0)
    dims = struct.unpack_from(">I", data, e0 + 0x20)[0]    # e.g. 0x00080010
    sig = struct.unpack_from(">I", data, e0 + 0x30)[0]     # 0x00f2006e signature
    return {
        "entries": ents,
        "e0": e0,
        "sub_offsets": sub,
        "sub_abs": [e0 + s for s in sub],
        "dims_word": dims,
        "signature": sig,
    }


def cmd_archdump(args):
    data = open(args.file, "rb").read()
    a = parse_archive(data)
    print(f"file {args.file} ({len(data)} bytes)")
    print(f"  entries (abs offsets): {[hex(x) for x in a['entries']]}")
    print(f"  entry0 @ {a['e0']:#x}")
    print(f"  sub-offsets (rel e0):  {[hex(x) for x in a['sub_offsets']]}")
    print(f"  sub-offsets (abs):     {[hex(x) for x in a['sub_abs']]}")
    print(f"  dims word  @ e0+0x20:  {a['dims_word']:#010x}"
          f"  ({a['dims_word'] >> 16}x{a['dims_word'] & 0xffff})")
    print(f"  signature  @ e0+0x30:  {a['signature']:#010x}")
    # bytes at the first data sub-block (candidate compressed / tree-def stream)
    off = a["sub_abs"][1]
    print(f"  data sub-block @ {off:#x}: {data[off:off+32].hex()}")


# ---------------------------------------------------------------------------
# 4bpp VDP1 texture authoring (English glyph via house font).

def author_4bpp(text, w, h, ink=0xF, scale=1, x0=1, y0=None):
    """Render `text` into a w x h 4bpp VDP1 texture (2px/byte, row-major, w must be
    even). ink = palette index for strokes (0 = transparent). Returns bytes of length
    w*h//2. Uses the mg_text 5x7 block font. Auto-centres vertically if y0 is None."""
    assert w % 2 == 0, "width must be even for 4bpp packing"
    gh = 7 * scale
    if y0 is None:
        y0 = max(0, (h - gh) // 2)
    # mg_text.render gives an 8bpp buffer; we threshold it to ink/0 and re-pack 4bpp.
    idx = mg_text.render(text, w, h, val=ink, hi=ink, scale=scale, x0=x0, y0=y0)
    out = bytearray(w * h // 2)
    for y in range(h):
        for x in range(w):
            v = idx[y * w + x] & 0xF
            bi = (y * w + x) // 2
            if (x & 1) == 0:
                out[bi] = (out[bi] & 0x0F) | (v << 4)
            else:
                out[bi] = (out[bi] & 0xF0) | v
    return bytes(out)


def cmd_glyph(args):
    b = author_4bpp(args.text, args.w, args.h, ink=args.ink, scale=args.scale)
    open(args.out, "wb").write(b)
    print(f"authored '{args.text}' -> {args.out} ({len(b)} bytes, {args.w}x{args.h} 4bpp, ink={args.ink:#x})")


# ---------------------------------------------------------------------------
# Ground-truth atlas carving (from a VDP1 VRAM dump).

def cmd_atlas(args):
    import mg_gfx  # write_png / palette
    vram = open(args.vram, "rb").read()
    base, end = 0x40000, 0x48000
    region = vram[base:end]
    # Render as a 4bpp linear image, 256 px wide, gray ramp palette.
    W = 256
    rows = (len(region) * 2) // W
    rgb = bytearray(W * rows * 3)
    for i, byte in enumerate(region):
        for half in range(2):
            v = (byte >> 4) if half == 0 else (byte & 0xF)
            px = i * 2 + half
            g = v * 17
            rgb[px * 3] = g
            rgb[px * 3 + 1] = g
            rgb[px * 3 + 2] = g
    mg_gfx.write_png(args.out, W, rows, bytes(rgb))
    nz = sum(1 for b in region if b)
    print(f"atlas 0x40000-0x48000: {nz} nonzero bytes -> {args.out} ({W}x{rows})")


# ---------------------------------------------------------------------------
def cmd_cmdlist(args):
    """Parse a VDP1 command table (from a --dump-wram vdp1-vram.bin) and print each
    sprite's SRCA/size/position. Filters to the atlas window 0x40000-0x48000 unless
    --all. This is the sprite GEOMETRY the width problem must respect (kanji->English
    needs a wider CMDSIZE + repositioned CMDXA, generated from the archive metadata)."""
    v = open(args.vram, "rb").read()
    off = 0
    for _ in range(512):
        ctrl = struct.unpack_from(">H", v, off)[0]
        if ctrl & 0x8000:
            break
        ctype = ctrl & 0xF
        srca = struct.unpack_from(">H", v, off + 8)[0] * 8
        size = struct.unpack_from(">H", v, off + 0xA)[0]
        xa = struct.unpack_from(">h", v, off + 0xC)[0]
        ya = struct.unpack_from(">h", v, off + 0xE)[0]
        w = ((size >> 8) & 0x3F) * 8
        h = size & 0xFF
        show = args.all or (0x40000 <= srca < 0x48000)
        if show and ctype in (0, 1, 2, 3):
            print(f"  cmd@{off:#06x} type={ctype} SRCA={srca:#07x} "
                  f"size={w}x{h} pos=({xa},{ya})")
        off += 0x20


def cmd_oracle_cmd(args):
    vaddr = int(args.vaddr, 0)
    print("# validation oracle: inject the authored texture at the resident VDP1 VRAM")
    print("# address, then VIEW the PNG (English renders in place of the JP sprite).")
    print(f'H=tools/ymir-harness/build/jinloop-harness')
    print(f'BIOS=".../Sega Saturn BIOS v1.01 (JAP).bin"')
    print(f'S=$(python3 tools/save_register.py path pBANNER-skillmenu-open)')
    print(f'$H --bios "$BIOS" --disc output/rc_27/Grandia-DM-patched.cue --state "$S" \\')
    print(f'   --out /tmp/o.json --max-frames 4 \\')
    print(f'   --inject-vram1 {args.tex} --inject-vram1-addr {vaddr:#x} \\')
    print(f'   --png-dir OUT --png-every 2')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("archdump"); p.add_argument("file"); p.set_defaults(fn=cmd_archdump)

    p = sub.add_parser("glyph")
    p.add_argument("text"); p.add_argument("out")
    p.add_argument("--w", type=int, default=16); p.add_argument("--h", type=int, default=16)
    p.add_argument("--ink", type=lambda x: int(x, 0), default=0xF)
    p.add_argument("--scale", type=int, default=1)
    p.set_defaults(fn=cmd_glyph)

    p = sub.add_parser("atlas")
    p.add_argument("vram"); p.add_argument("out"); p.set_defaults(fn=cmd_atlas)

    p = sub.add_parser("cmdlist")
    p.add_argument("vram"); p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_cmdlist)

    p = sub.add_parser("oracle-cmd")
    p.add_argument("vaddr"); p.add_argument("tex"); p.set_defaults(fn=cmd_oracle_cmd)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
