#!/usr/bin/env python3
"""Build output/gfx_NNN: patch /FIELD/DORAM.DAT with the English theater plates.

Pipeline (all gated on the real-engine round-trip before any disc write):
  1. decode the original slot-8 [6] plate block (gfx_plate, the byte-exact oracle);
  2. render English plates into it (gfx_build_plates.build_block);
  3. re-encode -> clean-terminating [6] (gfx_plate_encode.encode_block);
  4. HARD GATE: decode the new [6] through the engine again -> must be byte-exact AND exit normally;
  5. splice the new [6] back into DORAM.DAT ([6] is the last blob of the last slot, so this only
     changes the tail — no container-table edits);
  6. relayout the data track (src/relayout.py) to repoint /FIELD/DORAM.DAT, and copy Track 2 + cue.

Usage: python3 src/theater/gfx_ship.py <out_dir e.g. output/gfx_001>
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "theater"))
sys.path.insert(0, str(ROOT / "tools"))

import gfx_plate            # noqa: E402
import gfx_plate_encode as enc  # noqa: E402
import gfx_build_plates as gb   # noqa: E402
import sh2emu               # noqa: E402
import relayout             # noqa: E402

HWRAM = ROOT / "work/freeze/dump/wram-hi.bin"
DORAM = ROOT / "work/theater/gfx/DORAM.DAT"
DISC_BIN = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
DISC_T2 = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 2).bin"

OFF = 0x26500          # DORAM file offset of slot-8 [6]
SRC = 0x00236500       # its LWRAM address (DORAM @ 0x00210000)
TOTAL = 0x15000
DST = 0x25C00000 + 0x299C0

CUE = ('FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
       'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')


def _decode(hwram: bytes, lwram: bytes, comp_len: int):
    m = sh2emu.Mem()
    m.map(0x06000000, bytearray(hwram))
    m.map(0x00200000, bytearray(lwram))
    m.map(0x25C00000, bytearray(0x400000))
    m.map(0x060FC000, bytearray(0x4000))
    regs = {0: 0x5, 1: 0x06017054, 2: 0x060FC000, 3: 0x0601A716, 4: DST, 5: SRC,
            6: comp_len, 7: comp_len, 8: 0x0600CC88, 9: 0x060303D8, 10: 0x06036CAE,
            11: 0x06036B90, 12: 0, 13: 1, 14: 0, 15: 0x06001F64}
    cpu = gfx_plate._SH2(m)
    for k, v in regs.items():
        cpu.R[k] = v
    reason = "normal"
    try:
        cpu.run(0x0601A716, max_steps=160_000_000)
    except Exception as ex:
        reason = type(ex).__name__
    return m.region(0x25C00000)[0x299C0:0x299C0 + TOTAL], reason


def build_doram_bytes() -> bytes:
    """Decode the original plate block, render the English plates, re-encode, run the two hard
    round-trip gates, and return the fully spliced English DORAM.DAT bytes. Raises SystemExit on a
    gate failure so no caller can ship a broken plate block. Reused by rc_integrate (splices the
    result into the merged RC track) so the plate pipeline has ONE gated implementation."""
    hwram = HWRAM.read_bytes()
    doram = DORAM.read_bytes()
    lw = bytearray(0x100000)
    lw[0x10000:0x10000 + len(doram)] = doram[:0x100000 - 0x10000]

    orig, _ = _decode(hwram, bytes(lw), 0xC5)
    eng = gb.build_block(orig)
    new6 = enc.encode_block(eng, doram[OFF:OFF + 0x14000])

    # HARD GATE
    lw2 = bytearray(lw)
    lw2[0x10000 + OFF:0x10000 + OFF + len(new6)] = new6
    back, reason = _decode(hwram, bytes(lw2), len(new6))
    ok = back == eng and reason == "normal"
    print(f"round-trip English block: byte-exact={back == eng} exit={reason}  "
          f"[6]={len(new6)}B (orig 80624)")
    if not ok:
        raise SystemExit("GATE FAILED (round-trip) — not building.")

    # splice: [6] is the last blob of the last slot -> only the tail changes
    new_doram = doram[:OFF] + new6
    # re-decode from the freshly spliced DORAM (loaded standalone) as a final safety check
    lw3 = bytearray(0x100000)
    lw3[0x10000:0x10000 + len(new_doram)] = new_doram[:0x100000 - 0x10000]
    back2, reason2 = _decode(hwram, bytes(lw3), len(new6))
    if not (back2 == eng and reason2 == "normal"):
        raise SystemExit(f"GATE FAILED on spliced DORAM (exact={back2 == eng} exit={reason2})")
    print(f"spliced DORAM.DAT: {len(new_doram)}B (orig {len(doram)}, {len(new_doram) - len(doram):+d})")
    return new_doram


def build(out_dir: str) -> int:
    new_doram = build_doram_bytes()

    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    tmp_doram = od / "DORAM.DAT"
    tmp_doram.write_bytes(new_doram)
    track1 = od / "Track1.bin"
    rc = relayout.relocate_and_grow(str(DISC_BIN), "/FIELD/DORAM.DAT", str(tmp_doram), str(track1))
    if rc != 0:
        return rc
    shutil.copyfile(DISC_T2, od / "Track2.bin")
    (od / "Grandia-DM-patched.cue").write_text(CUE)
    tmp_doram.unlink()   # DORAM.DAT is baked into Track1.bin; keep the dir disc-only
    print(f"BUILT {out_dir}: Track1.bin + Track2.bin + Grandia-DM-patched.cue")
    return 0


if __name__ == "__main__":
    raise SystemExit(build(sys.argv[1] if len(sys.argv) > 1 else "output/gfx_001"))
