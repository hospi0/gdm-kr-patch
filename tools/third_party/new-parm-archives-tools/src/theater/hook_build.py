#!/usr/bin/env python3
"""Build the theater caption hook into a test disc.

Patches IP.BIN (the BIOS-loaded initial program, raw on the disc system area LBA 0-15) to detour the
per-chunk CD-stream call and blit English captions into the VDP1 framebuffer over the "SOUND ONLY"
screen. See docs/theater-hook.md for the full RE.

Pipeline:
  1. render an 8x16 ASCII font (Monaco) -> 1bpp glyph table (0x20..0x7E)
  2. assemble the SH-2 hook (src/theater/hook_sh2asm.py) at the IP free-gap address
  3. lay out [hook code | font | (phase B) caption table] in the IP gap; redirect the jsr literal
  4. copy the disc, write the patched IP sectors, emit cue

  python3 src/theater/hook_build.py --out output/hook_001 --phase a   # fixed-string smoke test
  python3 src/theater/hook_build.py --out output/hook_002 --phase b   # drama-1 caption table

NEVER commit output/ (gitignored). Stale EDC/ECC in the patched sectors is fine for the emulator
(YMIR); regenerate for a real disc (TODO).
"""
from __future__ import annotations
import argparse, json, shutil, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_sh2asm  # noqa
import hook_caption_table as hct  # noqa

RAW, USER, SYNC = 2352, 2048, 16
IP_BASE = 0x06002000               # IP.BIN loads here
# Free gap zero in BOTH the IP file AND WRAM-at-playback. The 0x060084xx range is completely
# clobbered during the attract mode "planet" scene. The 261-byte gap at 0x060074B8 (file 0x54B8)
# is proven stable across cold boot and the entire attract mode sequence.
GAP_FILE = 0x54B8
GAP_LEN = 261
HOOK_ADDR = IP_BASE + GAP_FILE     # resident hook entry = 0x060074B8
JSR_LIT_FILE = 0x2394              # literal loaded into r3 then `jsr @r3` (per-chunk path)
ORIG_FN = 0x06009B32               # original function at that literal (we tail-call it)
FAD_VAR = 0x06002008               # live CD playback FAD
VDP1_FB = 0x25C80000               # VDP1 framebuffer (512w, 16bpp)
FB_W = 512
COLOR = 0x050F                     # "SOUND ONLY" on-pixel value (renders white)
CAP_X, CAP_Y = 96, 150             # caption top-left in FB px (below SOUND ONLY, in black area)
LINE_H = 17                        # px per caption row

T1 = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M)/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
T2 = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M)/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 2).bin"
CUE = ('FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
       'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')

FONT_LO, FONT_HI = 0x20, 0x7E
NGLYPH = FONT_HI - FONT_LO + 1

# --- Gap-based placement (the cold-boot/curtain-freeze fix) -------------------------------------
# The game clobbers most IP gaps during boot or attract mode. The 261-byte gap at 0x060074B8
# is stable across all modes. We place the 92-byte installer there. The vhook + 8x8 split font 
# go in separate IP gaps that are zero during the drama (verified). The caption table follows 
# the installer in the stable gap.
# ------------------------------------------------------------------------------------------------
# The 1234 B gap at 0x06008922 is clobbered during boot, but stays zero during the drama.
# It holds vhook+font. The table sits after the installer at 0x06007514.
GAP_VHOOK  = 0x06008922   # 883 B stable run: vhook code (~258 B)
GAP_FONT1  = 0x06008A40   # 8x8 glyphs 0x20..0x3F (256 B)
GAP_FONT2  = 0x06008B40   # 8x8 glyphs 0x40..0x5F (256 B)  -> ends 0x06008C40 (< 0x06008C95)
GAP_TABLE  = 0x06007514   # file 0x5514 (169 B remaining): caption table (~4 lines)s)
CAP_Y8 = 168              # 8x8 caption top row
LINE_H8 = 10              # px per 8x8 caption line


def render_font8(lo, hi) -> bytes:
    """8x8 1bpp font, MSB=leftmost, glyphs [lo,hi). 8 bytes/glyph."""
    from PIL import Image, ImageFont, ImageDraw
    fnt = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 8)
    out = bytearray()
    for code in range(lo, hi):
        img = Image.new("L", (8, 8), 0); d = ImageDraw.Draw(img)
        d.text((0, -1), chr(code), fill=255, font=fnt)
        px = img.load()
        for y in range(8):
            bits = 0
            for x in range(8):
                if px[x, y] > 90: bits |= (0x80 >> x)
            out.append(bits)
    return bytes(out)


def render_font() -> bytes:
    """8x16, 1bpp, MSB=leftmost. ASCII 0x20..0x7E. 16 bytes/glyph."""
    from PIL import Image, ImageFont, ImageDraw
    fnt = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", 16)
    out = bytearray()
    for code in range(FONT_LO, FONT_HI + 1):
        img = Image.new("L", (8, 16), 0)
        d = ImageDraw.Draw(img)
        d.text((-1, -2), chr(code), fill=255, font=fnt)
        px = img.load()
        for y in range(16):
            bits = 0
            for x in range(8):
                if px[x, y] > 110:
                    bits |= (0x80 >> x)
            out.append(bits)
    return bytes(out)


def font_preview(font: bytes, text: str) -> str:
    """ASCII-art preview of a string rendered from the baked font (sanity check)."""
    rows = [""] * 16
    for ch in text:
        c = ord(ch)
        if not (FONT_LO <= c <= FONT_HI):
            c = ord('?')
        g = font[(c - FONT_LO) * 16:(c - FONT_LO) * 16 + 16]
        for y in range(16):
            rows[y] += "".join('#' if g[y] & (0x80 >> x) else ' ' for x in range(8))
    return "\n".join(rows)


# ---------------------------------------------------------------------------------------
# SH-2 hook source. Common register plan:
#   r4 = preserved (input to ORIG_FN). r3 set to ORIG_FN before the tail jmp.
#   save/restore r5..r11. scratch r0,r1,r2,r3.
#   r8=font base, r9=color, r10=string ptr, r11=glyph FB top-left.

def fb_addr(x, y):
    return VDP1_FB + (y * FB_W + x) * 2


# NOTE: SH-2 `cmp/eq #imm` only compares R0, so loop counters use `dt Rn` (decrement+test).
# Row FB pointer is advanced by the stride each row (no multiply). r6=stride(1024), r7=row ptr.
GLYPH_BLIT = """
char_loop:
  mov.b @r10,r0
  extu.b r0,r0
  cmp/eq #0,r0
  bt hdone
  add #-32,r0
  shll2 r0
  shll2 r0
  mov r8,r1
  add r0,r1
  mov #1,r6
  shll8 r6
  shll2 r6
  mov r11,r7
  mov #16,r2
row_loop:
  mov.b @r1,r0
  extu.b r0,r0
  mov r7,r3
  mov #8,r5
col_loop:
  tst #0x80,r0
  bt cskip
  mov.w r9,@r3
cskip:
  add #2,r3
  shll r0
  dt r5
  bf col_loop
  add #1,r1
  add r6,r7
  dt r2
  bf row_loop
  add #16,r11
  add #1,r10
  bra char_loop
  nop
hdone:
"""

# Save EVERY register the wrapped CD-stream function (0x06009b32) may read as input. r4 is its
# explicit arg (never touched). r3 is reloaded with ORIG_FN at the end (its entry value). r0/r1/r2
# ARE read by the function (proven: a blit that clobbered them stalled the stream), so save them too.
PROLOGUE = """
  mov.l r0,@-r15
  mov.l r1,@-r15
  mov.l r2,@-r15
  mov.l r5,@-r15
  mov.l r6,@-r15
  mov.l r7,@-r15
  mov.l r8,@-r15
  mov.l r9,@-r15
  mov.l r10,@-r15
  mov.l r11,@-r15
"""

EPILOGUE = """
  mov.l @r15+,r11
  mov.l @r15+,r10
  mov.l @r15+,r9
  mov.l @r15+,r8
  mov.l @r15+,r7
  mov.l @r15+,r6
  mov.l @r15+,r5
  mov.l @r15+,r2
  mov.l @r15+,r1
  mov.l @r15+,r0
  mov.l @(D_ORIG,PC),r3
  jmp @r3
  nop
"""


def build_phase_a(test_str: str):
    """Hook that unconditionally blits a fixed string. Returns (code_bytes, font_bytes, layout)."""
    font = render_font()
    src = PROLOGUE + """
  mov.l @(D_FONT,PC),r8
  mov.w @(D_COLOR,PC),r9
  mov.l @(D_STR,PC),r10
  mov.l @(D_FB,PC),r11
""" + GLYPH_BLIT + EPILOGUE + """
.align 4
D_ORIG:  .long %d
D_FONT:  .long FONT
D_STR:   .long STR
D_FB:    .long %d
D_COLOR: .word %d
.align 4
STR:
""" % (ORIG_FN, fb_addr(CAP_X, CAP_Y), COLOR)
    # append string bytes + font as data with labels
    src += "  .byte " + ",".join(str(b) for b in test_str.encode("ascii")) + ",0\n"
    src += ".align 4\nFONT:\n"
    src += "  .byte " + ",".join(str(b) for b in font) + "\n"
    code = hook_sh2asm.assemble(src, HOOK_ADDR)
    return code, font


CAP_Y0 = 150        # first caption row (FB y)
LINE_STRIDE = 18 * 512 * 2   # bytes per caption line in FB (18px tall * 512w * 2bytes)
DRAMA1_FAD_LO = 0x01BFAE
DRAMA1_FAD_HI = 0x01CBA5

# Single-glyph blitter: char in r0, top-left FB addr in r11, font r8, color r9.
# Scratch r0,r1,r2,r3,r5,r6,r7 (does NOT touch r10..r14 = outer state).
GLYPH_ONE = """
  add #-32,r0
  shll2 r0
  shll2 r0
  mov r8,r1
  add r0,r1
  mov #1,r6
  shll8 r6
  shll2 r6
  mov r11,r7
  mov #16,r2
%(p)s_grow:
  mov.b @r1,r0
  extu.b r0,r0
  mov r7,r3
  mov #8,r5
%(p)s_gcol:
  tst #0x80,r0
  bt %(p)s_gskip
  mov.w r9,@r3
%(p)s_gskip:
  add #2,r3
  shll r0
  dt r5
  bf %(p)s_gcol
  add #1,r1
  add r6,r7
  dt r2
  bf %(p)s_grow
"""


def render_font_upper() -> bytes:
    """Uppercase-only 8x16 font, ASCII 0x20..0x5F (64 glyphs) to save space."""
    from PIL import Image, ImageFont, ImageDraw
    fnt = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", 16)
    out = bytearray()
    for code in range(0x20, 0x60):
        img = Image.new("L", (8, 16), 0); d = ImageDraw.Draw(img)
        d.text((-1, -2), chr(code), fill=255, font=fnt)
        px = img.load()
        for y in range(16):
            bits = 0
            for x in range(8):
                if px[x, y] > 110: bits |= (0x80 >> x)
            out.append(bits)
    return bytes(out)


def bake_drama1_table(budget: int, wrap=34, fad_offset: int = 0):
    """Compact drama-1 table: per record start_rel(u16) end_rel(u16) len(u8) text(upper, \\n=newline).
    Terminator start_rel=0xFFFF. Fits within `budget` bytes (drops trailing lines that overflow).

    `fad_offset` (sectors) shifts every line's [start,end) FAD later to compensate for the CD clock's
    read-ahead lead: the live FAD var 0x06002008 runs ~3-7 sectors AHEAD of the audible position
    (measured against emulator audio, session-13; larger early in the drama, ~5 sectors mid-drama), so
    without it captions appear ~0.4 s before the voice. Residual error is bounded by the ~2 s clock
    staircase. R=12.116 sectors/s is confirmed correct (steady-state), so this is an offset not a rate."""
    cap = json.loads((Path(__file__).resolve().parent / "captions/drama1.json").read_text())
    R = 12.116
    recs = bytearray()
    used = 0
    n = 0
    for ln in cap["lines"]:
        s = round(ln["start"] * R) + fad_offset
        e = round(ln["end"] * R) + fad_offset
        if e <= s: e = s + 1
        if s > 0xFFFF or e > 0xFFFF: continue
        txt = hct.transliterate(ln["en"]).upper()
        spk = (ln.get("spk") or "").strip()
        if spk and spk.lower() != "title":
            txt = hct.transliterate(spk).upper() + ": " + txt
        rows = wrap_text(txt, wrap)
        body = "\n".join(rows).encode("ascii")[:0xFFFE]
        if len(body) & 1:                      # pad body to even length (space) so each record,
            body += b"\x20"                     # with its 6-byte header, stays 2-byte aligned
        rec = struct.pack(">HHH", s, e, len(body)) + body
        if used + len(rec) + 2 > budget:        # +2 for terminator
            break
        recs += rec; used += len(rec); n += 1
    recs += struct.pack(">H", 0xFFFF)
    return bytes(recs), n


def wrap_text(text, width):
    out, cur = [], ""
    for w in text.split():
        if not cur: cur = w
        elif len(cur) + 1 + len(w) <= width: cur += " " + w
        else: out.append(cur); cur = w
    if cur: out.append(cur)
    return out[:3]  # max 3 on-screen rows


VHOOK8_SRC = """
vhook:
  mov.l r0,@-r15
  mov.l r1,@-r15
  mov.l r2,@-r15
  mov.l r3,@-r15
  mov.l r5,@-r15
  mov.l r6,@-r15
  mov.l r7,@-r15
  mov.l r8,@-r15
  mov.l r9,@-r15
  mov.l r10,@-r15
  mov.l r11,@-r15
  mov.l r12,@-r15
  mov.l r13,@-r15
  mov.l r14,@-r15
  mov.l @(V_FADVAR,PC),r0
  mov.l @r0,r1
  mov.l @(V_FADLO,PC),r2
  cmp/hs r2,r1
  bf vchain
  mov.l @(V_FADHI,PC),r3
  cmp/hs r3,r1
  bt vchain
  sub r2,r1
  mov.l @(V_TABLE,PC),r13
vscan:
  mov.w @r13+,r0
  extu.w r0,r0
  mov.l @(V_FFFF,PC),r2
  cmp/eq r2,r0
  bt vchain
  mov.w @r13+,r2
  extu.w r2,r2
  mov.w @r13+,r14
  extu.w r14,r14
  cmp/hs r0,r1
  bf vnext
  cmp/hs r2,r1
  bf vfound
vnext:
  add r14,r13
  bra vscan
  nop
vfound:
  mov.w @(V_COLOR,PC),r9
  mov.l @(V_FB,PC),r12
  mov r12,r11
vcloop:
  mov.b @r13+,r0
  extu.b r0,r0
  mov #10,r2
  cmp/eq r2,r0
  bt vnewline
  add #-32,r0
  mov r0,r2
  mov #32,r1
  cmp/hs r1,r2
  bt vf2
  shll2 r0
  shll r0
  mov.l @(V_FONT1,PC),r1
  add r0,r1
  bra vfr
  nop
vf2:
  add #-32,r0
  shll2 r0
  shll r0
  mov.l @(V_FONT2,PC),r1
  add r0,r1
vfr:
  mov #1,r6
  shll8 r6
  shll2 r6
  mov r11,r7
  mov #8,r2
vgrow:
  mov.b @r1,r0
  extu.b r0,r0
  mov r7,r3
  mov #8,r5
vgcol:
  tst #0x80,r0
  bt vgskip
  mov.w r9,@r3
vgskip:
  add #2,r3
  shll r0
  dt r5
  bf vgcol
  add #1,r1
  add r6,r7
  dt r2
  bf vgrow
  add #16,r11
  bra vcnext
  nop
vnewline:
  mov.l @(V_STRIDE,PC),r2
  add r2,r12
  mov r12,r11
vcnext:
  dt r14
  bf vcloop
vchain:
  mov.l @r15+,r14
  mov.l @r15+,r13
  mov.l @r15+,r12
  mov.l @r15+,r11
  mov.l @r15+,r10
  mov.l @r15+,r9
  mov.l @r15+,r8
  mov.l @r15+,r7
  mov.l @r15+,r6
  mov.l @r15+,r5
  mov.l @r15+,r3
  mov.l @r15+,r2
  mov.l @r15+,r1
  mov.l @(V_HANDLER,PC),r0
  jmp @r0
  mov.l @r15+,r0
.align 4
V_FADVAR:  .long %d
V_FADLO:   .long %d
V_FADHI:   .long %d
V_FFFF:    .long 0x0000FFFF
V_FB:      .long %d
V_STRIDE:  .long %d
V_HANDLER: .long 0x06000846
V_FONT1:   .long %d
V_FONT2:   .long %d
V_TABLE:   .long %d
V_COLOR:   .word %d
"""

INSTALLER8_SRC = """
inst:
  mov.l r0,@-r15
  mov.l r1,@-r15
  mov.l r2,@-r15
  mov.l @(I_FADVAR,PC),r0
  mov.l @r0,r1
  mov.l @(I_DLO,PC),r2
  cmp/hs r2,r1
  bf inst_done
  mov.l @(I_DHI,PC),r2
  cmp/hs r2,r1
  bt inst_done
  mov.l @(I_VEC,PC),r0
  mov.l @r0,r1
  mov.l @(I_HOOK,PC),r2
  cmp/eq r2,r1
  bt inst_done
  mov.l @(I_CHAIN,PC),r0
  mov.l r1,@r0
  mov.l @(I_VEC,PC),r0
  mov.l @(I_HOOK,PC),r2
  mov.l r2,@r0
inst_done:
  mov.l @r15+,r2
  mov.l @r15+,r1
  mov.l @r15+,r0
  mov.l @(I_ORIG,PC),r3
  jmp @r3
  nop
.align 4
I_FADVAR: .long %d
I_DLO:    .long %d
I_DHI:    .long %d
I_VEC:    .long 0x06000104
I_HOOK:   .long %d
I_CHAIN:  .long %d
I_ORIG:   .long %d
"""


BANNER_ADDR = 0x06007514   # cold-boot-proven-stable 261 B gap (file 0x54b8) for the banner vhook
BANNER_TEXT = "** ENGLISH **"


def render_string8(text) -> bytes:
    """Pre-render `text` to a flat run of 8x8 1bpp glyphs (8 B each, in order, repeats included)."""
    from PIL import Image, ImageFont, ImageDraw
    fnt = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 8)
    out = bytearray()
    for ch in text:
        img = Image.new("L", (8, 8), 0); d = ImageDraw.Draw(img)
        d.text((0, -1), ch, fill=255, font=fnt)
        px = img.load()
        for y in range(8):
            bits = 0
            for x in range(8):
                if px[x, y] > 90: bits |= (0x80 >> x)
            out.append(bits)
    return bytes(out)


BANNER_SRC = """
vbanner:
  mov.l r0,@-r15
  mov.l r1,@-r15
  mov.l r2,@-r15
  mov.l r3,@-r15
  mov.l r5,@-r15
  mov.l r6,@-r15
  mov.l r7,@-r15
  mov.l r9,@-r15
  mov.l r11,@-r15
  mov.l r13,@-r15
  mov.l r14,@-r15
  mov.l @(B_FADVAR,PC),r0
  mov.l @r0,r1
  mov.l @(B_DLO,PC),r2
  cmp/hs r2,r1
  bf bchain
  mov.l @(B_DHI,PC),r2
  cmp/hs r2,r1
  bt bchain
  mov.l @(B_GLYPHS,PC),r13
  mov.l @(B_FB,PC),r11
  mov.w @(B_COLOR,PC),r9
  mov.l @(B_COUNT,PC),r14
bcloop:
  mov r13,r1
  mov #1,r6
  shll8 r6
  shll2 r6
  mov r11,r7
  mov #8,r2
brow:
  mov.b @r1,r0
  extu.b r0,r0
  mov r7,r3
  mov #8,r5
bcol:
  tst #0x80,r0
  bt bskip
  mov.w r9,@r3
bskip:
  add #2,r3
  shll r0
  dt r5
  bf bcol
  add #1,r1
  add r6,r7
  dt r2
  bf brow
  add #8,r13
  add #16,r11
  dt r14
  bf bcloop
bchain:
  mov.l @r15+,r14
  mov.l @r15+,r13
  mov.l @r15+,r11
  mov.l @r15+,r9
  mov.l @r15+,r7
  mov.l @r15+,r6
  mov.l @r15+,r5
  mov.l @r15+,r3
  mov.l @r15+,r2
  mov.l @r15+,r1
  mov.l @(B_HANDLER,PC),r0
  jmp @r0
  mov.l @r15+,r0
.align 4
B_FADVAR:  .long %d
B_DLO:     .long %d
B_DHI:     .long %d
B_FB:      .long %d
B_HANDLER: .long 0x06000846
B_GLYPHS:  .long GLYPHS
B_COUNT:   .long %d
B_COLOR:   .word %d
.align 4
GLYPHS:
"""


def build_phase_b():
    """SAFE (non-frozen) baseline disc. CAPTIONS ARE BLOCKED: only the 96 B prefix 0x06008434 is
    cold-boot-proven-stable resident IP space, which is not enough for even the vhook (260 B) — let
    alone the font+table. Every other IP gap is transiently clobbered by the game between boot and the
    drama (e.g. 0x060074b8 survived one cold-boot, was clobbered the next). So the vhook/font/table
    CANNOT be resident; synced captions require a CD-load of a relocatable blob into a big free region
    (LWRAM 0x002d6f3c etc.) — see docs/theater-hook.md "CAPTIONS BLOCKED".

    To leave a non-frozen disc, this ships only a **transparent installer**: the 0x2394 CD-stream
    literal is redirected to a proven-safe trampoline in the stable prefix that just tail-calls the
    original CD fn. It installs NO VBlank hook, so nothing can freeze and dramas play (uncaptioned),
    exactly like vanilla. The table-driven + banner builders below are kept for the CD-load follow-up.
    Returns {file_off: bytes}."""
    # proven-safe trampoline (session-1 verified): preserve the regs the CD fn reads, tail-call it.
    tramp_src = """
inst:
  mov.l @(T_ORIG,PC),r3
  jmp @r3
  nop
.align 4
T_ORIG: .long %d
""" % ORIG_FN
    tramp = hook_sh2asm.assemble(tramp_src, HOOK_ADDR)
    print(f"phase B (SAFE/uncaptioned): transparent trampoline {len(tramp)}B @ {HOOK_ADDR:#x} "
          f"(captions blocked -> CD-load required, see docs)")
    return {0x2394: struct.pack(">I", HOOK_ADDR), GAP_FILE: tramp}


def build_phase_b_banner():
    """(NOT shipped — 0x060074b8 proved unreliable) self-contained banner over SOUND ONLY."""
    glyphs = render_string8(BANNER_TEXT)
    src = (BANNER_SRC % (FAD_VAR, DRAMA1_FAD_LO, DRAMA1_FAD_HI, fb_addr(CAP_X, CAP_Y8),
                         len(BANNER_TEXT), COLOR)) + "  .byte " + ",".join(str(b) for b in glyphs) + "\n"
    asm = hook_sh2asm.Asm()
    vbanner = asm.assemble2(src, BANNER_ADDR)
    inst_src = INSTALLER8_SRC % (FAD_VAR, DRAMA1_FAD_LO, DRAMA1_FAD_HI, BANNER_ADDR,
                                 asm.labels["B_HANDLER"], ORIG_FN)
    installer = hook_sh2asm.assemble(inst_src, HOOK_ADDR)
    return {0x2394: struct.pack(">I", HOOK_ADDR), GAP_FILE: installer, BANNER_ADDR - IP_BASE: vbanner}


def build_phase_b_tabledriven():
    """Table-driven synced-caption hook (NOT shippable yet: needs a CD-load to place font+table in a
    big free region — see docs/theater-hook.md). Kept for the CD-load follow-up. Returns {off: bytes}."""
    font1 = render_font8(0x20, 0x40)   # 256 B
    font2 = render_font8(0x40, 0x60)   # 256 B
    # vhook code at GAP_VHOOK; needs the V_HANDLER slot address for the installer's dynamic chain
    vhook_src = VHOOK8_SRC % (FAD_VAR, DRAMA1_FAD_LO, DRAMA1_FAD_HI, fb_addr(CAP_X, CAP_Y8),
                              LINE_H8 * FB_W * 2, GAP_FONT1, GAP_FONT2, GAP_TABLE, COLOR)
    asm = hook_sh2asm.Asm()
    vhook = asm.assemble2(vhook_src, GAP_VHOOK)
    v_handler_addr = asm.labels["V_HANDLER"]
    inst_src = INSTALLER8_SRC % (FAD_VAR, DRAMA1_FAD_LO, DRAMA1_FAD_HI, GAP_VHOOK, v_handler_addr, ORIG_FN)
    installer = hook_sh2asm.assemble(inst_src, HOOK_ADDR)
    table, nlines = bake_drama1_table(261)
    pieces = {
        0x2394:           struct.pack(">I", HOOK_ADDR),   # jsr literal -> installer
        GAP_FILE:         installer,                       # 0x54B8 (stable gap)
        GAP_VHOOK - IP_BASE: vhook,                        # 0x5188
        GAP_FONT1 - IP_BASE: font1,                        # 0x5298
        GAP_FONT2 - IP_BASE: font2,                        # 0x53a8
        GAP_TABLE - IP_BASE: table,                        # 0x54b8
    }
    # fit checks
    fits = (len(installer) <= 0x60 and len(vhook) <= 262 and len(table) <= 261)
    print(f"phase B (gap): installer={len(installer)}B vhook={len(vhook)}B font={len(font1)+len(font2)}B "
          f"table={len(table)}B ({nlines} lines) fits={fits}")
    if not fits:
        raise SystemExit("a piece overflows its stable gap")
    return pieces


def patch_ip(t1out: Path, pieces: dict):
    """Write each hook piece to its IP file offset (sector-aware) + the jsr literal.
    pieces: {file_offset: bytes}. Gaps are tiny + stable across the drama (see GAP_* notes)."""
    with open(t1out, "r+b") as f:
        for off, data in sorted(pieces.items()):
            for i, b in enumerate(data):
                sector, within = divmod(off + i, USER)
                f.seek(sector * RAW + SYNC + within)
                f.write(bytes([b]))
    return HOOK_ADDR


def make_disc(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    t1out = out / "Track1.bin"
    shutil.copyfile(T1, t1out)
    shutil.copyfile(T2, out / "Track2.bin")
    (out / "Grandia-DM-patched.cue").write_text(CUE)
    return t1out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--phase", choices=["a", "b"], default="a")
    ap.add_argument("--test-str", default="ENGLISH CAPTIONS OK")
    ap.add_argument("--preview", action="store_true", help="just preview font, no disc")
    ap.add_argument("--emit-inject", action="store_true",
                    help="write hook_code.bin + literal.bin for harness --inject testing (no 455MB copy)")
    a = ap.parse_args()

    if a.phase == "a":
        code, _ = build_phase_a(a.test_str)
        pieces = {GAP_FILE: code, 0x2394: struct.pack(">I", HOOK_ADDR)}
    else:
        pieces = build_phase_b()
    if a.preview:
        return 0

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.emit_inject:
        # manifest of pieces for the harness --inject-manifest (each line: ADDR path)
        man = []
        for off, data in sorted(pieces.items()):
            fn = out / f"piece_{off:06x}.bin"
            fn.write_bytes(data)
            man.append(f"{IP_BASE + off:#010x} {fn}")
        (out / "inject_manifest.txt").write_text("\n".join(man) + "\n")
        print(f"inject manifest -> {out}/inject_manifest.txt ({len(pieces)} pieces)")
        return 0
    t1 = make_disc(out)
    hook = patch_ip(t1, pieces)
    print(f"patched IP: installer@{hook:#x}, vhook@{GAP_VHOOK:#x}, font@{GAP_FONT1:#x}/{GAP_FONT2:#x}, "
          f"table@{GAP_TABLE:#x}; jsr literal {JSR_LIT_FILE:#x} -> {hook:#x}")
    print(f"disc -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
