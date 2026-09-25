#!/usr/bin/env python3
"""cd_read_sectors — the session-8 CD-read loader (theater caption blob).

Assembles a self-contained SH-2 routine that reads `nsec` sectors at a fixed FAD from the disc into
LWRAM, reusing the game's OWN resident CDBlock driver functions (hook_loader.CD{}). It replicates
exactly what `stream_chunk`@0x06004256 does per drama chunk, changing only the FAD/count -> the blob
sectors and the dest -> BLOB_BASE.

STATUS (see docs/theater-hook.md "session 9"): the read is FULLY PROVEN headlessly. Run as a
VBlank-vector loader against a blob-on-disc build, it reads the 2 blob sectors into LWRAM
`0x002d6f3c` AND its stage2 installs the vhook into VBlank vector 0x41 — verified on BOTH
`theater-room-machine-spot` (CD idle) AND `theater-screening-menu` (CD busy w/ BGM): blob bytes
match, vector 0x41 = 0x002d6f60, no crash. The session-8 "empty gate" was a SetFilterConnection
ARG-ORDER bug (filter must be r4, not r5): it configured "Filter 0" not "Filter 17", so filter 17
had no output partition and its sectors were dropped. Fixed:
`set_filter_conn(r4=filter, r5=flags, r6=passPartition, r7=falsePartition)`.

NOT yet shippable on a cold-boot disc: the routine is ~300 B but only the 96 B IP prefix
(0x06008434) survives boot — 0x06008494 and the 0x06008922 gap are both zeroed/clobbered during
boot (marker-tested). A cold-boot loader also can't be headlessly verified (savestates carry the
vanilla IP; no headless nav to the theater room). Shipping needs a <=96 B bootstrap (reuse the
game's room-entry filter state) or a piggyback on a game file load — see docs.

`build_routine()` returns the assembled bytes (position-dependent at `org`).
"""
from __future__ import annotations
import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_sh2asm
import hook_loader as L

ORIG_VBLANK = 0x06000846     # the original VBlank-vector-0x41 handler we chain to


def build_routine(org: int, blob_fad: int, nsec: int, dst: int = L.BLOB_BASE,
                  orig_handler: int = ORIG_VBLANK, delay: int = 0x00040000,
                  cap: int = 0x00080000) -> bytes:
    """Assemble cd_read_sectors as a VBlank-vector-0x41 loader at `org`. Idempotent (DONE flag).
    On first frame: do the CD read into `dst`, then chain to `orig_handler`."""
    CD = L.CD
    src = f"""
rtn:
  mov.l r0,@-r15
  mov.l r1,@-r15
  mov.l r2,@-r15
  mov.l r3,@-r15
  mov.l r4,@-r15
  mov.l r5,@-r15
  mov.l r6,@-r15
  mov.l r7,@-r15
  mov.l r8,@-r15
  mov.l r14,@-r15
  sts.l pr,@-r15
  mov.l @(R_DONE,PC),r8
  mov.l @r8,r0
  tst r0,r0
  bf chain
  mov #1,r0
  mov.l r0,@r8
  mov.l @(R_CONNECT,PC),r3
  mov #0x11,r4
  jsr @r3
  nop
  bsr wait41
  nop
  mov.l @(R_FMODE,PC),r3
  mov #0x11,r4
  mov #0x40,r5
  jsr @r3
  nop
  bsr wait41
  nop
  mov.l @(R_FRANGE,PC),r3
  mov #0x11,r4
  mov.l @(R_FAD,PC),r5
  mov.l @(R_NSEC,PC),r6
  jsr @r3
  nop
  bsr wait41
  nop
  mov.l @(R_FCONN,PC),r3
  mov #0x11,r4
  mov #1,r5
  mov #0,r6
  mov #0,r7
  jsr @r3
  nop
  bsr wait41
  nop
  mov.l @(R_SLEN,PC),r3
  mov #0,r4
  mov #-1,r5
  jsr @r3
  nop
  bsr wait41
  nop
  mov.l @(R_PARAM,PC),r4
  mov.l @(R_PLAY,PC),r3
  jsr @r3
  nop
  mov.l @(R_DELAY,PC),r6
spin:
  dt r6
  bf spin
  mov.l @(R_GET,PC),r3
  mov #0,r4
  mov #0,r5
  mov.l @(R_NSEC,PC),r6
  jsr @r3
  nop
  mov.l @(R_NWORDS,PC),r4
  mov.l @(R_DST,PC),r5
  mov.l @(R_READW,PC),r3
  jsr @r3
  nop
  ; stage2: jsr BLOB_BASE — captures the live vector 0x41 + installs the vhook
  mov.l @(R_DST,PC),r3
  jsr @r3
  nop
  bra chain
  nop
wait41:
  sts.l pr,@-r15
  mov.l @(R_CAP,PC),r7
w41:
  mov.l @(R_HIRQR,PC),r3
  jsr @r3
  nop
  mov #0x41,r2
  and r2,r0
  mov #0x41,r1
  cmp/eq r1,r0
  bt w41ok
  dt r7
  bf w41
w41ok:
  lds.l @r15+,pr
  rts
  nop
chain:
  lds.l @r15+,pr
  mov.l @r15+,r14
  mov.l @r15+,r8
  mov.l @r15+,r7
  mov.l @r15+,r6
  mov.l @r15+,r5
  mov.l @r15+,r4
  mov.l @r15+,r3
  mov.l @r15+,r2
  mov.l @r15+,r1
  mov.l @(R_HANDLER,PC),r0
  jmp @r0
  mov.l @r15+,r0
.align 4
R_DONE:    .long DONE
R_CONNECT: .long {CD['connect_wait']}
R_FMODE:   .long {CD['set_filter_mode']}
R_FRANGE:  .long {CD['set_filter_range']}
R_FCONN:   .long {CD['set_filter_conn']}
R_SLEN:    .long {CD['set_sector_length']}
R_PLAY:    .long {CD['play_disc']}
R_GET:     .long {CD['get_then_delete']}
R_READW:   .long {CD['read_words']}
R_HIRQR:   .long {CD['hirq_read']}
R_PARAM:   .long PARAM
R_FAD:     .long {blob_fad}
R_NSEC:    .long {nsec}
R_NWORDS:  .long {nsec*1024}
R_DST:     .long {dst}
R_HANDLER: .long {orig_handler}
R_CAP:     .long {cap}
R_DELAY:   .long {delay}
.align 4
DONE:  .long 0
PARAM:
  .long 1
  .byte 0,{(blob_fad>>16)&0xff},{(blob_fad>>8)&0xff},{blob_fad&0xff}
  .long 1
  .byte 0,{(nsec>>16)&0xff},{(nsec>>8)&0xff},{nsec&0xff}
  .byte 0,0,0,0
"""
    return hook_sh2asm.assemble(src, org)


if __name__ == "__main__":
    b = build_routine(0x002e0000, blob_fad=0x24A86, nsec=2)
    print(f"cd_read_sectors routine: {len(b)} bytes @ 0x002e0000 "
          f"(PROVEN: loads blob->LWRAM + installs vhook into vec 0x41, both theater states)")
