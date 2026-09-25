#!/usr/bin/env python3
"""monst_text2_fix.py — retarget the Monster-Encyclopedia viewer's TEXT2.BIN buffer.

WHY (rc_23 user issue #5, "monster guide black-screens"):
MONST.BIN (the encyclopedia overlay, loads to HWRAM 0x0602C000) loads its data files
into a fixed LWRAM layout:

    0x230000..0x239000  decoded UI/font mask (0x9000)
    0x239000..0x240000  FIELD/TEXT2.BIN buffer  (0x7000 = 28672 bytes)
    0x240000..          DICDT.DAT (section header = first 32 bytes!)
    0x27C000..          B255.BBG book background

Vanilla FIELD/TEXT2.BIN is 26192 bytes and fits the 0x7000 window. The English menus
build grows it to ~36 KB, so the viewer's load (whole file, size from the boot-built
file index) overruns 0x240000 by ~0x1D80 bytes and CLOBBERS DICDT's section-offset
header (DICDT is loaded BEFORE TEXT2 in the viewer's sequence). The viewer then
dereferences garbage section offsets -> black screen. Proven byte-exact from the
user's rc_23 savestate: LWRAM 0x240000..0x241D80 == English TEXT2[0x7000:0x8D80].

FIX: move the viewer's TEXT2 buffer to LWRAM 0x2E0000 (0x2D8000..0x2F0000 verified
zero/free in the field room, the book-list page and the detail page, vanilla + rc_23).
All of the viewer's references to the buffer are 11 four-byte-aligned literal-pool
constants inside MONST.BIN (base +0x00 / +0x08 / +0x0C / +0x18); no other code
references 0x239xxx (the field engine never places TEXT2 there — verified from the
pre-press savestate). Patching all 11 together keeps loader and readers consistent.

Usage:
  monst_text2_fix.py patch-dat  MONST.BIN [OUT.BIN]        # patch an extracted file
  monst_text2_fix.py patch-track TRACK1.bin OUT_TRACK1.bin # extract, patch, re-inject
  monst_text2_fix.py check      MONST.BIN                  # report vanilla/patched
"""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD_BASE = 0x00239000
NEW_BASE = 0x002E0000

# file offset -> expected vanilla BE u32 (OLD_BASE + delta)
SITES = {
    0x1C08: 0x00,   # load destination / base
    0xB528: 0x00,
    0x12754: 0x00,
    0x14BB8: 0x00,
    0x12DE0: 0x08,
    0x14E0C: 0x08,
    0x12764: 0x0C,
    0x12898: 0x0C,
    0x12F20: 0x0C,
    0x1275C: 0x18,
    0x1288C: 0x18,
}

MONST_SIZE = 235656  # vanilla == rc_23 (never touched by other build steps)


def classify(data: bytes) -> str:
    old = sum(1 for off, d in SITES.items()
              if struct.unpack_from(">I", data, off)[0] == OLD_BASE + d)
    new = sum(1 for off, d in SITES.items()
              if struct.unpack_from(">I", data, off)[0] == NEW_BASE + d)
    if old == len(SITES):
        return "vanilla"
    if new == len(SITES):
        return "patched"
    return f"UNEXPECTED (vanilla-matching sites: {old}/{len(SITES)}, patched: {new})"


def patch(data: bytes) -> bytes:
    if len(data) != MONST_SIZE:
        sys.exit(f"MONST.BIN size {len(data)} != expected {MONST_SIZE} — refusing")
    state = classify(data)
    if state == "patched":
        print("already patched; no-op")
        return data
    if state != "vanilla":
        sys.exit(f"refusing to patch: {state}")
    out = bytearray(data)
    for off, d in SITES.items():
        struct.pack_into(">I", out, off, NEW_BASE + d)
    print(f"patched {len(SITES)} literal sites: TEXT2 buffer {OLD_BASE:#x} -> {NEW_BASE:#x}")
    return bytes(out)


RAW_SECTOR = 2352
USER_DATA = 2048
SYNC_HEADER = 16


def patch_track(track_in: str, track_out: str) -> None:
    """Patch MONST.BIN inside a MODE1/2352 track. If track_out == track_in
    (or is omitted), patches IN PLACE (only MONST's sectors are rewritten)."""
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "MONST.BIN"
        subprocess.run([sys.executable, str(ROOT / "src/iso.py"), "extract",
                        track_in, "MONST.BIN", str(raw)], check=True)
        find = subprocess.run([sys.executable, str(ROOT / "src/iso.py"), "find",
                               track_in, "MONST.BIN"], check=True,
                              capture_output=True, text=True).stdout
        lba = None
        for tok in find.replace("=", " ").split():
            if tok.isdigit() and int(tok) > 150:
                lba = int(tok)
                break
        if lba is None:
            sys.exit(f"could not parse LBA from iso.py find output: {find!r}")
        data = patch(raw.read_bytes())
    in_place = (Path(track_out).resolve() == Path(track_in).resolve())
    if not in_place:
        import shutil
        shutil.copyfile(track_in, track_out)
    with open(track_out, "r+b") as f:
        for i in range(0, len(data), USER_DATA):
            chunk = data[i:i + USER_DATA].ljust(USER_DATA, b"\x00")
            f.seek((lba + i // USER_DATA) * RAW_SECTOR + SYNC_HEADER)
            f.write(chunk)
    print(f"MONST.BIN TEXT2-buffer fix injected at LBA {lba} -> {track_out}"
          f"{' (in place)' if in_place else ''}")


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "check":
        print(classify(Path(sys.argv[2]).read_bytes()))
    elif cmd == "patch-dat":
        src = Path(sys.argv[2])
        out = Path(sys.argv[3]) if len(sys.argv) > 3 else src
        out.write_bytes(patch(src.read_bytes()))
        print(f"wrote {out}")
    elif cmd == "patch-track":
        patch_track(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
