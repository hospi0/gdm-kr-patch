#!/usr/bin/env python3
"""battle_results_gfx.py — English re-author of the POST-BATTLE RESULTS screen labels.

The victory/results screen text ("Nの経験値を獲得した!" / 報酬 / ゴールド: / アイテム:) is
NOT stored as text anywhere on disc (verified by every prior lane) — it is a baked
**tile-font** rendered by VDP2. Lane TILEFONT cracked the subsystem:

  * The results-screen glyph atlas is stored UNCOMPRESSED in /BATLE/ENDW.DAT ("END Window"),
    in a CONTIGUOUS block starting at file offset 0x18664. The game copies it verbatim into
    VDP2 VRAM (glyph strips land at VRAM 0x3480 = char-region base).
  * Each glyph is a **32x8 STRIP** = 4 horizontal 8x8 4bpp cells (128 bytes), = the TOP or
    BOTTOM half of a pair of 16x16 characters. A text line is two rows of strips.
  * ENDW.DAT offset of results glyph g (g = 0x29..0x3c) = 0x18664 + (g-0x29)*0x80.

This module composes the English labels onto a virtual screen-coordinate canvas, samples each
strip's 32x8 window (so the staggered/half-height strip layout is handled automatically), and
writes the strips into ENDW.DAT in place (size-preserving). When the game loads the results
screen it copies the patched atlas -> English renders. Validated via the accepted
inject-at-resident-VDP-address route (tools/ymir-harness --inject-vram2), PNGs in docs/lanes/.

Idempotent + md5-gated as a disc-track fold, following the lane-K / mgame pattern.
"""
from __future__ import annotations
import sys, hashlib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
import iso  # noqa: E402

ENDW_BASE = 0x18664          # ENDW.DAT offset of results glyph 0x29
GLYPH0    = 0x29
STRIP_LEN = 0x80

# The results glyph atlas maps 1:1 to VDP2 VRAM: strip glyph g -> VRAM 0x2000+g*0x80,
# and 8x8 char#c -> VRAM c*0x20. The ENDW.DAT offset of any VRAM address A is A+0x151E4
# (derived from ENDW_BASE: 0x18664 == 0x3a00[VRAM of g=0x34] + 0x151E4). So a single 8x8
# cell (char#) lives at ENDW offset char*0x20 + 0x151E4. Verified: char 0x1d0 -> 0x18be4,
# the start of strip 0x34 (== ENDW_BASE + (0x34-0x29)*0x80).
CELL_CONST = 0x151E4
CELL_LEN   = 0x20

def _endw_off(g: int) -> int:
    return ENDW_BASE + (g - GLYPH0) * STRIP_LEN

def _endw_cell(char: int) -> int:
    return char * CELL_LEN + CELL_CONST

_FONT_CACHE = {}
def _font(sz: int):
    if sz not in _FONT_CACHE:
        for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/System/Library/Fonts/Helvetica.ttc"):
            try:
                _FONT_CACHE[sz] = ImageFont.truetype(p, sz); break
            except OSError:
                continue
        else:
            _FONT_CACHE[sz] = ImageFont.load_default()
    return _FONT_CACHE[sz]

def _pack_strip(a):
    """a: 8x32 index array -> 128 bytes (4 horizontal 8x8 cells, 4bpp)."""
    out = bytearray()
    for cell in range(4):
        for y in range(8):
            for x in range(0, 8, 2):
                hi = int(a[y][cell * 8 + x]) & 0xF
                lo = int(a[y][cell * 8 + x + 1]) & 0xF
                out.append((hi << 4) | lo)
    return bytes(out)

# --- English composition: (text, x, y, size) laid out on a 352x224 canvas ---
# The exp line is authored per 32x8 STRIP (strips 0x34-0x3c, all unique). The three static
# labels 報酬/ゴールド:/アイテム: are authored per 8x8 CELL in build_cells() below (they sit
# on their own tilemap rows; the only shared cell is the Gold:/Item: colon, identical in
# both). See docs/lanes/laneTILEFONT.md for the full tilemap + cell/ENDW-offset table.
# NB: the bottom row of exp-line strips is staggered +8px from the top row (top strips at
# x=96/128/160/200, bottom strips at x=104/136/168/208 — see _ORIGINS). Text must start at
# x>=104 so the FIRST glyph has BOTH a top and a bottom strip; x=98 left the "E" bottom-left
# (x96-103) in a top-only gap -> the E rendered clipped (user report, rc_36). x=106 aligns it.
_TEXTS = [
    ("EXP gained!", 106, 24, 13),
]
# strip glyph -> (screen_x0, screen_y0) origin of its 32x8 window (== display position)
_ORIGINS = {
    # exp line (top strips y24, bottom strips y32) — all unique, sample==display.
    # (0x3c lands past ENDW.DAT's end and its bytes aren't in the file; the '!' bottom
    #  is carried by 0x3b, so it is not authored here.)
    0x34: (96, 24), 0x35: (128, 24), 0x36: (160, 24), 0x3b: (200, 24),
    0x38: (104, 32), 0x39: (136, 32), 0x3a: (168, 32), 0x3c: (208, 32),
}
# 0x3c is the LAST atlas strip; its 4th cell is truncated past ENDW.DAT's end, so only
# its first CLIP_TAIL bytes (cells covering x208-231) are writable/needed.
_CLIP = {0x3c}
# strips forced blank (reused separators on the exp line that must not carry ink)
_BLANK = [0x33, 0x37]

def build_strips() -> dict[int, bytes]:
    """Return {glyph: 128-byte strip} for every glyph this module authors."""
    im = Image.new("L", (352, 224), 0)
    d = ImageDraw.Draw(im)
    for s, x, y, sz in _TEXTS:
        d.text((x, y), s, fill=255, font=_font(sz))
    M = np.where(np.asarray(im) > 80, 15, 0)
    out = {}
    for g, (x0, y0) in _ORIGINS.items():
        win = np.zeros((8, 32), dtype=int)
        for yy in range(8):
            for xx in range(32):
                if y0 + yy < 224 and x0 + xx < 352:
                    win[yy][xx] = M[y0 + yy][x0 + xx]
        out[g] = _pack_strip(win)
    for g in _BLANK:
        out[g] = b"\x00" * STRIP_LEN
    return out

# --- The three static labels 報酬 / ゴールド: / アイテム: -------------------------
# These are authored PER 8x8 CELL (char#) rather than per 32x8 strip, because each label
# is a compact block on its own tilemap rows (found via the results pattern-name table at
# VDP2 VRAM 0xe170: 1-word entries, char# in low 10 bits). The exact cell layout (ground
# truth from the live tilemap):
#   報酬  (red, palette bank 5, 5 cells x 3 rows) : char# 0x1a1..0x1af  -> "Reward"
#   ゴールド: (white, bank 3, 6-cell word + colon) : word 0x1b0..0x1b5 / 0x1b7..0x1bc,
#            shared colon 0x1b6(top)/0x1bd(bot)   -> "Gold" + ":"
#   アイテム: (white, bank 3, 6-cell word + colon) : word 0x1be..0x1c3 / 0x1c4..0x1c9,
#            SAME shared colon 0x1b6/0x1bd         -> "Item" + ":"
# Gold: and Item: reuse ONE colon cell (both end in "："), so authoring ":" there satisfies
# both with no tilemap edit. Ink = palette index (7=red for bank5, 15=white for bank3); the
# bank in the tilemap entry colours it. Proven via --inject-vram2 oracle: docs/lanes/.
def _pack_cell(a, ink: int) -> bytes:
    """a: 8x8 luminance array -> 32 bytes 4bpp (ink where >80, else 0)."""
    out = bytearray()
    for yy in range(8):
        for xx in range(0, 8, 2):
            hi = ink if a[yy][xx] > 80 else 0
            lo = ink if a[yy][xx + 1] > 80 else 0
            out.append((hi << 4) | lo)
    return bytes(out)

def _canvas(text: str, w: int, h: int, x: int, y: int, sz: int):
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).text((x, y), text, fill=255, font=_font(sz))
    return np.asarray(im)

def build_cells() -> dict[int, bytes]:
    """Return {char#: 32-byte 8x8 cell} for the three static results labels."""
    cells: dict[int, bytes] = {}

    def rows(text, w, char_rows, ink, sz, x=0, y=1):
        cv = _canvas(text, w, len(char_rows) * 8, x, y, sz)
        for r, chars in enumerate(char_rows):
            for i, ch in enumerate(chars):
                cells[ch] = _pack_cell(cv[r * 8:r * 8 + 8, i * 8:i * 8 + 8], ink)

    # 報酬 -> "Reward" (bank 5), 5 wide x 3 tall, text vertically centred. Ink 8 = the
    # exact G1 label yellow (248,248,0) on this screen's bank-5 palette row (lane W3 test
    # card readout; the previous ink 7 rendered the duller (224,224,0)).
    rows("Reward", 40, [[0x1a1, 0x1a2, 0x1a3, 0x1a4, 0x1a5],
                        [0x1a6, 0x1a7, 0x1a8, 0x1a9, 0x1aa],
                        [0x1ab, 0x1ac, 0x1ad, 0x1ae, 0x1af]], 8, 11, x=0, y=8)
    # ゴールド: -> "Gold" (bank 3 white ink=15), 6-cell word (48px), 2 rows.
    rows("Gold", 48, [[0x1b0, 0x1b1, 0x1b2, 0x1b3, 0x1b4, 0x1b5],
                      [0x1b7, 0x1b8, 0x1b9, 0x1ba, 0x1bb, 0x1bc]], 15, 13)
    # アイテム: -> "Item", 6-cell word (48px), 2 rows.
    rows("Item", 48, [[0x1be, 0x1bf, 0x1c0, 0x1c1, 0x1c2, 0x1c3],
                      [0x1c4, 0x1c5, 0x1c6, 0x1c7, 0x1c8, 0x1c9]], 15, 13)
    # shared colon cell (0x1b6 top / 0x1bd bot) — one ":" satisfies both Gold: and Item:.
    col = _canvas(":", 8, 16, 1, 1, 13)
    cells[0x1b6] = _pack_cell(col[0:8, 0:8], 15)
    cells[0x1bd] = _pack_cell(col[8:16, 0:8], 15)
    return cells

def patch_endw(data: bytes) -> bytes:
    """Write English strips + label cells into an ENDW.DAT byte blob (size-preserving)."""
    b = bytearray(data)
    for g, strip in build_strips().items():
        o = _endw_off(g)
        n = STRIP_LEN
        if o + n > len(b):
            if g in _CLIP:
                n = len(b) - o          # write only the bytes that fit
            else:
                raise ValueError(f"glyph {g:#x} offset {o:#x} past ENDW.DAT end {len(b):#x}")
        b[o:o + n] = strip[:n]
    for ch, cell in build_cells().items():
        o = _endw_cell(ch)
        if o + CELL_LEN > len(b):
            raise ValueError(f"cell {ch:#x} offset {o:#x} past ENDW.DAT end {len(b):#x}")
        b[o:o + CELL_LEN] = cell
    return bytes(b)

def _english_md5() -> str:
    """md5 of the concatenated authored strips + label cells, for idempotency gating."""
    strips = build_strips()
    cells = build_cells()
    blob = (b"".join(strips[g] for g in sorted(strips))
            + b"".join(cells[c] for c in sorted(cells)))
    return hashlib.md5(blob).hexdigest()

def _read_authored(data: bytes) -> bytes:
    out = []
    for g in sorted(build_strips()):
        o = _endw_off(g)
        n = min(STRIP_LEN, len(data) - o)
        out.append(data[o:o + n])
    for ch in sorted(build_cells()):
        o = _endw_cell(ch)
        out.append(data[o:o + CELL_LEN])
    return b"".join(out)

def cmd_patch_file(inp: str, out: str):
    data = Path(inp).read_bytes()
    Path(out).write_bytes(patch_endw(data))
    print(f"patched {inp} -> {out}")

def cmd_fold(track: str):
    """In-place, size-preserving, md5-gated patch of ENDW.DAT on a disc track."""
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    with open(track, "r+b") as f:
        rec = iso.find_record(f, "ENDW.DAT")
        lba, size = rec["lba"], rec["size"]
        data = iso.read_bytes(f, lba, size)
        new = patch_endw(data)
        if new == data:
            print("ENDW.DAT: already English (results exp line + labels) — skip"); return
        # write back sector-by-sector (Mode 1 user data)
        for i in range(0, len(new), U):
            sec = lba + i // U
            off = sec * RAW + SYNC
            f.seek(off)
            f.write(new[i:i + U])
    print(f"ENDW.DAT: results -> English ({len(build_strips())} strips + "
          f"{len(build_cells())} label cells)")

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "fold":
        cmd_fold(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "patch-file":
        cmd_patch_file(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 2 and sys.argv[1] == "md5":
        print(_english_md5())
    else:
        print("usage: battle_results_gfx.py fold TRACK1.bin | patch-file IN OUT | md5")
