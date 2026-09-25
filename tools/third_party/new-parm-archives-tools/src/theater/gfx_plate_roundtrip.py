#!/usr/bin/env python3
"""Real-engine round-trip harness for the plate encoder (the SHIP GATE for pixel correctness).

Validates `gfx_plate_encode` against the actual engine decoder (`gfx_plate.decode_plate`, the
byte-exact SH-2-emulator oracle): encode must produce a stream the real decoder turns back into the
exact input pixels.

WORKING SETUP (proven 2026-06-30): load raw DORAM.DAT into an LWRAM image at SH-2 0x00210000
(lwram offset 0x10000); use an in-theater HWRAM dump (work/freeze/dump/wram-hi.bin) for the resident
engine code.  Slot-8 [6] (DORAM 0x26500 -> SRC 0x00236500) is ONE stream that decodes the WHOLE
plate block: size 0x15000 = 86016 bytes to VRAM 0x299c0 (header 144x40, empty 152x48 @0x2b040,
Gumbo 152x48 @0x2ccc0, then the rest).

RESULT: `decode(encode_block(decoded_block, orig_stream6))` reproduces the full 0x15000 block
**byte-exact** (the no-RLE literal body).  The decoder is input-driven and the no-RLE body carries
no terminator, so after emitting all 86016 correct pixels it keeps consuming source — caught here
(harness uses a 4 MB VRAM map; the run ends on an out-of-range source read AFTER the block is fully
and correctly decoded).  A real-disc build additionally needs the RLE-escape terminator (see
gfx_plate_encode docstring / docs/theater-gfx.md).

  python3 src/theater/gfx_plate_roundtrip.py work/freeze/dump/wram-hi.bin work/theater/gfx/DORAM.DAT
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gfx_plate, gfx_plate_encode as enc  # noqa: E402
import sh2emu  # noqa: E402

SRC = 0x00236500           # DORAM [6] resident in LWRAM (DORAM @ 0x00210000)
OFF = 0x26500              # [6] file offset in DORAM.DAT
DECODE_SIZE = 0x15000      # whole plate block
DST_OFF = 0x299C0          # VRAM dst
# named sub-plates within the block (offset, w, h) — for reporting / English edits
PLATES = {
    "header": (0x00000, 144, 40),     # VRAM 0x299c0
    "empty":  (0x01680, 152, 48),     # VRAM 0x2b040
    "gumbo":  (0x02d00, 152, 48),     # VRAM 0x2ccc0
}


def _decode(hwram: bytes, lwram: bytes, comp_len: int, out_bytes: int):
    """Run the engine decoder with a large VRAM map; return the decoded block (out_bytes)."""
    m = sh2emu.Mem()
    m.map(0x06000000, bytearray(hwram))
    m.map(0x00200000, bytearray(lwram))
    m.map(0x25C00000, bytearray(0x400000))
    m.map(0x060FC000, bytearray(0x4000))
    dst = 0x25C00000 + DST_OFF
    regs = {0: 0x5, 1: 0x06017054, 2: 0x060FC000, 3: 0x0601A716, 4: dst, 5: SRC,
            6: comp_len, 7: comp_len, 8: 0x0600CC88, 9: 0x060303D8, 10: 0x06036CAE,
            11: 0x06036B90, 12: 0, 13: 1, 14: 0, 15: 0x06001F64}
    cpu = gfx_plate._SH2(m)
    for k, v in regs.items():
        cpu.R[k] = v
    exit_reason = "normal"
    try:
        cpu.run(0x0601A716, max_steps=160_000_000)
    except Exception as ex:                       # over-read after the block (no-RLE terminator gap)
        exit_reason = type(ex).__name__
    return m.region(0x25C00000)[DST_OFF:DST_OFF + out_bytes], exit_reason


def run(hwram_path: str, doram_path: str) -> int:
    hwram = Path(hwram_path).read_bytes()
    doram = Path(doram_path).read_bytes()
    lwram = bytearray(0x100000)
    lwram[0x10000:0x10000 + len(doram)] = doram[:0x100000 - 0x10000]
    stream6 = doram[OFF:OFF + 0x14000]

    # 1) decode the original block (ground truth)
    orig, _ = _decode(hwram, bytes(lwram), 0xC5, DECODE_SIZE)
    print(f"original block decoded: {len(orig)} bytes, {100*sum(1 for b in orig if b)//len(orig)}% filled")

    # 2) re-encode it and decode again — must be byte-exact
    re = enc.encode_block(orig, stream6)
    lw2 = bytearray(lwram)
    lw2[0x10000 + OFF:0x10000 + OFF + len(re)] = re
    back, reason = _decode(hwram, bytes(lw2), len(re), DECODE_SIZE)

    ok = back == orig
    normal = reason == "normal"
    print(f"re-encoded body: {len(re)}B (orig [6] ~0x13af0=80624B); decode exit: {reason}")
    print(f"ROUND-TRIP (full 0x15000 block): {'BYTE-EXACT OK' if ok else 'MISMATCH'}"
          f" + {'NORMAL EXIT' if normal else 'ABNORMAL EXIT (' + reason + ')'}")
    for name, (off, w, h) in PLATES.items():
        a = back[off:off + w * h]
        b = orig[off:off + w * h]
        print(f"  [{name:6}] {w}x{h}: {'OK' if a == b else 'DIFF'}")

    # 3) English-edited block: mutate real (non-transparent) pixels across several plates, then
    #    require byte-exact + normal exit again — proves the terminator is content-independent.
    edited = bytearray(orig)
    nz = [i for i in range(DECODE_SIZE) if orig[i]]
    for k, i in enumerate(nz[::997]):            # a spread-out sample of real pixels
        edited[i] = (orig[i] + 0x37 + k) & 0xFF
        if edited[i] == 0:                       # keep it non-zero (don't create new transparency)
            edited[i] = 0x5A
    edited = bytes(edited)
    re2 = enc.encode_block(edited, stream6)
    lw3 = bytearray(lwram)
    lw3[0x10000 + OFF:0x10000 + OFF + len(re2)] = re2
    back2, reason2 = _decode(hwram, bytes(lw3), len(re2), DECODE_SIZE)
    ok2 = back2 == edited
    normal2 = reason2 == "normal"
    print(f"EDITED block ({sum(1 for k in range(len(nz[::997])))} pixels changed): body {len(re2)}B; "
          f"exit: {reason2}")
    print(f"ROUND-TRIP (edited 0x15000 block): {'BYTE-EXACT OK' if ok2 else 'MISMATCH'}"
          f" + {'NORMAL EXIT' if normal2 else 'ABNORMAL EXIT (' + reason2 + ')'}")

    all_ok = ok and normal and ok2 and normal2
    print(f"\nGATE: {'ALL GREEN (byte-exact + normal exit, orig AND edited)' if all_ok else 'FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1], sys.argv[2]))
