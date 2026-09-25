#!/usr/bin/env python3
"""pW3_endw_style.py — post-battle RESULTS-family screens: G1-style page headers (lane W3).

THE SURFACE (RE'd this lane): the red banner headers on the two post-battle summary
screens — 戦闘結果 (Battle Result), 習得技術 (Acquired Skills), 経験値 (EXP) — are VDP1
sprites decoded at screen-open by the SAME resident decompressor the battle chrome uses
(entry HWRAM 0x0601A716; caller = the ENDW driver, PR 0x060C02B8, observed live on the
screen-1 -> screen-2 C transition). The compressed stream lives INSIDE /BATLE/ENDW.DAT:

  * stream: ENDW.DAT 0x3A48 .. 0x5B4C (0x2104 bytes) -> VDP1 VRAM 0x44000..0x46AE0
    (bit-exact vs live VDP1 dumps via tools/pO4_chrome_codec / pO4_chrome_encode oracles)
  * textures (native cells, same in G1): 0x44000 = 戦闘結果 112x32 (LUT fe00: the
    orange-red ramp), 0x44700 = 経験値 64x24, 0x46720 = 習得技術 80x24 (LUT fe04),
    plus the shared window frames / decor (byte-IDENTICAL between DM and the G1 EN disc).

THE FIX = a straight TRANSPLANT from the TrekkiesUnite G1 EN fan patch (the locked style
authority): G1's ENDW.DAT carries the same stream at the same offset with the SAME codec,
and its decoded window differs from DM's ONLY inside the three text cells — where it has
the authentic "Battle Result" (orange-red fill/dark border), "Skills" and "EXP Points"
pre-rendered art. `patches/battle/pW3_g1_endw_stream.bin` = G1's stream (0x1E40 B, extracted from
the patched G1 disc, decode-verified). Both streams write the exact same VRAM extent
(0x44000..0x46AE0, marker-canvas-verified), so the swap is drop-in.

SEMANTIC CROSS-MAP (the one non-transplant bit): in G1 the 0x44700 cell is the SKILLS
page header and 0x46720 the EXP POINTS one — the REVERSE of DM's page->cell mapping. So
the two page headers' display-list elements in ENDW.DAT (same [w6 w7 w8] 2081 mode x0 y0
x1 y1 element format as the chrome tables, w7=(VRAM-0x44000)>>3) get their texture triples
SWAPPED (and x1 adjusted for the 64px vs 80px widths):
  * EXP page element   @0x3324: (01c0,00e0,0818) -> (09c8,04e4,0a18), x1 0x58->0x68
  * skill page element @0x39d2: (09c8,04e4,0a18) -> (01c0,00e0,0818), x1 0x68->0x58
Result: EXP page shows "EXP Points" (80x24), skill page shows "Skills" (64x24).
Elements located by unique word-triple search in ENDW.DAT; verified against the live
VDP1 command lists of both screens (draws at screen x=200,y=100).

Idempotent, byte-gated, size-preserving (stream zero-padded to the 0x2104 footprint).
Wired into tools/build_rc.py after the other ENDW folds (they touch disjoint tile-font
blocks: results +0x151E4 / skill +0x5D4C / exp +0xAD48 — the stream+tables end @0x5D4C).
Validation: resident-inject oracle (whole patched ENDW at HWRAM 0x060C0000 + C-press
re-decodes) — see docs/lanes/laneW3-style-parity.md.
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
import iso  # noqa: E402

STREAM_OFF = 0x3A48          # ENDW.DAT offset of the compressed header/window stream
STREAM_FOOTPRINT = 0x2104    # bytes up to 0x5B4C (the tilemap templates start after)
G1_STREAM = HERE.parent / "patches/battle/pW3_g1_endw_stream.bin"
WIN_LO, WIN_HI = 0x44000, 0x46AE0   # decoded VDP1 window (both streams, marker-verified)

# (endw_off, old_word, new_word) — the two page-header elements' texture swap
GEOM_WORDS = [
    # EXP page (経験値 slot) -> "EXP Points" (G1 cell @0x46720, 80x24)
    (0x3324, 0x01c0, 0x09c8), (0x3326, 0x00e0, 0x04e4), (0x3328, 0x0818, 0x0a18),
    (0x3332, 0x0058, 0x0068),
    # skill page (習得技術 slot) -> "Skills" (G1 cell @0x44700, 64x24)
    (0x39d2, 0x09c8, 0x01c0), (0x39d4, 0x04e4, 0x00e0), (0x39d6, 0x0a18, 0x0818),
    (0x39e0, 0x0068, 0x0058),
]

# ---------------------------------------------------------------------------------------
# LABEL COLOUR: tilemap-template bank flips 3 -> 5 (G1's yellow labels).
# The NBG pattern-name TEMPLATES for the two summary screens live in ENDW.DAT in the
# char<0x100 gap of each screen's glyph block (nothing else lives there — the digit/big-
# digit glyphs come from an external LWRAM font). Entries are 1-word [bank:4][char:12].
# A live palette test card (all 3 stat rows re-authored as index strips under banks
# 5/0/6/3) fixed the screen's bank->colour table: bank 5 ink 8 = (248,248,0), the exact
# G1 label yellow; bank 3 ink 15 = white (names, unchanged). battle_skillgain_gfx.py
# authors the label glyphs at ink 8; this fold flips their template words to bank 5.
# Cells deliberately NOT flipped: names (white), 0x15f '/' (white value), the skill
# screen's red wedge 0x14c + delta arrow 0x156, panel borders 0x10d, digits (runtime
# bank-4 entries — see the lane doc DEFER).
# ---------------------------------------------------------------------------------------
EXP_ZONE = (0xAD48, 0xCD48)      # EXP/stat screen template zone (block base .. +0x2000)
SKILL_ZONE = (0x5B4C, 0x7D4C)    # skill-gain screen template zone (starts after the stream)
EXP_LABEL_CHARS = (
    list(range(0x103, 0x106)) + list(range(0x10e, 0x111)) +      # STR VIT
    list(range(0x118, 0x11b)) + list(range(0x121, 0x124)) +      # AGI MOV
    [0x12a, 0x12b, 0x12c, 0x132, 0x133, 0x138] +                 # HP SP M(P)
    [0x139, 0x13a, 0x13b, 0x142, 0x143, 0x144, 0x14b, 0x14c] +   # LV1 LV2 LV3
    [0x153, 0x16d, 0x16e, 0x16f] +                               # LV3 (panel-2 variant)
    [0x15b, 0x15c, 0x15d, 0x15e] +                               # EXP,
    [0x170, 0x171, 0x172, 0x173]                                 # LEVEL
)
SKILL_LABEL_CHARS = (
    # element names only — the shared "skill" word cells 0x151-0x155 stay bank 3: G1's
    # Skills page draws them lowercase WHITE next to the yellow element name
    list(range(0x14d, 0x151)) +                                  # Weapon
    list(range(0x157, 0x167))                                    # Fire Water Wind Earth
)
TEMPLATE_FLIPS = [(EXP_ZONE, EXP_LABEL_CHARS), (SKILL_ZONE, SKILL_LABEL_CHARS)]


def _scan_words(b, lo, hi, word):
    """Even (word-aligned) offsets of big-endian `word` in b[lo:hi]."""
    pat = word.to_bytes(2, "big")
    out, i = [], lo
    while True:
        i = b.find(pat, i, hi)
        if i < 0:
            break
        if i % 2 == 0:
            out.append(i)
            i += 2
        else:
            i += 1
    return out


def flip_templates(b: bytearray) -> int:
    """Flip 0x3xxx -> 0x5xxx template words for all label chars. Returns #words flipped."""
    n = 0
    for (lo, hi), chars in TEMPLATE_FLIPS:
        for ch in chars:
            for off in _scan_words(b, lo, hi, 0x3000 | ch):
                b[off:off + 2] = (0x5000 | ch).to_bytes(2, "big")
                n += 1
    return n


def templates_done(b) -> bool:
    """True when no label char still carries a bank-3 template word in its zone."""
    for (lo, hi), chars in TEMPLATE_FLIPS:
        for ch in chars:
            if _scan_words(b, lo, hi, 0x3000 | ch):
                return False
    return True


def _rd16(b, o):
    return (b[o] << 8) | b[o + 1]


def _decode(stream: bytes) -> bytes:
    import pO4_chrome_encode as enc
    return enc._rom_decode_raw(bytes(stream), 0x44000)


def geom_state(endw) -> str:
    st = set()
    for off, old, new in GEOM_WORDS:
        cur = _rd16(endw, off)
        if cur == old:
            st.add("old")
        elif cur == new:
            st.add("new")
        else:
            raise SystemExit(f"ENDW geometry word @{off:#x} is neither vanilla nor "
                             f"patched: {cur:#06x} (expected {old:#06x}/{new:#06x})")
    return st.pop() if len(st) == 1 else "mixed"


def patch_endw(endw: bytes) -> bytes:
    """Return the patched ENDW.DAT bytes (headers transplant + element swap + bank flips)."""
    g1 = G1_STREAM.read_bytes()
    assert len(g1) <= STREAM_FOOTPRINT
    b = bytearray(endw)
    for off, _old, new in GEOM_WORDS:
        b[off:off + 2] = new.to_bytes(2, "big")
    b[STREAM_OFF:STREAM_OFF + STREAM_FOOTPRINT] = \
        g1 + b"\x00" * (STREAM_FOOTPRINT - len(g1))
    flip_templates(b)
    return bytes(b)


def _stream_done(endw) -> bool:
    """Decoded-window gate: current stream already renders the G1 art?"""
    cur = _decode(endw[STREAM_OFF:STREAM_OFF + STREAM_FOOTPRINT])
    tgt = _decode(G1_STREAM.read_bytes())
    return cur[WIN_LO:WIN_HI] == tgt[WIN_LO:WIN_HI]


def cmd_fold(track: str):
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    with open(track, "r+b") as f:
        rec = iso.find_record(f, "ENDW.DAT")
        lba, size = rec["lba"], rec["size"]
        endw = iso.read_bytes(f, lba, size)
        if geom_state(endw) == "new" and _stream_done(endw) and templates_done(endw):
            print("ENDW.DAT: G1-style page headers + label banks already applied — skip")
            return
        new = patch_endw(endw)
        # oracle self-check before touching the disc
        chk = _decode(new[STREAM_OFF:STREAM_OFF + STREAM_FOOTPRINT])
        tgt = _decode(G1_STREAM.read_bytes())
        if chk[WIN_LO:WIN_HI] != tgt[WIN_LO:WIN_HI]:
            raise SystemExit("transplanted stream failed the decode oracle")
        assert len(new) == len(endw)
        for i in range(0, len(new), U):
            f.seek((lba + i // U) * RAW + SYNC)
            f.write(new[i:i + U])
    print("ENDW.DAT: post-battle style -> G1 (Battle Result / Skills / EXP Points headers "
          "+ label template banks 3->5)")


def cmd_patch_file(inp: str, out: str):
    Path(out).write_bytes(patch_endw(Path(inp).read_bytes()))
    print(f"patched {inp} -> {out}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fold":
        cmd_fold(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "patch-file":
        cmd_patch_file(sys.argv[2], sys.argv[3])
    else:
        print("usage: pW3_endw_style.py fold TRACK1.bin | patch-file IN OUT")
