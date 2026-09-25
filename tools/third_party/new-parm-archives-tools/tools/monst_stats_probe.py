#!/usr/bin/env python3
"""
monst_stats_probe.py  —  Lane O5 (monster-book detail-page STAT PANEL) calibration harness.

STATUS: investigative tool, NOT a fold/ship tool. The stat-panel labels are baked pixels
inside a VDP2 RBG0 rotation bitmap that is (a) stored PIXEL-INTERLEAVED across two VDP2 VRAM
banks and (b) read through the rotation engine (per-line coefficient geometry). This tool
generates the marker-injection payloads and de-interleave renders used to crack that layout.
See docs/lanes/laneM2-stats-redraw.md for the full decoded state and the remaining blocker.

WHY THIS EXISTS: prior lanes (M, M2) tried to render the panel buffer statically and got only
noise, and could not explain it. This tool's `--gen` payloads, fed through the harness with
--inject-vram2, EMPIRICALLY reveal the buffer->screen mapping (the "static render = noise"
mystery was: the buffer is 2-bank pixel-interleaved, so any single-bank linear read shows a
half-density lattice). It is the calibration rig the next agent should extend to pin the exact
per-line rotation geometry, then locate + author the English label glyphs.

KEY DECODED FACTS (all empirically re-verified this session with inject-vram2 -> viewed PNG):
  * The panel BACKGROUND + the JP stat LABELS live in the RBG0 bitmap whose per-monster blit
    lands at VDP2 VRAM 0x10000 (bank A0) with a parallel copy at 0x30000 (bank A1). Filling
    0x10000 (both banks) turns the whole page uniform and ERASES the labels.
  * The stat NUMBERS (18/87/...), the two header lines (Name:/Habitat:), and the monster
    SPRITE are composited SEPARATELY (a different, linear layer) — they SURVIVE a full fill of
    the RBG0 buffer. => a labels-only edit to the RBG0 bitmap is isolated and safe.
  * A ruler written to ONE bank renders as a diamond/dash LATTICE (half the pixels). The SAME
    ruler written to BOTH banks (0x10000 AND 0x30000) renders coherently => 2-bank pixel
    interleave confirmed. See docs/lanes/pO5_ruler-*.png.
  * Vertical buffer->screen is monotonic (buffer top -> screen top) but maps into a screen
    SUB-RECTANGLE with per-line horizontal scaling (page perspective) => NOT a single affine;
    a rotation coefficient table is in play. This is the remaining read-map blocker.

USAGE
  # 1) generate a marker payload spanning both banks (writes identical data to A0 and A1):
  python3 tools/monst_stats_probe.py gen --kind fill    --out work/pO5/fill.bin
  python3 tools/monst_stats_probe.py gen --kind ruler-h --out work/pO5/ruler.bin
  python3 tools/monst_stats_probe.py gen --kind vbands  --out work/pO5/vbands.bin
  #    ...then inject at 0x10000 (payload already carries the A1 copy at +0x20000):
  H=tools/ymir-harness/build/jinloop-harness
  S=$(python3 tools/save_register.py path monster-detail-redoni)
  "$H" --bios "$BIOS" --disc "$CUE" --state "$S" --script work/pO5/nop.json \
       --inject-vram2 work/pO5/ruler.bin --inject-vram2-addr 0x10000 \
       --png-dir png/pO5/x --png-every 8 --out work/pO5/x.json
  #    then VIEW png/pO5/x/frame_final.png.

  # 2) de-interleave-render a VDP2 VRAM dump (experiment with layout params):
  python3 tools/monst_stats_probe.py render --vram output/pO5_dump/vdp2-vram.bin \
       --cram output/pO5_dump/cram-final.bin --stride 256 --mode colpar --out png/pO5/r.png

Repro state: monster-detail-redoni (JP disc D493EA66, already ON the detail page so the RBG0
buffer is resident and --inject-vram2 survives — no navigation re-blit to overwrite it).
On an rc build use pJ01-monster-book-list and drive C into a monster to reach the same panel.
"""
import argparse, struct, sys

# --- VDP2 VRAM geometry of the panel RBG0 bitmap (empirically established) ---
BANK_A0 = 0x10000          # per-monster blit dst (== LWRAM 0x24CFA0, byte-exact)
BANK_A1 = 0x30000          # parallel copy (2nd interleaved bank)
BANK_STEP = 0x20000        # A0->A1 offset (one VDP2 bank)
BLIT_LEN = 0xF4C0          # bytes copied per bank on detail entry (352*178 nominal)

# Bright-ish 8bpp palette indices for the live monster-detail CRAM (cram-final.bin from the
# monster-detail-redoni dump). Recompute with `render`-side --scan if the palette changes.
IDX_BRIGHT = 223   # near-white
IDX_RED    = 19
IDX_GREEN  = 58
IDX_BLUE   = 64


def _dup_both_banks(pat: bytes) -> bytes:
    """A payload that, injected at 0x10000, writes `pat` to A0 and an identical copy to A1
    (so every interleaved screen pixel receives the marker regardless of bank parity)."""
    assert len(pat) <= BLIT_LEN, "pattern longer than one bank blit"
    out = bytearray(pat)
    out += bytes(BANK_STEP - len(out))   # pad A0 up to the bank boundary
    out += pat                           # lands at 0x10000 + 0x20000 == 0x30000 (A1)
    return bytes(out)


def gen(kind: str, stride: int) -> bytes:
    N, S = BLIT_LEN, stride
    rows = N // S
    pat = bytearray(N)
    if kind == "fill":
        pat = bytearray([IDX_BRIGHT]) * N
    elif kind == "ruler-h":                       # bright band every 16 buffer rows
        for r in range(rows):
            if r % 16 < 3:
                for x in range(S):
                    pat[r * S + x] = IDX_BRIGHT
    elif kind == "ruler-v":                       # bright column every 32 buffer cols
        for r in range(rows):
            for x in range(S):
                if x % 32 < 2:
                    pat[r * S + x] = IDX_BRIGHT
    elif kind == "vbands":                         # 3 colored horizontal bands (R/G/B)
        def band(r0, r1, c):
            for r in range(r0, r1):
                for x in range(S):
                    o = r * S + x
                    if o < N:
                        pat[o] = c
        band(0, 16, IDX_RED); band(rows // 2 - 8, rows // 2 + 8, IDX_GREEN)
        band(rows - 20, rows - 4, IDX_BLUE)
    else:
        sys.exit(f"unknown --kind {kind}")
    return _dup_both_banks(bytes(pat))


def render(vram: str, cram: str, base: int, stride: int, mode: str, height: int, out: str):
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow required for render")
    d = open(vram, "rb").read()
    cr = open(cram, "rb").read()

    def cval(i):
        w = struct.unpack_from("<H", cr, (i & 0x7FF) * 2)[0]
        return ((w & 0x1F) << 3, (w >> 5 & 0x1F) << 3, (w >> 10 & 0x1F) << 3)

    a0, a1 = base, base + BANK_STEP
    W = stride * 2 if mode in ("colpar", "half") else stride
    img = Image.new("RGB", (W, height)); px = img.load()
    for y in range(height):
        for x in range(W):
            if mode == "linear":
                o = a0 + y * stride + x
            elif mode == "colpar":                 # even screen cols A0, odd A1
                o = (a0 if x % 2 == 0 else a1) + y * stride + x // 2
            elif mode == "half":                   # left half A0, right half A1
                o = (a0 + y * stride + x) if x < stride else (a1 + y * stride + (x - stride))
            else:
                sys.exit(f"unknown --mode {mode}")
            px[x, y] = cval(d[o] if o < len(d) else 0)
    img.save(out)
    print("wrote", out, f"({W}x{height}, base={base:#x} stride={stride} mode={mode})")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="generate a both-banks marker payload for --inject-vram2")
    g.add_argument("--kind", required=True,
                   choices=["fill", "ruler-h", "ruler-v", "vbands"])
    g.add_argument("--stride", type=int, default=352)
    g.add_argument("--out", required=True)
    r = sub.add_parser("render", help="de-interleave-render a VDP2 VRAM dump")
    r.add_argument("--vram", required=True); r.add_argument("--cram", required=True)
    r.add_argument("--base", type=lambda s: int(s, 0), default=BANK_A0)
    r.add_argument("--stride", type=int, default=256)
    r.add_argument("--mode", default="colpar", choices=["linear", "colpar", "half"])
    r.add_argument("--height", type=int, default=224)
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "gen":
        open(a.out, "wb").write(gen(a.kind, a.stride))
        print("wrote", a.out, "(both-bank payload; inject at 0x10000)")
    else:
        render(a.vram, a.cram, a.base, a.stride, a.mode, a.height, a.out)


if __name__ == "__main__":
    main()
