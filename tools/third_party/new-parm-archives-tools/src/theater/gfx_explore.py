#!/usr/bin/env python3
"""GFX agent (a): tooling for the theater drama-selection-screen graphics.

Two relevant graphics systems (see docs/theater-gfx.md for the full writeup):

1. GM3.STZ 'ST5' entries  — raw 8bpp paletted background images (NOT compressed).
   Reuses src/theater/adx.py (parse_idx/read_logical). READ-ONLY on the disc.
   GM3.IDX @ LBA 39126: 1024 slots, BE [tag:u16][start_sector:u16]; only the first
   ~369 are real (rest are 0xffff placeholders). Real = 124 ADX (dramas = idx 295-299,
   leave alone) + 245 ST5 graphics (magic "ST5\\0" = 53 54 35 00).
   ST5 = 64-byte header, payload @ 0x800, 1 byte/pixel palette indices 0-127 (a 128-color
   bank, so the high bit is never set). idx321 decodes cleanly as a 256x224 starfield,
   idx0 as 264x231 — they are raw, editable in place. But these are background plates for
   OTHER screens; the drama-SELECTION menu is drawn from VDP1 sprites (system 2), not these.

2. VDP1 sprites — the drama-selection screen (上映メニュー) itself. Drawn as pre-rendered
   8bpp sprite textures (like the minigame logos in docs/mgame-format.md). From savestate 0
   the VDP1 command list (parse with `vdp1`) is:
     cmd1/2  352x224 @(0,0)   tex 0x1000 / 0x14400  CMDCOLR 0x300  = curtain bg + menu frame
     cmd3    144x40  @(104,8) tex 0x299c0           CMDCOLR 0x500  = 上映メニュー header
     cmd5    152x48  @(16,54) tex 0x2ccc0           CMDCOLR 0x500  = ガンボ Gumbo plate (slot 1)
     cmd4/6-9 152x48          tex 0x2b040           CMDCOLR 0x500  = empty plate template
   8bpp, palette = VDP2 CRAM at word offset = CMDCOLR (0x500 -> cram byte 0xA00, BGR555 BE).
   `sprite` reproduces each exactly. BLOCKER: these textures are decompressed straight to
   VDP1 VRAM; the on-disc source is COMPRESSED (not found raw on disc) with the same uncracked
   custom codec the minigame lane flagged (docs/mgame-format.md) -> disc patch blocked.

Capture VRAM/CRAM with the harness (savestate 0 = the selection screen):
  tools/ymir-harness/build/jinloop-harness --bios "$GDM_BIOS" \\
    --disc input/Grandia*Digital*10M).cue --state .../0.savestate \\
    --out r.json --script idle.json --png-dir DIR --dump-wram DIR   (writes vdp1-vram.bin,
  vdp2-cram.bin). Then: gfx_explore.py vdp1 DIR/vdp1-vram.bin ; gfx_explore.py sprite ...
"""
from __future__ import annotations
import struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adx  # noqa: E402

GM3_LBA = 39128
IDX_LBA = 39126
DRAMA_IDX = list(range(295, 300))  # ADX, do NOT touch


# ---- GM3.STZ ST5 (raw paletted backgrounds) --------------------------------
def load_idx(f):
    idx = adx.read_logical(f, IDX_LBA, 4096)
    ents = [struct.unpack(">HH", idx[i:i + 4]) for i in range(0, len(idx), 4)]
    while ents and ents[-1] == (0, 0):
        ents.pop()
    return ents, adx.parse_idx(idx)


def real_indices(ents):
    return [i for i in range(len(ents)) if ents[i][0] != 0xffff]


def read_entry(f, sec):
    hdr = adx.read_logical(f, GM3_LBA + sec, 16)
    if hdr[:3] == b"ST5":
        return adx.read_logical(f, GM3_LBA + sec, struct.unpack(">I", hdr[12:16])[0])
    return hdr  # ADX: caller checks magic


def decode_st5(blob, width):
    """Raw 8bpp paletted -> HxW index array (palette applied separately)."""
    import numpy as np
    body = np.frombuffer(blob[0x800:], dtype=np.uint8)
    h = len(body) // width
    return body[:width * h].reshape(h, width).astype(np.int32)


# ---- VDP1 command list + sprite extraction (the selection screen) ----------
def parse_vdp1(vram: bytes):
    """Parse the VDP1 command table (0x20 B cmds) from a vram dump -> list of dicts."""
    def be16(o):
        return (vram[o] << 8) | vram[o + 1]

    def s16(v):
        return v - 65536 if v >= 32768 else v

    out, o = [], 0
    while o + 0x20 <= len(vram) and len(out) <= 256:
        ctrl = be16(o)
        if ctrl & 0x8000:
            break
        size = be16(o + 10)
        out.append({
            "type": ctrl & 0xf, "pmod": be16(o + 4), "cmdcolr": be16(o + 6),
            "tex": be16(o + 8) * 8, "w": ((size >> 8) & 0x3f) * 8, "h": size & 0xff,
            "x": s16(be16(o + 12)), "y": s16(be16(o + 14)),
        })
        o += 0x20
    return out


def render_sprite(vram, cram, tex, w, h, cmdcolr):
    """8bpp VDP1 sprite -> HxWx3 RGB (cram is BGR555 big-endian, word offset = cmdcolr)."""
    import numpy as np
    cr = np.frombuffer(cram, dtype=">u2").astype(np.int32)
    r = (cr & 31) << 3; g = ((cr >> 5) & 31) << 3; b = ((cr >> 10) & 31) << 3
    PAL = np.stack([r, g, b], -1).astype(np.uint8)
    px = np.frombuffer(vram[tex:tex + w * h], dtype=np.uint8).astype(np.int32)
    return PAL[(px + cmdcolr) % len(cr)].reshape(h, w, 3)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("table"); t.add_argument("track1")
    v = sub.add_parser("vdp1"); v.add_argument("vram")
    s = sub.add_parser("sprite")
    s.add_argument("vram"); s.add_argument("cram"); s.add_argument("out")
    s.add_argument("--tex", type=lambda x: int(x, 0), required=True)
    s.add_argument("--w", type=int, required=True); s.add_argument("--h", type=int, required=True)
    s.add_argument("--cmdcolr", type=lambda x: int(x, 0), default=0x500)
    a = ap.parse_args()

    if a.cmd == "table":
        with open(a.track1, "rb") as f:
            ents, abss = load_idx(f)
            for i in real_indices(ents):
                hdr = adx.read_logical(f, GM3_LBA + abss[i], 16)
                k = "STS" if hdr[:3] == b"ST5" else ("ADX" if hdr[0] == 0x80 else "?")
                sz = struct.unpack(">I", hdr[12:16])[0] if k == "STS" else "-"
                tail = "  <- drama" if i in DRAMA_IDX else ""
                print(f"{i:4d} {ents[i][0]:04x} {k} {sz}{tail}")
    elif a.cmd == "vdp1":
        for n, c in enumerate(parse_vdp1(Path(a.vram).read_bytes())):
            print(f"cmd{n}: type{c['type']} tex{c['tex']:#08x} {c['w']}x{c['h']} "
                  f"pos=({c['x']},{c['y']}) cmdcolr{c['cmdcolr']:#06x} pmod{c['pmod']:#06x}")
    elif a.cmd == "sprite":
        from PIL import Image
        img = render_sprite(Path(a.vram).read_bytes(), Path(a.cram).read_bytes(),
                            a.tex, a.w, a.h, a.cmdcolr)
        Image.fromarray(img).save(a.out)
        print(f"{a.w}x{a.h} tex{a.tex:#x} -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
