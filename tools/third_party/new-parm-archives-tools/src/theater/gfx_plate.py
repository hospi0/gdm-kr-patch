#!/usr/bin/env python3
"""GFX agent (a): decode the theater 上映メニュー plate sprites (DORAM.DAT slot 8).

The drama-selection-screen plates (上映メニュー header + the 5 drama-title plates) are NOT the
ST1-Huffman backgrounds (DORAM slots 3/5, decoded by tools/mg_tree). They use a SECOND,
engine-resident codec: a fixed-Huffman bit decoder at HWRAM function **0x0601A716** with its
decode table baked into the engine at **0x0601A9E4** (so the compressed blob carries no tree).
Per-sprite compressed streams are concatenated in DORAM slot 8 sub-blob [6] (file off 0x9cc =
DORAM 0x26500), indexed by slot-8's sub-tables. Each sprite is decoded straight to VDP1 VRAM
(8bpp), e.g. the header → VRAM 0x299c0 (144x40), src DORAM 0x26500, len 0xC5.

Rather than re-implement the codec, we RUN the real engine routine on a minimal SH-2 interpreter
(tools/sh2emu, extended here with braf/bsrf/xtrct which it lacked). Validated byte-exact: decoding
the header reproduces VRAM 0x299c0 at 100%.

Inputs: an HWRAM image (engine code, e.g. a savestate-0 wram-hi.bin) and an LWRAM image with DORAM
resident (wram-lo.bin) — capture both with the harness `--dump-wram` on the selection screen, or
load DORAM yourself at the same LWRAM address (0x210000 in the captured states).

  decode_plate(hwram, lwram, src_addr, comp_len, out_w, out_h) -> bytes (8bpp pixels)
"""
from __future__ import annotations
import sys
from pathlib import Path
TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
sys.path.insert(0, TOOLS)
import sh2emu  # noqa: E402

PLATE_FN = 0x0601A716     # engine plate-decoder function
VRAM1_BASE = 0x25C00000   # VDP1 VRAM (SCU bus address)


class _SH2(sh2emu.SH2):
    """sh2emu + the opcodes the plate routine needs that the base interpreter lacks."""
    def _exec_at(self, pc, in_delay=False):
        op = self.m.r16(pc); R = self.R
        if (op & 0xF0FF) == 0x0023:          # braf Rn
            self.steps += 1; n = (op >> 8) & 0xF
            self._branch((pc + 4 + R[n]) & 0xFFFFFFFF); return
        if (op & 0xF0FF) == 0x0003:          # bsrf Rn
            self.steps += 1; n = (op >> 8) & 0xF
            self.PR = (pc + 4) & 0xFFFFFFFF
            self._branch((pc + 4 + R[n]) & 0xFFFFFFFF); return
        if (op & 0xF00F) == 0x200D:           # xtrct Rm,Rn
            self.steps += 1; n = (op >> 8) & 0xF; mm = (op >> 4) & 0xF
            R[n] = ((R[mm] << 16) | (R[n] >> 16)) & 0xFFFFFFFF; return
        return super()._exec_at(pc, in_delay)


def decode_plate(hwram: bytes, lwram: bytes, src_addr: int, comp_len: int,
                 out_w: int, out_h: int, dst_vram_off: int = 0x299c0) -> bytes:
    """Run the engine plate decoder; return out_w*out_h bytes of 8bpp pixels."""
    m = sh2emu.Mem()
    m.map(0x06000000, hwram)            # engine code + tables
    m.map(0x00200000, lwram)            # LWRAM (DORAM resident, src lives here)
    m.map(VRAM1_BASE, bytes(0x80000))   # VDP1 VRAM (dst)
    m.map(0x060FC000, bytes(0x4000))    # R2 scratch
    cpu = _SH2(m)
    # Entry register state captured live at the header call (the routine only uses
    # R4=dst, R5=src, R6=len plus engine globals it reads from HWRAM).
    regs = {0: 0x5, 1: 0x06017054, 2: 0x060FC000, 3: PLATE_FN,
            4: VRAM1_BASE + dst_vram_off, 5: src_addr, 6: comp_len, 7: comp_len,
            8: 0x0600CC88, 9: 0x060303D8, 10: 0x06036CAE, 11: 0x06036B90,
            12: 0, 13: 1, 14: 0, 15: 0x06001F64}
    for k, v in regs.items():
        cpu.R[k] = v
    cpu.run(PLATE_FN, max_steps=20_000_000)
    return m.region(VRAM1_BASE)[dst_vram_off:dst_vram_off + out_w * out_h]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("hwram"); ap.add_argument("lwram"); ap.add_argument("out")
    ap.add_argument("--src", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--len", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--w", type=int, required=True); ap.add_argument("--h", type=int, required=True)
    ap.add_argument("--dst", type=lambda x: int(x, 0), default=0x299c0)
    a = ap.parse_args()
    px = decode_plate(Path(a.hwram).read_bytes(), Path(a.lwram).read_bytes(),
                      a.src, a.len, a.w, a.h, a.dst)
    Path(a.out).write_bytes(px)
    print(f"decoded {len(px)} bytes ({a.w}x{a.h}) -> {a.out}")
