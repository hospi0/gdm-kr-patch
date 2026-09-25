#!/usr/bin/env python3
"""pN5_growth_relayout.py — widen the character-GROWTH screen's name field so English
spell/skill names are no longer COVERED by the beige LV-growth box (lane pN5 / TASK N5).

THE BUG (user-reported, docs/lanes/pN5-moves-growth-cutoff.md): on the character growth
"Moves/Skills" + "Moves LEVEL n" pages the English name renders at FULL length but the beige
LV box + LV#/element/SP# are painted OVER its tail at fixed tile-x, so "Puffy Kick" shows as
"Puffy Kic", "Round Whacker" -> "Round Wha", "Puffy Fire" -> "Puffy Fir", etc.

ROOT CAUSE / LEVER (traced live, this lane): the per-row draw routine in the FIELD-menu overlay
/FIELD/CMDMN.BIN (loaded to HWRAM 0x060B2000; file offset = addr - 0x060B2000) draws:
  * the NAME string at x = r11             (r11 = name base = @(2,r9)+17 = tile 19)
  * per stat CELL (LV / 2nd-stat / SP):
      - beige box fill  at x = r11 + 9     (add #9,r4  before jsr 0x060bb3e2)   -> tile 28,32,36
      - the number      at x = r11 + 11    (add #11,r5 before jsr 0x060bb324)   -> tile 30,34,38
      - then r11 += 4   (cascades to the next cell)
The name is drawn from r11 (unchanged by this patch); only the widget offsets move. Bumping the
box offset +9 -> +12 and the number offset +11 -> +14 on all THREE cells relocates the whole
right-hand widget cluster +3 tiles into the empty green margin (tiles 40-43), widening the visible
name field from 9 to ~12 chars. Name code path is untouched (no text change, ordinal-safe, no
battle impact -- battle uses BBG sec1 / MGDAT.BIN, a different file).

The cascade `add #4,r11` between cells is preserved, so inter-column spacing stays 4 tiles:
  box  28,32,36 -> 31,35,39   number 30,34,38 -> 33,37,41.

Idempotent, byte-gated, size-preserving disc-track fold of CMDMN.BIN's six instruction words.
Wire into tools/build_rc.py AFTER the menus step (it edits a FIELD-menu overlay, not a BBG):
    run(sys.executable, ROOT / "tools/pN5_growth_relayout.py", "fold", final_track)
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
import iso  # noqa: E402

LOAD_BASE = 0x060B2000  # CMDMN.BIN loads here; file offset = addr - LOAD_BASE

# (file offset, original word, patched word, note) — big-endian SH2 opcodes in CMDMN.BIN.
# box offset  add #9,r4  (0x7409) -> add #12,r4 (0x740c)
# num offset  add #11,r5 (0x750b) -> add #14,r5 (0x750e)
PATCHES = [
    (0x060C2C32 - LOAD_BASE, 0x7409, 0x740C, "cell1 LV  box  +9->+12"),
    (0x060C2C5A - LOAD_BASE, 0x750B, 0x750E, "cell1 LV  num +11->+14"),
    (0x060C2C78 - LOAD_BASE, 0x7409, 0x740C, "cell2 stat box  +9->+12"),
    (0x060C2CA0 - LOAD_BASE, 0x750B, 0x750E, "cell2 stat num +11->+14"),
    (0x060C2CBE - LOAD_BASE, 0x7409, 0x740C, "cell3 SP  box  +9->+12"),
    (0x060C2CFE - LOAD_BASE, 0x750B, 0x750E, "cell3 SP  num +11->+14"),
]


def _apply(data: bytes) -> bytes:
    b = bytearray(data)
    for off, orig, new, _note in PATCHES:
        cur = (b[off] << 8) | b[off + 1]
        if cur == new:
            continue                      # already relocated (idempotent)
        if cur != orig:
            raise ValueError(f"CMDMN.BIN @{off:#x}: expected {orig:#06x} or {new:#06x}, found {cur:#06x}")
        b[off] = (new >> 8) & 0xFF
        b[off + 1] = new & 0xFF
    return bytes(b)


def cmd_patch_file(inp: str, out: str):
    Path(out).write_bytes(_apply(Path(inp).read_bytes()))
    print(f"patched {inp} -> {out}")


def cmd_fold(track: str):
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    with open(track, "r+b") as f:
        rec = iso.find_record(f, "CMDMN.BIN")
        lba, size = rec["lba"], rec["size"]
        for off, orig, new, _note in PATCHES:
            data = iso.read_bytes(f, lba, size)
            cur = (data[off] << 8) | data[off + 1]
            if cur == new:
                continue
            if cur != orig:
                raise ValueError(f"CMDMN.BIN @{off:#x}: found {cur:#06x}, expected {orig:#06x}")
            sec = lba + off // U
            within = off % U
            secbytes = bytearray(iso.read_bytes(f, sec, U))
            secbytes[within] = (new >> 8) & 0xFF
            if within + 1 < U:
                secbytes[within + 1] = new & 0xFF
            else:
                nb = bytearray(iso.read_bytes(f, sec + 1, U)); nb[0] = new & 0xFF
                f.seek((sec + 1) * RAW + SYNC); f.write(bytes(nb))
            f.seek(sec * RAW + SYNC); f.write(bytes(secbytes[:U]))
    with open(track, "rb") as f:
        d = iso.read_bytes(f, lba, size)
        ok = all(((d[o] << 8) | d[o + 1]) == n for o, _, n, _ in PATCHES)
    print(f"CMDMN.BIN: growth-screen widget relayout +3 tiles ({'ok' if ok else 'FAILED'})")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fold":
        cmd_fold(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "patch-file":
        cmd_patch_file(sys.argv[2], sys.argv[3])
    else:
        print("usage: pN5_growth_relayout.py fold TRACK1.bin | patch-file IN OUT")
