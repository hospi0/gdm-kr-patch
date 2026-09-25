#!/usr/bin/env python3
"""battle_banner_reroute.py — make the mid-attack ACTION BANNER show the skill NAME, not its
DESCRIPTION (lane BANNER / O3).

THE BUG (user-reported, laneBANNER-execbanner.md): when a player skill/spell fires, the top action
banner shows the skill's DESCRIPTION (BBG sec4) instead of its NAME (BBG sec1) — e.g. Knife Hurl
fires and the banner reads "Cuts 1 enemy with a sword of ice". Grandia-1 shows the NAME.

ROOT CAUSE (traced live, this lane): the banner render code lives in /BATLE/MGDAT.BIN, loaded to
HWRAM 0x060C0000 (file offset = addr - 0x060C0000). Two sites form the banner's source-string
pointer from the resident BBG item base (r=0x239000) by loading **header[3]** (the description
section base, item+0xc) and adding the base:
    0x060C3556  mov.l @(12,r0),r4   (5403)  — the width/measure pass
    0x060C3590  mov.l @(12,r3),r6   (5633)  — the glyph-draw pass
header[1] (item+0x4) is the NAME section (sec1). sec1 and the description list are index-aligned
127-entry NUL lists, so the same skill index that yields desc[i] yields name[i]. Rerouting both
loads from header[3] (disp 12) to header[1] (disp 4) makes the banner read the NAME:
    5403 -> 5401  (mov.l @(4,r0),r4)
    5633 -> 5631  (mov.l @(4,r3),r6)

FONT: the banner draw honours the 0x03 font-switch (8x16 ASCII); sec4 descriptions carry a leading
0x03, sec1 names are raw ASCII. So this reroute REQUIRES sec1 names to be authored with a leading
0x03 (see tools/moves_sec1.py, which now emits 0x03+ASCII). Both the battle skill MENU and this
banner then render the name in the ASCII font (PROVEN: injecting the two-word reroute + a 0x03-
prefixed "Knife Hur" over the resident copies made the banner read "Knife Hur" in clean English and
the skill menu still rendered it correctly — docs/lanes/laneBANNER-*).

WHY NOT the menu description box: the box uses a DIFFERENT render path (wrapper ~0x0603F9AC, not the
0x060C355C banner path), so it keeps reading sec4 descriptions — unchanged by this reroute.

Idempotent, byte-gated, size-preserving disc-track fold of MGDAT.BIN's two instruction words.

================================================================================
SECOND BANNER PATH — /BATLE/BATLE.BIN (lane pMM, rc_37):  the MGDAT reroute above only fixes ONE of
the two mid-action banner render paths. Per-move animation overlays in MGDAT.BIN carry their own
banner code (0x060C3556, above) for e.g. the 技 skills (Knife Hurl → shows the NAME, PROVEN). But
MAGIC spells / Puffy moves fall back to the DEFAULT banner routine baked into /BATLE/BATLE.BIN
(resident HWRAM 0x0602c000; routines 0x0603FD40 + 0x06040500). Those form the banner's name-source
by dereferencing a HARD-CODED absolute pointer to the resident BBG item's **header[3]** word
(0x0023900c = item_base 0x239000 + 0xc) and adding the base — i.e. header[3] is the skill-NAME
section (in VANILLA header[3] = sec3, the tbl-kanji duplicate name list; the banner honours 0x03).

REGRESSION (lane BAT2, rc_28): tools/battle_bbg_repack.py stubs sec3 to a 4-byte NUL block (donor).
So header[3] now points at 4 empty entries, and the resolver's index-walk (walk N NUL-terminated
strings from the base) skips those 4 empties and spills N-4 entries into sec4 (DESCRIPTIONS) →
the banner shows a WRONG DESCRIPTION (e.g. Puffy-move idx 65 → sec4[61] "Hurl knives around at all
enemies"); for high indices (Burnflare) the walk runs far past the item → OOB read → CRASH.
Traced live from `user-battle-puffyfire-mismap-rc37`: bp 0x0603fdf4 → base r4=0x23995d (=header[3]
stub), idx r5=65, resolver 0x0603fb76 lands on sec4[61]. See docs/lanes/pMM_magic-mismap.md.

FIX (same shape as the MGDAT reroute): repoint the 3 BATLE.BIN name-base literals from header[3]
(0x0023900c) to **header[1]** (0x00239004 = sec1, the English spell/skill NAME list authored as
0x03+ASCII by moves_sec1/battle_bbg_repack). sec1 and vanilla sec3 are ordinal-aligned (verified:
both put Puffy Fire at ordinal 67, Knife Hurl at 60), so reading sec1 with the same game index gives
the SAME skill's name the intact-sec3 game would have shown — restoring vanilla banner semantics in
English, and bounding the walk inside the 128-entry sec1 (no more OOB → no crash). The header[3]
VALUE in the item header is untouched, so section-bounds math is unaffected. Item banners read
header[6] (sec6, also stubbed) but sec5 item names lack the 0x03 prefix → out of scope here
(documented in the lane doc as a separate follow-up).
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
import iso  # noqa: E402

# (file offset, original word, patched word) — big-endian 16-bit SH2 opcodes in MGDAT.BIN
PATCHES = [
    (0x3556, 0x5403, 0x5401),   # measure: mov.l @(12,r0),r4 -> @(4,r0),r4  (header[3]->header[1])
    (0x3590, 0x5633, 0x5631),   # draw:    mov.l @(12,r3),r6 -> @(4,r3),r6
]

# (file offset, original dword, patched dword) — 32-bit BE code literals in BATLE.BIN that hold the
# absolute pointer to the resident BBG item's header[3] (skill-NAME section). Repoint to header[1].
# 0x13e84 = measure literal (routine 0x0603FD40, PROVEN Puffy path); 0x13fb8 = its draw literal;
# 0x14640 = the second banner routine's literal (0x06040500, shared by its measure+draw).
BATLE_PATCHES = [
    (0x13e84, 0x0023900C, 0x00239004),
    (0x13fb8, 0x0023900C, 0x00239004),
    (0x14640, 0x0023900C, 0x00239004),
]

def _apply(data: bytes) -> bytes:
    b = bytearray(data)
    for off, orig, new in PATCHES:
        cur = (b[off] << 8) | b[off + 1]
        if cur == new:
            continue                      # already rerouted (idempotent)
        if cur != orig:
            raise ValueError(f"MGDAT.BIN @{off:#x}: expected {orig:#06x} or {new:#06x}, found {cur:#06x}")
        b[off] = (new >> 8) & 0xFF
        b[off + 1] = new & 0xFF
    return bytes(b)

def cmd_patch_file(inp: str, out: str):
    Path(out).write_bytes(_apply(Path(inp).read_bytes()))
    print(f"patched {inp} -> {out}")

def _patch_bytes_in_record(f, lba, size, off, oldbytes, newbytes):
    """Overwrite len(newbytes) bytes at file offset `off` within a record, honouring the raw-sector
    layout (2352-byte sectors, 2048-byte user data after a 16-byte sync/header). Byte-gated: no-op if
    already patched; raises if neither the original nor the patched value is present. Returns True if
    a write happened."""
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    n = len(newbytes)
    cur = bytes(iso.read_bytes(f, lba, size)[off:off + n])
    if cur == newbytes:
        return False                       # already patched (idempotent)
    if cur != oldbytes:
        raise ValueError(f"@{off:#x}: found {cur.hex()}, expected {oldbytes.hex()}")
    for i in range(n):
        a = off + i
        sec = lba + a // U
        within = a % U
        sb = bytearray(iso.read_bytes(f, sec, U))
        sb[within] = newbytes[i]
        f.seek(sec * RAW + SYNC)
        f.write(bytes(sb[:U]))
    return True


def cmd_fold(track: str):
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    with open(track, "r+b") as f:
        rec = iso.find_record(f, "MGDAT.BIN")
        lba, size = rec["lba"], rec["size"]
        # only the sectors holding the two patched words need touching
        for off, orig, new in PATCHES:
            data = iso.read_bytes(f, lba, size)
            cur = (data[off] << 8) | data[off + 1]
            if cur == new:
                continue
            if cur != orig:
                raise ValueError(f"MGDAT.BIN @{off:#x}: found {cur:#06x}, expected {orig:#06x}")
            sec = lba + off // U
            within = off % U
            secbytes = bytearray(iso.read_bytes(f, sec, U))
            secbytes[within] = (new >> 8) & 0xFF
            # handle a word straddling a sector boundary (not the case here, but be safe)
            if within + 1 < U:
                secbytes[within + 1] = new & 0xFF
            else:
                nb = bytearray(iso.read_bytes(f, sec + 1, U)); nb[0] = new & 0xFF
                f.seek((sec + 1) * RAW + SYNC); f.write(bytes(nb))
            f.seek(sec * RAW + SYNC); f.write(bytes(secbytes[:U]))
        f.flush()
        d = iso.read_bytes(f, lba, size)
        ok = all(((d[o] << 8) | d[o + 1]) == n for o, _, n in PATCHES)
        print(f"MGDAT.BIN: action-banner reroute -> skill NAME ({'ok' if ok else 'FAILED'})")

        # BATLE.BIN default-banner reroute (lane pMM): header[3] (stubbed sec3) -> header[1] (sec1)
        brec = iso.find_record(f, "BATLE.BIN")
        blba, bsize = brec["lba"], brec["size"]
        wrote = 0
        for off, orig, new in BATLE_PATCHES:
            if _patch_bytes_in_record(f, blba, bsize, off,
                                      orig.to_bytes(4, "big"), new.to_bytes(4, "big")):
                wrote += 1
        f.flush()
        d = iso.read_bytes(f, blba, bsize)
        bok = all(int.from_bytes(d[o:o + 4], "big") == n for o, _, n in BATLE_PATCHES)
        print(f"BATLE.BIN: magic/Puffy banner reroute header[3]->header[1] "
              f"({wrote} word(s) written; {'ok' if bok else 'FAILED'})")

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fold":
        cmd_fold(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "patch-file":
        cmd_patch_file(sys.argv[2], sys.argv[3])
    else:
        print("usage: battle_banner_reroute.py fold TRACK1.bin | patch-file IN OUT")
