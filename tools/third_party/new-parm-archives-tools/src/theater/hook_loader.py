#!/usr/bin/env python3
"""Relocatable theater-caption BLOB baker + two-stage room-entry loader.

This is the session-7 build of the "CD-load" architecture from docs/theater-hook.md. The hard
constraint (sessions 4-6): there is NO reliable resident IP space for the vhook+font+table
(~986 B) — only the 96 B prefix at IP 0x06008434 survives boot. Fix: ship a single relocatable
BLOB and load it into a big free LWRAM region (0x002d6f3c, proven zero boot->drama), then point
VBlank vector 0x41 (0x06000104) at the loaded vhook.

The blob is `[ stage2-init | vhook | font1 | font2 | drama-table ]`, assembled to RUN at
BLOB_BASE = 0x002d6f3c.  Everything inside it is PC-relative / absolute-to-BLOB_BASE so it is
position-correct once copied there.

  * stage2-init: captures the live VBlank vector 0x41 into the vhook's chain slot, then writes the
    vhook entry into vector 0x41. (Idempotent; called once by the stage-1 loader after the CD read.)
  * vhook: the VBlank handler (reused from hook_build.VHOOK8_SRC) — FAD-gated 8x8 caption blitter
    that chains to the captured original handler.

`bake_blob()` returns (blob_bytes, meta) where meta has the absolute entry addresses. The blob is
verified offline (assembles, internal pointers land inside the blob, fits one sector).

See hook_build.build_phase_c() for the disc build (stage-1 CD-read loader + on-disc blob sector).
"""
from __future__ import annotations
import struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_sh2asm          # noqa
import hook_build as HB      # noqa: reuse font + table bakers + the vhook source

BLOB_BASE = 0x002d6f3c       # LWRAM dest: zero at vanilla game-screen AND during drama (verified)
VEC41 = 0x06000104           # VBlank vector 0x41 (VBR=0x06000000)
ORIG_VBLANK = 0x06000846     # the engine's persistent VBlank handler (resident HWRAM; never re-inited
                             # per scene — verified door==theater, session 11). Safe uninstall target.

# --- session-11: option-(b) piggyback on E804.MDT (the ONLY file loaded to RAM at theater entry) ---
# E804.MDT (FAD 0x7B17, 83 sectors) is copied RAW + LINEAR to LWRAM 0x00280000 on theater-room entry
# (verified: file+0 -> 0x280000, file+0x800 -> 0x280800, file+0x10000 -> 0x290000). So a blob placed at
# E804 file offset F lands at LWRAM 0x280000+F every entry. E804 is SHARED with the dialogue lane, so
# this requires coordination (see docs/theater-hook.md session 11 + docs/MERGE-coordination.md).
E804_LOAD = 0x00280000       # fixed LWRAM staging address of the current field MDT (E804 at theater)
BLOB_MAGIC = 0x47444d42      # "GDMB" — bootstrap room-loaded gate (first 4 bytes of the piggyback blob)

# stage-2 init: runs in LWRAM. Captures *(VEC41) into the vhook's V_HANDLER chain slot, installs the
# vhook entry into *(VEC41). r4 = vhook entry, r5 = &V_HANDLER slot. Returns (rts).
STAGE2_SRC = """
s2init:
  mov.l @(S_VEC,PC),r0
  mov.l @r0,r1            ; r1 = current vector 0x41 (original VBlank handler)
  mov.l @(S_HSLOT,PC),r2  ; r2 = &vhook.V_HANDLER
  mov.l @r2,r3
  mov.l @(S_VHOOK,PC),r6  ; r6 = vhook entry
  cmp/eq r6,r1            ; already installed?  (idempotent)
  bt s2done
  mov.l r1,@r2           ; vhook.V_HANDLER = original handler
  mov.l r6,@r0           ; vector 0x41 = vhook entry
s2done:
  rts
  nop
.align 4
S_VEC:    .long %d
S_HSLOT:  .long %d
S_VHOOK:  .long %d
"""


# caption geometry: 8x8 glyphs. The visible NTSC frame is ~320 px wide; the curtains sit at the far
# edges. Keep text inside ~x[40..300] so 30 cols (240 px) fit with margins.
CAP_X = 40
WRAP = 30

# --- session-13: 2x-scaled blit (user asked for a BIGGER font). We keep the 512 B 8x8 Menlo font
# (glyphs fixed upstream, commit 1107cef) but the vhook draws every font pixel as a 2x2 block -> 16x16
# on screen, double the height, within the same font budget (leaves room for the caption table in the
# 1516 B E804 free run). Game-font reuse was ruled out: the 8x16 dialogue font is NOT resident in a
# blittable form during a drama (no dialogue on the SOUND-ONLY screen; confirmed by scanning WRAM/VRAM).
CAP_X16 = 48          # 16px glyphs; 16-col field spans x[48..304) — measured (lane I): the stage
                      # black area is x[46..303] and "SOUND ONLY" (the engine's own centered
                      # element) is centered at x=175.5, so the field center 48+128=176 matches.
                      # Rows are centered WITHIN the field by baked leading spaces
                      # (hook_caption_table, center=True) — was 32/left-anchored, which the user
                      # read as glued to the left curtain. FB x maps 1:1 to the 352-px screen.
CAP_Y16 = 142         # top row: below "SOUND ONLY" (ends y119); 4 rows end y214 (lane E; was 150/3 rows)
WRAP16 = 16           # cols at 16px wide (16*16=256 px)
LINE_H16 = 18         # on-screen rows are 16 px tall + 2 px gap
MAX_ROWS16 = 4        # rows per caption page (hook_caption_table.bake_vhook_table time-splits longer)


def render_font8_from16(lo: int, hi: int) -> bytes:
    """Clean 8x8 font derived from the 8x16 (Monaco-16) render by OR-ing row pairs. Better glyph
    fidelity than a direct 8pt raster — notably it DISTINGUISHES M / N / W (which collapse at 8pt) —
    so the 2x-scaled blit reads correctly. 8 bytes/glyph, glyphs [lo,hi)."""
    f16 = HB.render_font()   # 0x20..0x7E, 16 B/glyph, clean
    out = bytearray()
    for c in range(lo, hi):
        g = f16[(c - 0x20) * 16:(c - 0x20) * 16 + 16]
        for y in range(8):
            out.append(g[2 * y] | g[2 * y + 1])
    return bytes(out)

# 2x-scaling VHOOK: identical to hook_build.VHOOK8_SRC (FAD gate + table scan + char dispatch + chain)
# except the per-glyph blit draws each 8x8 font pixel as a 2x2 FB block (r8=subrow, r10=row bits held
# across the 2 output rows), and advances the pen by 16 px/glyph.
#
# Lane E addition — CLEAR-ON-CHANGE: the VDP1 FB caption band is NOT reliably erased by the game
# between records (observed live: overlapping text mid-drama, leftover rows after short records — a
# latent bug of the 14-record hook that full 5-drama coverage exposed). The vhook now keeps the
# last-drawn record's body pointer in V_LAST (a RAM slot inside the blob) and:
#   * record CHANGED  -> clear the whole caption band (CLR_ROWS x 256 px at V_FB), then draw;
#   * record found, same as last -> just redraw (per-frame redraw beats the buffer swap);
#   * NO record but V_LAST set (hole between lines mid-drama) -> clear band once, V_LAST=0;
#   * FAD gate fails (not in a drama) -> chain untouched — NEVER clear outside the drama screen
#     (the band belongs to the game there; stale V_LAST just triggers one clear at next install).
# PR is saved/restored (the clear uses bsr; the VBlank'd code's PR must survive).
# Extra %-args vs VHOOK8_SRC: V_LASTP (abs addr of V_LAST, two-pass) and CLR_ROWS.
VHOOK16_SRC = """
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
  sts.l pr,@-r15
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
  bt vnone
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
vnone:
  mov.l @(V_LASTP,PC),r5
  mov.l @r5,r0
  tst r0,r0
  bt vchain
  mov #0,r0
  mov.l r0,@r5
  bsr vclear
  nop
  bra vchain
  nop
vfound:
  mov.l @(V_LASTP,PC),r5
  mov.l @r5,r0
  cmp/eq r13,r0
  bt vdraw
  mov.l r13,@r5
  bsr vclear
  nop
vdraw:
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
  mov.b @r1,r10
  extu.b r10,r10
  mov #2,r8
vgsub:
  mov r10,r0
  mov r7,r3
  mov #8,r5
vgcol:
  tst #0x80,r0
  bt vgskip
  mov.w r9,@r3
  add #2,r3
  mov.w r9,@r3
  add #2,r3
  bra vgcont
  nop
vgskip:
  add #4,r3
vgcont:
  shll r0
  dt r5
  bf vgcol
  add r6,r7
  dt r8
  bf vgsub
  add #1,r1
  dt r2
  bf vgrow
  add #32,r11
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
  lds.l @r15+,pr
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
vclear:
  mov.l @(V_FB,PC),r3
  mov #0,r0
  mov #1,r8
  shll8 r8
  shll2 r8
  mov #%d,r6
vclrrow:
  mov r3,r7
  mov #64,r2
vclrpx:
  mov.w r0,@r7
  add #2,r7
  mov.w r0,@r7
  add #2,r7
  mov.w r0,@r7
  add #2,r7
  mov.w r0,@r7
  add #2,r7
  dt r2
  bf vclrpx
  add r8,r3
  dt r6
  bf vclrrow
  rts
  nop
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
V_LASTP:   .long %d
V_LAST:    .long 0
V_COLOR:   .word %d
"""


FAD_LEAD_SECTORS = 5   # subtract the CD read-ahead lead so captions land on the voice (session-13)


def bake_blob(drama_table_budget: int = 0x600, blob_base: int = BLOB_BASE,
              magic: int | None = None, scale2x: bool = False, fad_offset: int = 0,
              all_dramas: bool = False):
    """Assemble the relocatable blob to run at `blob_base`. Returns (blob, meta).

    If `magic` is given, the blob is prefixed with a 4-byte big-endian magic word and all code/data is
    assembled to run at blob_base+4 (so stage2 entry = blob_base+4). The room-entry bootstrap then gates
    on *(blob_base)==magic to confirm the piggyback file (E804.MDT) is loaded before installing the
    vhook (and to detect that it has been UNloaded on theater exit). See build_room_bootstrap().

    all_dramas=True (lane E): the table covers ALL FIVE dramas full-length
    (hook_caption_table.bake_vhook_table, ~15.5 KB) and the vhook's FAD gate spans drama-1 start ..
    drama-5 end (one table relative to drama-1's FAD; max rel 0x49E5 fits the u16 records — no asm
    change). `drama_table_budget` is ignored; the caller must give the blob a big enough home
    (the grown E804 CPU-window free tail; see rc_integrate)."""
    asm = hook_sh2asm.Asm
    base = blob_base + (4 if magic is not None else 0)

    # vhook variant + caption geometry: 2x-scaled 16x16 (session-13) or the original 8x8.
    VSRC = VHOOK16_SRC if scale2x else HB.VHOOK8_SRC
    capx = CAP_X16 if scale2x else HB.CAP_X
    capy = CAP_Y16 if scale2x else HB.CAP_Y8
    lineh = LINE_H16 if scale2x else HB.LINE_H8
    wrap = WRAP16 if scale2x else WRAP

    # --- caption table + the vhook's FAD gate range ---
    if all_dramas:
        import hook_caption_table as hct
        table, tmeta = hct.bake_vhook_table(wrap_w=wrap, max_rows=MAX_ROWS16,
                                            fad_offset=fad_offset)
        nlines = tmeta["records"]
        fad_lo, fad_hi = tmeta["fad_lo"], tmeta["fad_hi"]
    else:
        table, nlines = HB.bake_drama1_table(drama_table_budget, wrap=wrap, fad_offset=fad_offset)
        tmeta = None
        fad_lo, fad_hi = HB.DRAMA1_FAD_LO, HB.DRAMA1_FAD_HI

    if scale2x:
        # VHOOK16 signature: clr_rows, fadvar, lo, hi, fb, stride, font1, font2, table, v_lastp, color
        vargs = lambda f1, f2, t, vl=0: (MAX_ROWS16 * LINE_H16, HB.FAD_VAR, fad_lo, fad_hi,
                                         HB.fb_addr(capx, capy), lineh * HB.FB_W * 2,
                                         f1, f2, t, vl, HB.COLOR)
    else:
        vargs = lambda f1, f2, t, vl=0: (HB.FAD_VAR, fad_lo, fad_hi,
                                         HB.fb_addr(capx, capy), lineh * HB.FB_W * 2,
                                         f1, f2, t, HB.COLOR)

    # --- pass 1: size the stage2 + vhook so we can place font/table after them ---
    # We must know the vhook's V_HANDLER slot address (inside the vhook literal pool) for stage2,
    # and the vhook needs the font/table addresses. So: assemble vhook once at a provisional base to
    # learn its length + the V_HANDLER offset, then lay out the blob and assemble for real.
    fontbake = render_font8_from16 if scale2x else HB.render_font8
    font1 = fontbake(0x20, 0x40)          # 256 B  (0x20..0x3F)
    font2 = fontbake(0x40, 0x60)          # 256 B  (0x40..0x5F)

    # provisional vhook to measure length + V_HANDLER offset (addresses don't affect size)
    prov = asm()
    prov.assemble2(VSRC % vargs(0, 0, 0), 0)
    # stage2 length (addresses don't affect size)
    prov_s2 = asm()
    s2_len = len(prov_s2.assemble2(STAGE2_SRC % (0, 0, 0), 0))
    s2_len = (s2_len + 3) & ~3            # vhook starts 4-aligned

    VHOOK_ADDR = base + s2_len
    vhook_len_prov = len(prov.assemble2(VSRC % vargs(0, 0, 0), VHOOK_ADDR))
    v_handler_slot = prov.labels["V_HANDLER"]
    v_last_slot = prov.labels.get("V_LAST", 0)     # VHOOK16 only (clear-on-change state)

    font1_addr = VHOOK_ADDR + ((vhook_len_prov + 3) & ~3)
    font2_addr = font1_addr + len(font1)
    table_addr = font2_addr + len(font2)

    # --- pass 2: assemble for real with final addresses ---
    s2_asm = asm()
    stage2 = s2_asm.assemble2(STAGE2_SRC % (VEC41, v_handler_slot, VHOOK_ADDR), base)
    stage2 = stage2 + b"\x00" * (s2_len - len(stage2))   # pad to 4-align vhook

    v_asm = asm()
    vhook = v_asm.assemble2(VSRC % vargs(font1_addr, font2_addr, table_addr, v_last_slot),
                            VHOOK_ADDR)
    assert v_asm.labels["V_HANDLER"] == v_handler_slot, "V_HANDLER moved between passes"
    if v_last_slot:
        assert v_asm.labels["V_LAST"] == v_last_slot, "V_LAST moved between passes"
    assert len(vhook) == vhook_len_prov, "vhook length changed between passes"

    pad = b"\x00" * (((len(vhook) + 3) & ~3) - len(vhook))
    blob = stage2 + vhook + pad + font1 + font2 + table
    if magic is not None:
        blob = struct.pack(">I", magic) + blob   # 4-byte room-loaded gate; stage2 entry = base = blob_base+4

    meta = dict(blob_base=blob_base, magic=magic, s2_entry=base, vhook_entry=VHOOK_ADDR,
                v_handler_slot=v_handler_slot, v_last_slot=v_last_slot, font1=font1_addr,
                font2=font2_addr, table=table_addr, table_lines=nlines, blob_len=len(blob),
                fad_lo=fad_lo, fad_hi=fad_hi, all_dramas=all_dramas)
    if tmeta:
        meta["table_meta"] = tmeta

    # --- self-verify: internal pointers must land inside the blob ---
    end = blob_base + len(blob)
    for nm in ("vhook_entry", "font1", "font2", "table"):
        assert blob_base <= meta[nm] < end, f"{nm} {meta[nm]:#x} outside blob"
    assert v_handler_slot % 4 == 0 and blob_base <= v_handler_slot < end
    return blob, meta


# --- session-12: the room-entry bootstrap (lives in the cold-boot-stable 96 B IP prefix at file
# 0x6434 / resident 0x06008434, reached via the 0x2394 CD-jsr redirect). It REPLACES the infeasible
# option-(a) CD-read entirely: the blob is already resident (piggybacked in E804.MDT, loaded to LWRAM
# 0x280000 at theater entry), so the bootstrap only INSTALLS / UNINSTALLS the vhook.
#
# It runs at the per-chunk CD-stream site (stream_chunk @0x06004256): the requested FAD of THIS chunk
# was just written to the FAD var 0x06002008 (at 0x0600427E) BEFORE the 0x2394 jsr — so it is known
# here, BEFORE this chunk's data transfer touches LWRAM 0x280000. That makes the uninstall RACE-FREE.
#
#   INSTALL (magic-gated): vector41 != vhook AND *(blob_base) == BLOB_MAGIC ("GDMB", first 4 B of the
#     blob) -> the blob is fully resident (the magic sits near the END of E804, file 0x291E0) -> chain
#     the current handler into the blob's V_HANDLER slot, write vhook into vector41.
#   UNINSTALL (FAD-gated, race-free): vector41 == vhook AND curFAD < 0x7B17 (= E804's start FAD) -> a
#     field-MDT load BELOW E804 is starting (E800 reloading on theater EXIT, which will clobber the
#     blob at 0x280000) -> restore vector41 = ORIG_VBLANK (0x06000846, resident/stable) NOW, before the
#     clobber. Audio (0xA0A6+) and drama (0x1BFAE+) are >= 0x7B17 so they never uninstall; E804 re-reads
#     (0x7B17) are >= so they keep it installed. FIELD/*.MDT span 0x72D0..0x8A53; the theater is a
#     dead-end room whose only exit reloads E800 (0x7A21 < 0x7B17). A both-sides window
#     [0x7000,0x9000)\\[0x7B17,0x7B6A) would generalize to exits via higher-FAD rooms (not needed here).
# No `jsr` (install/uninstall inlined) so PR is preserved for the tail-call to the orig CD fn.
FAD_VAR = 0x06002008             # live requested/playback FAD (written at 0x0600427E pre-0x2394-jsr)
E804_FAD_LO = 0x7B17             # E804.MDT start FAD; field-MDT loads below this = theater exit
ROOM_BOOTSTRAP_SRC = """
boot:
  mov.l @(P_VEC,PC),r0    ; r0 = &vector41
  mov.l @r0,r3           ; r3 = *vector41
  mov.l @(P_VHOOK,PC),r5  ; r5 = vhook entry
  mov.l @(P_FADVAR,PC),r1
  mov.l @r1,r1           ; r1 = curFAD (this chunk's requested FAD, written pre-transfer)
  mov.l @(P_ELO,PC),r2   ; gate threshold
  cmp/hs r2,r1           ; T = curFAD >= threshold
  %s p_exit              ; -> EXIT-zone read (branch dir per gate mode; see build_room_bootstrap)
  cmp/eq r5,r3           ; KEEP zone: already installed?
  bt p_done              ; yes -> nothing to do
  mov.l @(P_BASE,PC),r1  ; not installed: magic-gate install (blob fully resident?)
  mov.l @r1,r1           ; r1 = *(blob_base)
  mov.l @(P_MAGIC,PC),r2
  cmp/eq r2,r1
  bf p_done
  mov.l @(P_HSLOT,PC),r2 ; install: V_HANDLER = current handler (chain), vector41 = vhook
  mov.l r3,@r2
  bra p_done
  mov.l r5,@r0           ; (delay slot: vector41 = vhook)
p_exit:
  cmp/eq r5,r3           ; EXIT zone: a field-MDT load that clobbers LWRAM 0x280000 is starting.
  bf p_done              ; not installed -> DO NOTHING. Install is FORBIDDEN here: pre-transfer the
  mov.l @(P_ORIGH,PC),r2 ; magic can still be resident, so installing would leave the vector pointing
  mov.l r2,@r0           ; at code this chunk is about to clobber = crash (s14 exit-race fix).
p_done:
  mov.l @(P_ORIG,PC),r3
  jmp @r3
  nop
.align 4
P_VEC:    .long %d
P_VHOOK:  .long %d
P_BASE:   .long %d
P_MAGIC:  .long %d
P_HSLOT:  .long %d
P_FADVAR: .long %d
P_ELO:    .long %d
P_ORIGH:  .long %d
P_ORIG:   .long %d
"""

PREFIX_LIMIT = 0x60          # the 96 B cold-boot-stable IP prefix (0x06008434..0x06008494)


# --- s14: 3-ZONE room bootstrap (the RC-layout shipper; supersedes the 2-zone gate above) -------
#
# WHY (root-caused on the pB_rc build, 2026-07-02): the theater room STREAMS ITS BGM from GM3.STZ
# continuously (observed FADs ~0xA2xx..0xA3xx, 0x18-sector chunks). With any 2-zone keep/exit gate,
# those BGM reads sit in the KEEP zone, so during the exit transition the reads INTERLEAVE with the
# E800 room load: [E800 chunk -> uninstall] [BGM chunk -> magic still resident -> REINSTALL] [E800
# chunk covering the blob lands -> vhook bytes gone] -> next VBlank jumps into clobbered code ->
# exception storm (observed: stack spray of PC=0x29CA40 pairs over the vector table, black screen).
#
# FIX: three zones keyed off the per-chunk requested FAD, with install allowed ONLY on drama reads:
#   [0, DRAMA_LO)            NEUTRAL   in-room BGM (~0xA2xx), E804 reloads (0x7B17), all vanilla-zone
#                                      files: do nothing (installed stays installed, uninstalled
#                                      stays uninstalled).
#   [DRAMA_LO, EXIT_THR)     INSTALL   the 5 drama streams (0x1BFAE..0x20993): magic-gated install.
#                                      Captions need the vhook only while a drama plays, so deferring
#                                      install to the first drama chunk costs nothing.
#   [EXIT_THR, inf)          EXIT      the relocated-MDT zone (E800 reload = leaving the theater,
#                                      which clobbers the blob at LWRAM 0x280000+): uninstall, and
#                                      NEVER install. BGM chunks are neutral, so no reinstall race.
#
# MAGIC = the vhook entry ADDRESS (e.g. 0x0029CA3C), not "GDMB": the bootstrap already holds the
# vhook address in a register for the installed-check, so using it as the blob's resident sentinel
# drops the P_MAGIC literal + its load — that is what fits the routine in the 96 B stable prefix.
# (The blob spans a single 2048 B disc sector, so per-sector transfers make sentinel-present <=>
# blob-intact atomic.)  Bake the blob with bake_blob(magic=<vhook_entry>) (two-pass; the entry does
# not depend on the magic VALUE).
ROOM_BOOTSTRAP3_SRC = """
boot:
  mov.l @(P_VEC,PC),r0    ; r0 = &vector41
  mov.l @r0,r3           ; r3 = *vector41
  mov.l @(P_VHOOK,PC),r5  ; r5 = vhook entry (== blob magic sentinel)
  mov.l @(P_FADVAR,PC),r1
  mov.l @r1,r1           ; r1 = requested FAD of this chunk (written pre-transfer)
  mov.l @(P_EXIT,PC),r2
  cmp/hs r2,r1           ; FAD >= EXIT_THR ?
  bt p_exit
  mov.l @(P_DLO,PC),r2
  cmp/hs r2,r1           ; FAD >= DRAMA_LO ?  (else NEUTRAL)
  bf p_done
  cmp/eq r5,r3           ; INSTALL zone: already installed?
  bt p_done
  mov.l @(P_BASE,PC),r1  ; sentinel-gate: *(blob_base) == vhook addr <=> blob resident+intact
  mov.l @r1,r1
  cmp/eq r5,r1
  bf p_done
  mov.l @(P_HSLOT,PC),r2 ; install: V_HANDLER = current handler (chain), vector41 = vhook
  mov.l r3,@r2
  bra p_done
  mov.l r5,@r0           ; (delay slot)
p_exit:
  cmp/eq r5,r3           ; EXIT zone: uninstall if installed; NEVER install here
  bf p_done
  mov.l @(P_ORIGH,PC),r2
  mov.l r2,@r0           ; vector41 = ORIG_VBLANK (race-free: pre-transfer)
p_done:
  mov.l @(P_ORIG,PC),r3
  jmp @r3
  nop
.align 4
P_VEC:    .long %d
P_VHOOK:  .long %d
P_FADVAR: .long %d
P_EXIT:   .long %d
P_DLO:    .long %d
P_BASE:   .long %d
P_HSLOT:  .long %d
P_ORIGH:  .long %d
P_ORIG:   .long %d
"""


def build_room_bootstrap3(meta: dict, drama_lo: int, exit_thr: int,
                          orig_fn: int = 0x06009B32, addr: int = 0x060074B8):
    """Assemble the 3-zone bootstrap (see ROOM_BOOTSTRAP3_SRC). Requires a blob baked with
    magic == meta['vhook_entry'] (the address-as-sentinel trick). Returns (code_bytes, asm)."""
    assert meta.get("magic") == meta["vhook_entry"], \
        "3-zone bootstrap requires bake_blob(magic=<vhook_entry>) (address-as-sentinel)"
    assert drama_lo < exit_thr, (drama_lo, exit_thr)
    src = ROOM_BOOTSTRAP3_SRC % (VEC41, meta["vhook_entry"], FAD_VAR, exit_thr, drama_lo,
                                 meta["blob_base"], meta["v_handler_slot"], ORIG_VBLANK, orig_fn)
    a = hook_sh2asm.Asm()
    code = a.assemble2(src, addr)
    if len(code) > 261:
        raise SystemExit(f"bootstrap3 {len(code)} B > 261 B stable IP prefix")
    return code, a


def build_room_bootstrap(meta: dict, orig_fn: int = 0x06009B32, addr: int = 0x06008434,
                         gate: str = "below", exit_fad: int = E804_FAD_LO):
    """Assemble the magic-install / FAD-uninstall room-entry bootstrap from a magic-prefixed blob's
    `meta`. Returns (code_bytes, asm). Raises if it overflows the 96 B stable IP prefix.

    The uninstall gate keys off the per-chunk requested FAD to detect that the theater is being LEFT
    (a field MDT other than E804 is loading, about to clobber the blob at LWRAM 0x280000). Which
    direction depends on where E800 (the theater's exit room) sits relative to E804 ON THE DISC:

      gate="below" (VANILLA/hook_006 layout): E804 at LBA 31361 (FAD 0x7B17), E800 just BELOW it
        (FAD 0x7A21). EXIT zone = curFAD < exit_fad (=E804_FAD_LO); KEEP zone = curFAD >= it
        (E804 reload / audio / drama, all >= 0x7B17). [branch to p_exit on T=0: bf]
      gate="above" (merged RC layout): the dialogue build RELOCATES E800/E804 to high LBAs (FAD
        ~0x2F7xx), but E804 is re-pinned in-place at 0x7B17 and the drama streams GM3.STZ (FAD
        0x996e..~0x209xx). Now the EXIT (E800 reload) is ABOVE the drama. EXIT zone = curFAD >=
        exit_fad (a threshold between the max drama FAD and the relocated MDT zone, e.g. 0x28000);
        KEEP zone = below it (E804 0x7B17 + the whole drama range). [branch to p_exit on T=1: bt]

    In BOTH zones the action is total (s14 exit-race fix): KEEP zone -> magic-gated install if not
    installed; EXIT zone -> uninstall if installed, and NEVER install (pre-transfer the magic can
    still be resident while this very chunk is about to clobber the blob).

    exit_fad = the gate threshold placed in the P_ELO literal slot."""
    assert meta.get("magic") is not None, "bootstrap requires a magic-prefixed blob (bake_blob(magic=...))"
    branch = {"below": "bf", "above": "bt"}[gate]
    # Placeholder appearance order in ROOM_BOOTSTRAP_SRC: the %s branch (in p_installed) precedes the
    # bottom .long block (P_VEC..P_ORIG), so branch must be the FIRST format arg.
    src = ROOM_BOOTSTRAP_SRC % (branch, VEC41, meta["vhook_entry"], meta["blob_base"], meta["magic"],
                                meta["v_handler_slot"], FAD_VAR, exit_fad, ORIG_VBLANK, orig_fn)
    a = hook_sh2asm.Asm()
    code = a.assemble2(src, addr)
    if len(code) > PREFIX_LIMIT:
        raise SystemExit(f"bootstrap {len(code)} B > {PREFIX_LIMIT} B stable IP prefix")
    return code, a


# ---------------------------------------------------------------------------------------------
# STAGE-1 resident loader stub (lives in the 96 B stable IP prefix 0x06008434, reached via the
# 0x2394 redirect = the HIRQ-accumulate helper 0x06009b32 which ticks constantly from early boot).
#
# It is IDEMPOTENT and SELF-GATING on the destination: it only acts once vector 0x41 (0x06000104)
# does NOT already point at the loaded vhook. The body it must run when triggered:
#     cd_read_sectors(blob_fad, nsectors, BLOB_BASE)   <-- the remaining TODO (see docs)
#     jsr  BLOB_BASE        ; stage2-init: install vhook into vector 0x41
#     <tail-call 0x06009b32>
#
# THE ONE UNFINISHED PIECE is cd_read_sectors — see the CD{} map below (all addresses located this
# session via capstone disasm + live --bp tracing) for the turnkey building blocks.
#
# Verification path for the next session (does NOT need cold-boot walk-in navigation): build a disc
# with the blob on a known free sector, load the `theater-screening-menu` savestate (CD IDLE, in the
# theater room — the loader's exact trigger condition) against it (harness overrides the disc hash),
# inject this stub + the 0x2394 redirect, run, --dump-wram, and assert the blob is resident at
# BLOB_BASE and vector 0x41 == vhook_entry. That isolates the CD-read without any GUI navigation.

# --- IP CDBlock driver functions, located by capstone disasm + live --bp tracing (session-7). ---
# The game's per-chunk drama read (`stream_chunk`@0x06004256, which WRITES the clock 0x06002008 — do
# NOT reuse it whole) does exactly: connect CD->filter 0x11; SetFilterMode(0x40 fad);
# SetFilterRange(startFAD,count); SetSectorLength(2048); PlayDisc(startFAD,count); then transfer.
# Verified against YMIR's own CDBlock log ("connected to filter 17 / Filter 17 mode=40 fad / FAD
# range start=01BFFF count=18 / Play parameters start=81BFFF end=800018"). KEY FINDING: the bulk
# sector DATA moves by **SCU-DMA** (regs 0x25fe0080/84/88/8c; fns 0x06009d38/0x06009d88), NOT the CPU
# `read_words` loop (0 hits during the drama; it's used only for small command RESULTS). For a
# one-shot 2-sector blob read, prefer the CPU path (GetThenDeleteSectorData to open the 0x25898000
# gate + read_words->BLOB_BASE) to avoid a stray DMA into arbitrary RAM.
CD = dict(
    stream_chunk      = 0x06004256,  # top per-chunk (writes clock 0x06002008) — reference only
    connect_wait      = 0x06004870,  # SetCDDeviceConnection(r4=filter) + wait HIRQ 0x41
    set_filter_mode   = 0x0600966e,  # (r4=filter, r5=0x40 fad)
    set_filter_range  = 0x06009560,  # (r4=filter, r5=startFAD, r6=count)
    set_filter_conn   = 0x060096dc,  # (r4=filter, r5=flags=1 set-pass, r6=passPartition, r7=falsePart)
    set_sector_length = 0x06009998,  # (r4=0, r5=-1)
    play_disc         = 0x06009344,  # (r4=&playparam) -> PlayDisc; struct below
    get_sector_data   = 0x060099c0,  # (r4=partition, r5=sectorPos, r6=count) GetSectorData(0x61)
    get_then_delete   = 0x06009a1c,  # (r4=partition, r5=sectorPos, r6=count) GetThenDelete(0x63)
    dispatcher        = 0x06009e10,  # (r4=HIRQ-wait-mask, r5=&descriptor{[0]=opcode,...})
    cmd_issue_core    = 0x06009cb8,  # (r4=HIRQ-bit) poll 0x25890008
    write_cmd         = 0x06009ce8,  # write CR1..CR4 from a 4xu16 buffer at r4
    read_words        = 0x06009b7a,  # (r4=count, r5=buf) CPU copy from data reg 0x25898000
    hirq_read         = 0x06009b2a,  # returns *0x25890008 (poll for bit 0x41)
    data_reg          = 0x25898000,  # CD data-transfer register (CPU reads sectors here)
    drama_filter      = 0x11,        # the filter the CD connects to for the drama stream
)
# PlayDisc playparam struct (r4 ->), decoded from 0x06009344/0x06009388: two 8-byte sub-structs +
# a mode byte.  [0:4]=start.type(=1 FAD), [5:8]=start FAD (24-bit BE), [8:12]=end.type(=1),
# [13:16]=end count (24-bit BE), [16]=mode/repeat byte.  build_cr_field ORs 0x80 onto the hi byte.

# === session-9: cd_read_sectors WORKS — proven headlessly (see docs + src/theater/hook_cdread.py). ===
# `hook_cdread.build_routine()` assembles the full sequence; run as a VBlank-vector-0x41 loader vs a
# blob-on-disc build it reads the blob into LWRAM 0x002d6f3c AND its stage2 installs the vhook into
# vector 0x41 — verified on BOTH theater-room-machine-spot (CD idle) AND theater-screening-menu (CD
# busy w/ BGM): blob bytes match, vector 0x41 = 0x002d6f60, no crash.  The session-8 "empty gate" was
# a SetFilterConnection ARG-ORDER bug (it set "Filter 0" not 17 -> filter 17 had no output partition
# -> sectors dropped).  Fixed (CD['set_filter_conn'] = r4=filter, r5=flags, r6=passPartition).
CDREAD_SEQUENCE = (
    "connect_wait(0x11); wait41; set_filter_mode(0x11,0x40); wait41;"
    " set_filter_range(0x11,fad,nsec); wait41; set_filter_conn(0x11,flags=1,passPart=0,0); wait41;"
    " set_sector_length(0,-1); wait41; play_disc(&param); <seek delay>;"
    " get_then_delete(part=0,0,nsec); read_words/copy nsec*1024 words 0x25898000->BLOB_BASE;"
    " jsr BLOB_BASE (stage2 installs vhook into vec 0x41)"
)

# Resident stage-1 stub. cd_read_sectors WORKS when resident (proven). NOT yet wired into the shipped
# disc: the routine is ~308 B but only the 96 B IP prefix (0x06008434) survives boot — 0x06008494 and
# the 0x06008922 gap are both zeroed/clobbered during boot (marker-tested). A cold-boot loader also
# can't be headlessly verified (savestates carry the vanilla IP; no headless nav to the theater room).
# Shipping needs a <=96 B bootstrap that reuses the game's room-entry filter state, or a piggyback on a
# game file load. hook_005 stays the SAFE trampoline.
STAGE1_GUARD_SRC = """
inst:
  mov.l @(C_VEC,PC),r0
  mov.l @r0,r1            ; r1 = *vector41
  mov.l @(C_VHOOK,PC),r2  ; r2 = loaded vhook entry
  cmp/eq r2,r1
  bt c_skip              ; already installed -> nothing to do
  ; ---- TODO: cd_read_sectors(C_FAD, C_NSEC, C_DST) via the CD{} fns above ----
  ; (left unimplemented on purpose: shipping a guessed CD sequence risks a crashing disc)
c_skip:
  mov.l @(C_ORIG,PC),r3
  jmp @r3
  nop
.align 4
C_VEC:   .long %d
C_VHOOK: .long %d
C_ORIG:  .long %d
"""


def build_phase_c(out: Path, blob_fad: int | None = None):
    """Ship the SAFE cold-boot disc (transparent trampoline = hook_003 behavior, freeze-proof) and
    STAGE the relocatable blob + its metadata into the output so the loader work can resume turnkey.
    The blob is written to a high free disc sector (data-only; nothing reads it yet, so it cannot
    affect boot). Returns meta."""
    blob, meta = bake_blob()
    out.mkdir(parents=True, exist_ok=True)
    t1 = HB.make_disc(out)
    # safe trampoline (identical to build_phase_b): redirect 0x2394 -> tail-call orig CD fn.
    pieces = HB.build_phase_b()
    HB.patch_ip(t1, pieces)
    # stage the blob as a standalone file next to the disc (for the next session's CD-read test)
    (out / "blob.bin").write_bytes(blob)
    (out / "blob_meta.json").write_text(__import__("json").dumps(meta, indent=1))
    print(f"phase C: SAFE cold-boot disc -> {out} (trampoline, no freeze); blob.bin staged "
          f"({meta['blob_len']:#x} B, vhook@{meta['vhook_entry']:#x})")
    return meta


RAW, USER, SYNC = 2352, 2048, 16
E804_LBA = 31361                 # /FIELD/E804.MDT start LBA (FAD 0x7B17)
# E804 loads its first ~0x1d000 bytes LINEARLY to LWRAM 0x280000..0x29d000 (the rest = graphics ->
# VDP VRAM, NOT CPU RAM — verified by mapping the file into the live theater dump). So the piggyback
# blob must live in that CPU-loaded window. The one free run big enough is a 1516 B zero block at file
# 0x1CA14 -> LWRAM 0x29CA14 (4-aligned; live-zero in the theater after entry — verified). file 0x1d000+
# (incl. the trailing padding) is NOT in CPU RAM, so it canNOT host the blob.
E804_BLOB_OFF = 0x1CA14          # E804 file offset of the free run -> LWRAM E804_LOAD + 0x1CA14 = 0x29CA14
E804_BLOB_AVAIL = 0x1D000 - E804_BLOB_OFF   # 1516 B (to the end of the linearly-loaded region)


def _write_e804(t1out: Path, file_off: int, data: bytes):
    """Overwrite E804.MDT user-data bytes in the disc copy at `file_off` (sector-aware)."""
    with open(t1out, "r+b") as f:
        for i, b in enumerate(data):
            sector, within = divmod(file_off + i, USER)
            f.seek((E804_LBA + sector) * RAW + SYNC + within)
            f.write(bytes([b]))


def build_phase_e804_test(out: Path, table_budget: int = 0x250):
    # (budget lowered 0x2B0 -> 0x250: the lane-E clear-on-change vhook is 92 B bigger, and this
    # vanilla-layout TEST disc must still fit the 1516 B un-grown free run)
    """TEST-ONLY disc (output/, gitignored, NOT committed; NOT the final shipped composition):
    vanilla base + the magic-prefixed caption blob written IN-PLACE into E804.MDT's largest CPU-loaded
    free zero run (file 0x1CA14 -> LWRAM 0x29CA14, equal-length, no growth/relayout) + the room-entry
    bootstrap in the 96 B IP prefix. Proves the option-(b) mechanism end-to-end: piggyback-load ->
    magic-install -> FAD-gated uninstall. Returns meta."""
    blob_base = E804_LOAD + E804_BLOB_OFF                 # LWRAM 0x29CA14
    blob, meta = bake_blob(drama_table_budget=table_budget, blob_base=blob_base, magic=BLOB_MAGIC,
                           scale2x=True, fad_offset=FAD_LEAD_SECTORS)
    if len(blob) > E804_BLOB_AVAIL:
        raise SystemExit(f"blob {len(blob)} B > {E804_BLOB_AVAIL} B free run; lower table_budget")
    bootstrap, _ = build_room_bootstrap(meta)
    out.mkdir(parents=True, exist_ok=True)
    t1 = HB.make_disc(out)
    _write_e804(t1, E804_BLOB_OFF, blob)                  # in-place, equal-length
    HB.patch_ip(t1, {0x2394: struct.pack(">I", HB.HOOK_ADDR), HB.GAP_FILE: bootstrap})
    (out / "blob.bin").write_bytes(blob)
    (out / "blob_meta.json").write_text(__import__("json").dumps(
        {**meta, "bootstrap_len": len(bootstrap), "e804_file_off": E804_BLOB_OFF}, indent=1))
    print(f"E804 TEST disc -> {out}: blob {len(blob)} B @ LWRAM {blob_base:#x} (E804 file {E804_BLOB_OFF:#x}, "
          f"in-place, avail {E804_BLOB_AVAIL} B); {meta['table_lines']} lines; bootstrap {len(bootstrap)} B "
          f"@ {HB.HOOK_ADDR:#x}; vhook@{meta['vhook_entry']:#x}")
    print("  WARNING: edits E804.MDT in the disc COPY only (gitignored output/); do NOT commit E804.")
    return meta


# ---------------------------------------------------------------------------------------------
# Lane E: sh2emu unit suite (`python3 src/theater/hook_loader.py --selftest`).
# Part 1 recreates lane B's 11 bootstrap3 zone/install/uninstall cases (regression for the s14
# exit-race fix). Part 2 is NEW: the 2x vhook is executed in the interpreter against the FULL
# 5-drama table and its VDP1-FB writes are compared BYTE-EXACT to an independent Python reference
# blit, at sampled FADs covering every drama (early/mid/late), the inter-line holes, and both gate
# edges. This is the unit gate for the all-dramas capacity change (table + FAD range; asm unchanged).

def _ref_blit(body: bytes, font1: bytes, font2: bytes) -> bytearray:
    """Python reference of VHOOK16's blit: 8x8 font pixels as 2x2 blocks at (CAP_X16, CAP_Y16)."""
    fb = bytearray(512 * 256 * 2)
    stride = LINE_H16 * HB.FB_W * 2
    base = (HB.fb_addr(CAP_X16, CAP_Y16) - HB.VDP1_FB)
    r12 = base
    r11 = base
    for ch in body:
        if ch == 10:
            r12 += stride
            r11 = r12
            continue
        gi = ch - 0x20
        g = (font1[gi * 8:gi * 8 + 8] if gi < 32 else font2[(gi - 32) * 8:(gi - 32) * 8 + 8])
        for row in range(8):
            bits = g[row]
            for sub in range(2):
                a = r11 + (row * 2 + sub) * HB.FB_W * 2
                for col in range(8):
                    if bits & (0x80 >> col):
                        fb[a] = 0x05; fb[a + 1] = 0x0F
                        fb[a + 2] = 0x05; fb[a + 3] = 0x0F
                    a += 4
        r11 += 32
    return fb


def _parse_table(table: bytes):
    """[(start_rel, end_rel, body_bytes)] in table order (== vhook scan order)."""
    out, off = [], 0
    while True:
        s = struct.unpack(">H", table[off:off + 2])[0]
        if s == 0xFFFF:
            return out
        e, ln = struct.unpack(">HH", table[off + 2:off + 6])
        out.append((s, e, table[off + 6:off + 6 + ln]))
        off += 6 + ln


def selftest() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import sh2emu
    import hook_caption_table as hct

    BLOB_HOME = 0x0029D214           # RC-layout home (value irrelevant to the logic under test)
    ORIG_FN = 0x06009B32
    DRAMA_LO, EXIT_THR = 0x1BFAE, 0x28000

    blob0, m0 = bake_blob(blob_base=BLOB_HOME, magic=0, scale2x=True,
                          fad_offset=FAD_LEAD_SECTORS, all_dramas=True)
    blob, meta = bake_blob(blob_base=BLOB_HOME, magic=m0["vhook_entry"], scale2x=True,
                           fad_offset=FAD_LEAD_SECTORS, all_dramas=True)
    assert meta["vhook_entry"] == meta["magic"]
    boot, _ = build_room_bootstrap3(meta, drama_lo=DRAMA_LO, exit_thr=EXIT_THR)
    vhook = meta["vhook_entry"]
    passed = failed = 0

    def check(name, ok):
        nonlocal passed, failed
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        passed += ok
        failed += not ok

    # ---------- part 1: bootstrap3 zones (lane B's 11 cases, recreated) ----------
    def run_boot(fad, vec, blob_resident=True, hslot0=0):
        m = sh2emu.Mem()
        m.map(HB.HOOK_ADDR & ~0xFF, b"\x00" * (HB.HOOK_ADDR & 0xFF) + bytes(boot) + b"\x00" * 0x100)
        m.map(VEC41 & ~0xFF, b"\x00" * 0x100)
        m.map(FAD_VAR & ~0xFF, b"\x00" * 0x100)
        m.map(BLOB_HOME, bytes(blob) if blob_resident else b"\x00" * len(blob))
        m.w32(VEC41, vec)
        m.w32(FAD_VAR, fad)
        if hslot0:
            m.w32(meta["v_handler_slot"], hslot0)
        cpu = sh2emu.SH2(m)
        cpu.PC = HB.HOOK_ADDR
        for _ in range(500):
            if cpu.PC == ORIG_FN:
                break
            cpu.step()
        else:
            raise AssertionError("bootstrap never reached orig fn")
        return m.r32(VEC41), m.r32(meta["v_handler_slot"])

    ORIG = ORIG_VBLANK
    v, h = run_boot(0xA2A1, ORIG);              check("neutral: BGM chunk, not installed -> no-op", v == ORIG)
    v, h = run_boot(0x7B17, ORIG);              check("neutral: vanilla E804 FAD, not installed -> no-op", v == ORIG)
    v, h = run_boot(0xA2A1, vhook, hslot0=ORIG); check("neutral: installed stays installed", v == vhook and h == ORIG)
    v, h = run_boot(DRAMA_LO, ORIG);            check("install @ drama_lo edge", v == vhook and h == ORIG)
    v, h = run_boot(0x20992, ORIG);             check("install @ max drama FAD", v == vhook and h == ORIG)
    v, h = run_boot(0x1C167, ORIG, blob_resident=False); check("install zone, blob absent -> no install", v == ORIG)
    v, h = run_boot(0x1C167, vhook, hslot0=ORIG); check("install zone, already installed -> hslot untouched",
                                                        v == vhook and h == ORIG)
    v, h = run_boot(EXIT_THR, vhook, hslot0=ORIG); check("exit @ thr edge: uninstall", v == ORIG)
    v, h = run_boot(0x2F7AD, ORIG);             check("exit: E800 reload, not installed -> NEVER install", v == ORIG)
    v, h = run_boot(DRAMA_LO - 1, ORIG);        check("neutral @ drama_lo-1 edge", v == ORIG)
    v, h = run_boot(0xFFFFF, vhook, hslot0=ORIG); check("exit: high relocated FAD, uninstall", v == ORIG)

    # ---------- part 2: vhook render vs reference blit over the FULL table ----------
    moff = 4                                    # magic prefix
    f1o = meta["font1"] - BLOB_HOME
    f2o = meta["font2"] - BLOB_HOME
    tbo = meta["table"] - BLOB_HOME
    font1, font2 = blob[f1o:f1o + 256], blob[f2o:f2o + 256]
    table = _parse_table(blob[tbo:])
    lo, hi = meta["fad_lo"], meta["fad_hi"]

    def expect(fad):
        if not (lo <= fad < hi):
            return b""
        rel = fad - lo
        for s, e, body in table:
            if s <= rel < e:
                return body
        return b""

    def fresh_mem():
        m = sh2emu.Mem()
        m.map(BLOB_HOME, bytes(blob))
        m.map(FAD_VAR & ~0xFF, b"\x00" * 0x100)
        m.map(HB.VDP1_FB, b"\x00" * (512 * 256 * 2))
        m.map(0x06070000, b"\x00" * 0x1000)      # stack
        return m

    def run_vhook(fad, m=None):
        m = m or fresh_mem()
        m.w32(FAD_VAR, fad)
        cpu = sh2emu.SH2(m)
        cpu.PC = meta["vhook_entry"]
        cpu.PR = 0x12345678                      # must survive (vclear uses bsr; PR saved/restored)
        cpu.R[15] = 0x06070F00
        for _ in range(3_000_000):
            if cpu.PC == ORIG_VBLANK:
                break
            cpu.step()
        else:
            raise AssertionError("vhook never chained")
        assert cpu.PR == 0x12345678, "vhook clobbered PR"
        assert cpu.R[15] == 0x06070F00, "vhook unbalanced stack"
        return m, m.region(HB.VDP1_FB)

    def d_fad(n, sec):
        return hct.drama_start_fad(hct.DRAMA_IDX[n - 1]) + round(sec * hct.SECTORS_PER_SEC) \
            + FAD_LEAD_SECTORS + hct.SYNC_DELAY_SECTORS

    def last_rec_fad(n):
        """FAD inside the LAST caption record of drama n (proves late-drama coverage)."""
        dlo = hct.drama_start_fad(hct.DRAMA_IDX[n - 1]) - lo
        dhi = (hct.GM3_LBA + hct.DRAMA_END_SEC[hct.DRAMA_IDX[n - 1]] + hct.FAD_OFFSET) - lo
        s, e, _ = [t for t in table if dlo <= t[0] < dhi][-1]
        return lo + s

    cases = [("gate: below drama1", lo - 1),
             ("gate: at/above drama5 end", hi),
             ("drama1 title card", d_fad(1, 0.5)),
             ("drama1 MID (~120s)", d_fad(1, 120.0)),
             ("drama1 LAST record", last_rec_fad(1)),
             ("drama2 mid", d_fad(2, 150.0)),
             ("drama2 LAST record", last_rec_fad(2)),
             ("drama3 mid", d_fad(3, 180.0)),
             ("drama3 LAST record", last_rec_fad(3)),
             ("drama4 mid", d_fad(4, 140.0)),
             ("drama4 LAST record", last_rec_fad(4)),
             ("drama5 mid", d_fad(5, 150.0)),
             ("drama5 LAST record", last_rec_fad(5))]
    # plus: a genuine hole (no record) inside the gate, and a SPLIT line's page 1 vs page 2
    rel_holes = [r for r in range(table[0][1], 0x49E5)
                 if not any(s <= r < e for s, e, _ in table)]
    if rel_holes:
        cases.append(("in-gate hole (no record)", lo + rel_holes[0]))
    for s, e, body in table:
        nxt = [t for t in table if t[0] == e]
        if nxt and body.split(b"\n")[0][:6] != nxt[0][2].split(b"\n")[0][:6]:
            cases.append(("split line page 1", lo + s))
            cases.append(("split line page 2 (same line, later)", lo + e))
            break

    for name, fad in cases:
        body = expect(fad)
        want = _ref_blit(body, font1, font2)
        _, got = run_vhook(fad)
        ok = bytes(got) == bytes(want)
        tag = f"{name} [FAD {fad:#x}]" + (f" -> {body.splitlines()[0][:24].decode()}..." if body else " -> (blank)")
        check(tag, ok)

    # ---------- part 2b: STATEFUL clear-on-change (the mid-drama remnant bug, caught live) ------
    # long record A -> different record B on the SAME FB: A's pixels must be fully cleared.
    fA = d_fad(1, 120.0)                          # a long multi-row record
    fB = last_rec_fad(1)                          # a different, shorter record
    m, _ = run_vhook(fA)
    m, got = run_vhook(fB, m)
    check("clear-on-change: A then B leaves no A remnant",
          bytes(got) == bytes(_ref_blit(expect(fB), font1, font2)))
    # record -> in-gate hole: band must be wiped
    hole = lo + rel_holes[0] if rel_holes else None
    if hole is not None:
        m, _ = run_vhook(fA)
        m, got = run_vhook(hole, m)
        check("clear-on-none: record then hole wipes the band",
              all(b == 0 for b in got))
        # and a second hole frame must NOT clear again (V_LAST=0 short-circuit)
        m, got = run_vhook(hole, m)
        check("hole steady-state stays blank", all(b == 0 for b in got))
    # same record twice: second frame just redraws (byte-identical)
    m, g1 = run_vhook(fA)
    m, g2 = run_vhook(fA, m)
    check("same record redraw is stable", bytes(g1) == bytes(g2))
    # gate-fail with stale V_LAST: FB untouched (never clear outside the drama screen)
    m, _ = run_vhook(fA)
    before = bytes(m.region(HB.VDP1_FB))
    m, got = run_vhook(lo - 100, m)
    check("gate-fail never touches the FB (stale V_LAST kept)", bytes(got) == before)

    # ---------- part 2c: lane I — centered geometry + global sync delay ----------
    # CENTERING (cell-exact, all 366 records): each baked row's glyph-cell field must be centered
    # on FB/screen x=176 (the measured "SOUND ONLY" center; stage black = x[46..303]) to within
    # half a glyph (8 px — integer leading-space padding), and must end at or before x=304.
    bad = []
    for s, e, body in table:
        for row in body.split(b"\n"):
            txt = row.strip()
            if not txt:
                continue
            pad = len(row) - len(row.lstrip())
            cell_l = CAP_X16 + pad * 16
            cell_r = cell_l + len(txt) * 16
            if not (CAP_X16 <= cell_l and cell_r <= CAP_X16 + WRAP16 * 16
                    and abs((cell_l + cell_r) / 2 - 176) <= 8):
                bad.append((s, row))
    check(f"centering: all {len(table)} record rows centered on x=176 (+/-8), inside x[48,304)",
          not bad)
    # ink never escapes the stage: rendered FB text pixels confined to x[48,304), y[CAP_Y16,214)
    _, got = run_vhook(d_fad(1, 120.0))
    stray = [i for i in range(0, len(got), 2) if (got[i] or got[i + 1])
             and not (48 <= (i // 2) % 512 < 304
                      and CAP_Y16 <= (i // 2) // 512 < CAP_Y16 + MAX_ROWS16 * LINE_H16)]
    check("centered blit stays inside the stage band", not stray)
    # SYNC DELAY: the module constant shifts EVERY record by exactly that many sectors
    # (individual line timings untouched; bodies identical).
    t0, m0d = hct.bake_vhook_table(fad_offset=FAD_LEAD_SECTORS, sync_delay=0)
    td, mdd = hct.bake_vhook_table(fad_offset=FAD_LEAD_SECTORS)
    p0, pd = _parse_table(t0), _parse_table(td)
    D = hct.SYNC_DELAY_SECTORS
    check(f"sync delay: every record start/end shifted +{D} sectors (~{D / hct.SECTORS_PER_SEC:.2f}s), bodies identical",
          D > 0 and len(p0) == len(pd)
          and all(sd == s0 + D and ed == e0 + D and bd == b0
                  for (s0, e0, b0), (sd, ed, bd) in zip(p0, pd)))
    check("sync delay: vhook gate hi covers the shifted final record",
          meta["fad_hi"] >= meta["fad_lo"] + max(e for _, e, _ in table))

    # ---------- part 3: legacy drama-1 blob still bakes identically-shaped (regression) ----------
    lblob, lmeta = bake_blob(drama_table_budget=0x2B0, blob_base=BLOB_HOME, magic=0x47444d42,
                             scale2x=True, fad_offset=FAD_LEAD_SECTORS)
    check("legacy drama1 bake (fad gate = drama1)", lmeta["fad_lo"] == HB.DRAMA1_FAD_LO
          and lmeta["fad_hi"] == HB.DRAMA1_FAD_HI and lmeta["table_lines"] >= 13)

    print(f"selftest: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "--selftest":
        raise SystemExit(selftest())
    if len(_sys.argv) > 1 and _sys.argv[1] == "--build":
        build_phase_c(Path(_sys.argv[2]))
        raise SystemExit(0)
    if len(_sys.argv) > 2 and _sys.argv[1] == "--e804-test":
        build_phase_e804_test(Path(_sys.argv[2]))
        raise SystemExit(0)
    blob, meta = bake_blob()
    print("blob bytes:", len(blob))
    for k, v in meta.items():
        print(f"  {k:14} = {v:#x}" if isinstance(v, int) else f"  {k:14} = {v}")
    sector = (len(blob) + 2047) // 2048
    print(f"fits in {sector} sector(s) (2048 B each)")
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "blob.bin").write_bytes(blob)
        print("wrote", outdir / "blob.bin")
