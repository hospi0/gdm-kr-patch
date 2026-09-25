#!/usr/bin/env python3
"""battle_skillgain_gfx.py — English re-author of the TWO post-battle summary screens that use
the ENDW.DAT VDP2 tile-font (NBG1): the SKILL-GAIN screen (戦闘結果 / 習得技術) and the EXP/STAT
screen (戦闘結果 / 経験値).

Subsystem (lanes TILEFONT / N3 / N6): a baked VDP2 tile-font whose 8x8 4bpp glyph atlas is stored
UNCOMPRESSED in /BATLE/ENDW.DAT and copied into VDP2 VRAM at screen load. NBG1, pattern-name table
~VRAM 0xe000 (1-word entries, palette bank 3, char# in low 10 bits, each 8x8 cell -> VRAM char*0x20).
The ENDW.DAT offset of a VRAM char# depends on WHICH screen's block is loaded:
  * RESULTS screen (report/gold/item) : char*0x20 + 0x151E4   (tools/battle_results_gfx.py)
  * SKILL-GAIN screen                 : char*0x20 + 0x5D4C
  * EXP/STAT screen                   : char*0x20 + 0xAD48
All THREE blocks verified byte-identical to the live VDP2 VRAM for their screen.

WHAT THIS TOOL AUTHORS (all size-preserving, in-place, md5/byte-gated, idempotent) — updated by
lane W3 (G1 style parity, rc_47+ polish; see docs/lanes/laneW3-style-parity.md):
  (N3/W3)  SKILL-GAIN element labels ぶき/ほのお/みず/かぜ/つち スキル -> "Weapon skill" /
        "Fire skill" / ... (block 0x5D4C): element name YELLOW (ink 8 + the pW3 bank-5 template
        flip), shared スキル cells -> lowercase white "skill" — exactly the G1 Skills page forms.
  (N6a/W3) CHARACTER NAMES ジャスティン/スー/フィーナ -> JUSTIN/SUE/FEENA (ALL-CAPS white, the G1
        panel-tab form). 16px tall (2 tile rows) on BOTH screens — the original N6 "8px EXP names"
        claim was a tilemap misread that left JP katakana halves on the other row (fixed here).
        Dash flank cells stay untouched; Feena's uneven 6-top/5-bottom cell rows are handled.
  (N6b/W3) EXP/STAT labels 力/体力/す早さ/走力 -> STR/VIT/AGI/MOV, plus the whole label column
        HP/SP/MP/Lv1/Lv2/Lv3/EXP,/LEVEL re-authored (per-cell where the JP design shares cells:
        12b='P' of HP and MP, 142='L' of Lv2/Lv3, ...). All labels YELLOW ink 8 (bank-5 flip);
        '/' of the EXP total white; wedge lead-in/tail cells blanked.
        走力→MOV is a DM-specific stat name (review-flagged in dictionary/exceptions.json).

The red banner headers 戦闘結果/習得技術/経験値 (the old N3 DEFER) are SHIPPED by
tools/pW3_endw_style.py (G1 stream transplant: "Battle Result" / "Skills" / "EXP Points").

Validated live via the resident-inject oracle (whole folded ENDW at HWRAM 0x060C0000 + C-press
re-decode), state user-postbattle-skillgain-rc33: docs/lanes/pW3_results-*-side-by-side.png.
"""
from __future__ import annotations
import sys, hashlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
import iso  # noqa: E402

CELL_LEN = 0x20
CONST_SKILL = 0x5D4C   # SKILL-GAIN screen block
CONST_EXP   = 0xAD48   # EXP/STAT screen block

# Lane W3 (G1 style parity): labels are now YELLOW — the G1 results screens use yellow
# (248,248,0) labels with white values. The tilemap TEMPLATE words for every label cell are
# flipped to pattern bank 5 by tools/pW3_endw_style.py (runs right after this fold in
# build_rc.py), and bank 5 renders ink 8 as the exact G1 yellow (live palette test card —
# see docs/lanes/laneW3-style-parity.md; the results-screen "Reward", bank 5 ink 7, was the
# corroborating datum). Ink 8 under the old bank 3 is a dark gray, so the two folds ship
# together (both are wired in build_rc.py: a built track carries both or neither).
INK_LABEL = 8          # yellow via the bank-5 template flip (was 1 = light-blue, bank 3)
INK_NAME  = 15         # white (pal bank 3) — character names
INK_VALUE = 15         # white (pal bank 3) — value punctuation ('/')

# ----------------------------------------------------------------------------------------------
# Chunky 5x7 pixel font ('#'=ink). Proportional; 7 rows + a blank/descender 8th row.
# Much crisper than the old thresholded Arial-Narrow render (the user asked for the chunky look).
# ----------------------------------------------------------------------------------------------
_G = {
'A':["  #  "," # # "," # # ","#   #","#####","#   #","#   #"],
'B':["#### ","#   #","#   #","#### ","#   #","#   #","#### "],
'C':[" ####","#    ","#    ","#    ","#    ","#    "," ####"],
'D':["###  ","#  # ","#   #","#   #","#   #","#  # ","###  "],
'E':["#####","#    ","#    ","#### ","#    ","#    ","#####"],
'F':["#####","#    ","#    ","#### ","#    ","#    ","#    "],
'G':[" ####","#    ","#    ","#  ##","#   #","#   #"," ####"],
'H':["#   #","#   #","#   #","#####","#   #","#   #","#   #"],
'I':["###","  # ","  # ","  # ","  # ","  # ","###"],
'J':["  ###","    #","    #","    #","#   #","#   #"," ### "],
'K':["#   #","#  # ","# #  ","##   ","# #  ","#  # ","#   #"],
'L':["#    ","#    ","#    ","#    ","#    ","#    ","#####"],
'M':["#   #","## ##","# # #","#   #","#   #","#   #","#   #"],
'N':["#   #","##  #","# # #","#  ##","#   #","#   #","#   #"],
'O':[" ### ","#   #","#   #","#   #","#   #","#   #"," ### "],
'P':["#### ","#   #","#   #","#### ","#    ","#    ","#    "],
'Q':[" ### ","#   #","#   #","#   #","# # #","#  # "," ## #"],
'R':["#### ","#   #","#   #","#### ","# #  ","#  # ","#   #"],
'S':[" ####","#    ","#    "," ### ","    #","    #","#### "],
'T':["#####","  #  ","  #  ","  #  ","  #  ","  #  ","  #  "],
'U':["#   #","#   #","#   #","#   #","#   #","#   #"," ### "],
'V':["#   #","#   #","#   #","#   #","#   #"," # # ","  #  "],
'W':["#   #","#   #","#   #","# # #","# # #","## ##","#   #"],
'X':["#   #","#   #"," # # ","  #  "," # # ","#   #","#   #"],
'Y':["#   #","#   #"," # # ","  #  ","  #  ","  #  ","  #  "],
'Z':["#####","    #","   # ","  #  "," #   ","#    ","#####"],
'a':["     ","     "," ### ","    #"," ####","#   #"," ####"],
'b':["#    ","#    ","#### ","#   #","#   #","#   #","#### "],
'c':["     ","     "," ####","#    ","#    ","#    "," ####"],
'd':["    #","    #"," ####","#   #","#   #","#   #"," ####"],
'e':["     ","     "," ### ","#   #","#####","#    "," ####"],
'f':["  ## "," #  #"," #   ","###  "," #   "," #   "," #   "],
'g':["     "," ####","#   #","#   #"," ####","    #"," ### "],
'h':["#    ","#    ","#### ","#   #","#   #","#   #","#   #"],
'i':["  #  ","     "," ##  ","  #  ","  #  ","  #  "," ### "],
'j':["   # ","     ","  ## ","   # ","   # ","   # "," ##  "],
'k':["#    ","#    ","#  # ","# #  ","##   ","# #  ","#  # "],
'l':[" ##  ","  #  ","  #  ","  #  ","  #  ","  #  ","  ## "],
'm':["     ","     ","## # ","# # #","# # #","# # #","#   #"],
'n':["     ","     ","#### ","#   #","#   #","#   #","#   #"],
'o':["     ","     "," ### ","#   #","#   #","#   #"," ### "],
'p':["     ","#### ","#   #","#   #","#### ","#    ","#    "],
'q':["     "," ####","#   #","#   #"," ####","    #","    #"],
'r':["     ","     ","# ## ","##  #","#    ","#    ","#    "],
's':["     ","     "," ####","#    "," ### ","    #","#### "],
't':[" #   "," #   ","###  "," #   "," #   "," #  #","  ## "],
'u':["     ","     ","#   #","#   #","#   #","#   #"," ####"],
'v':["     ","     ","#   #","#   #","#   #"," # # ","  #  "],
'w':["     ","     ","#   #","# # #","# # #","# # #"," # # "],
'x':["     ","     ","#   #"," # # ","  #  "," # # ","#   #"],
'y':["     ","#   #","#   #","#   #"," ####","    #"," ### "],
'z':["     ","     ","#####","   # ","  #  "," #   ","#####"],
' ':["  ","  ","  ","  ","  ","  ","  "],
'0':[" ### ","#   #","#  ##","# # #","##  #","#   #"," ### "],
'1':[" # ","## "," # "," # "," # "," # ","###"],
'2':[" ### ","#   #","    #","   # ","  #  "," #   ","#####"],
'3':[" ### ","#   #","    #","  ## ","    #","#   #"," ### "],
'4':["   # ","  ## "," # # ","#  # ","#####","   # ","   # "],
'5':["#####","#    ","#### ","    #","    #","#   #"," ### "],
'6':[" ### ","#    ","#    ","#### ","#   #","#   #"," ### "],
'7':["#####","    #","   # ","   # ","  #  ","  #  ","  #  "],
'8':[" ### ","#   #","#   #"," ### ","#   #","#   #"," ### "],
'9':[" ### ","#   #","#   #"," ####","    #","    #"," ### "],
',':["  ","  ","  ","  ","  "," #","# "],
'/':["    #","    #","   # ","  #  "," #   ","#    ","#    "],
'!':["#","#","#","#","#"," ","#"],
}
_DESC = set('gjpqy')

def _glyph(ch):
    rows = _G.get(ch, _G[' '])
    w = max(len(r) for r in rows)
    rows = [r.ljust(w) for r in rows]
    rows = (["".ljust(w)] + rows)[:8] if ch in _DESC else (rows + ["".ljust(w)])[:8]
    return rows, w

def _render(text, tracking=1):
    glyphs = [_glyph(c) for c in text]
    total = sum(w for _, w in glyphs) + tracking*max(len(glyphs)-1, 0)
    a = np.zeros((8, max(total, 1)), dtype=np.uint8)
    x = 0
    for rows, w in glyphs:
        for y in range(8):
            for xi in range(w):
                if rows[y][xi] == '#':
                    a[y, x+xi] = 1
        x += w + tracking
    return a

def _fit(text, W, H=8, tracking=1):
    """Render `text` centred into an (H,W) 1-bit box; squeeze horizontally if too wide, scale to H."""
    from PIL import Image
    a = _render(text, tracking)
    img = Image.fromarray((a*255).astype('uint8'))
    if img.width > W:
        img = img.resize((W, img.height), Image.NEAREST)
    if H != 8:
        img = img.resize((img.width, H), Image.NEAREST)
    arr = (np.asarray(img) > 96).astype(np.uint8)
    out = np.zeros((H, W), dtype=np.uint8)
    ox = (W - arr.shape[1]) // 2
    oy = (H - arr.shape[0]) // 2
    out[oy:oy+arr.shape[0], ox:ox+arr.shape[1]] = arr
    return out

def _pack_cell(a, ink):
    """8x8 1-bit array -> 32 bytes 4bpp solid `ink`."""
    out = bytearray()
    for y in range(8):
        for x in range(0, 8, 2):
            hi = ink if a[y][x]     else 0
            lo = ink if a[y][x + 1] else 0
            out.append((hi << 4) | lo)
    return bytes(out)

def _cells_1row(text, char_ids, ink):
    """Author `text` across N horizontal 8x8 cells (one 8px row). -> {char#: 32B}."""
    W = len(char_ids) * 8
    cv = _fit(text, W, 8)
    return {c: _pack_cell(cv[0:8, i*8:i*8+8], ink) for i, c in enumerate(char_ids)}

def _cells_2row(text, top_ids, bot_ids, ink):
    """Author `text` 16px tall across N columns -> top row + bottom row cells. -> {char#: 32B}."""
    assert len(top_ids) == len(bot_ids)
    W = len(top_ids) * 8
    cv = _fit(text, W, 16)
    cells = {}
    for i, c in enumerate(top_ids):
        cells[c] = _pack_cell(cv[0:8,  i*8:i*8+8], ink)
    for i, c in enumerate(bot_ids):
        cells[c] = _pack_cell(cv[8:16, i*8:i*8+8], ink)
    return cells

# ----------------------------------------------------------------------------------------------
# Cell maps (char#s from the live VDP2 tilemap, both screens; see docs/lanes/laneN6-*.md)
# ----------------------------------------------------------------------------------------------
# --- SKILL-GAIN screen (block 0x5D4C) ---
_SKILL_ELEMENTS = [   # element name -> its 4 unique 8x8 label cells (1 row, left->right)
    ("Weapon", [0x14d, 0x14e, 0x14f, 0x150]),
    ("Fire",   [0x157, 0x158, 0x159, 0x15a]),
    ("Water",  [0x15b, 0x15c, 0x15d, 0x15e]),
    ("Wind",   [0x15f, 0x160, 0x161, 0x162]),
    ("Earth",  [0x163, 0x164, 0x165, 0x166]),
]
_SKILL_SKILL_CELLS = [0x151, 0x152, 0x153, 0x154, 0x155]     # shared "スキル" -> "skill" (all rows;
                                                              #  lowercase white, exactly as G1's Skills page)
# 16px-tall names (top row / bottom row owned cells; dash flanks left untouched)
_SKILL_NAMES = [
    # ALL-CAPS: the G1 reference draws the panel name tabs as JUSTIN/SUE (lane W3)
    ("JUSTIN", [0x102,0x103,0x104,0x105,0x106,0x107], [0x109,0x10a,0x10b,0x10c,0x10d,0x10e]),
    ("SUE",    [0x11b,0x11c,0x11d,0x11e],             [0x11f,0x120,0x121,0x122]),
    ("FEENA",  [0x10f,0x110,0x111,0x112,0x113],       [0x115,0x116,0x117,0x118,0x119]),
]
# --- EXP/STAT screen (block 0xAD48) ---
# Names are 16px tall (2 tile rows) on THIS screen too — the original N6 "8px names" claim
# was a tilemap misread (lane W3): the live pattern-name grid shows every name spanning two
# rows, so the old single-row authoring left the OTHER row showing JP katakana halves
# (Justin/Sue kept their JP bottom strokes, Feena her JP top). Fixed: 2-row authoring into
# the exact live-grid cells. Feena's top row has 6 cells but her bottom only 5 (the 6th
# bottom position is the SHARED blank 0x101, untouched) -> she is authored at 40px with the
# extra top cell blanked.
_EXP_NAMES2 = [
    # (name, top cells, bottom cells, extra top cells to blank)
    ("JUSTIN", [0x107,0x108,0x109,0x10a,0x10b,0x10c], [0x112,0x113,0x114,0x115,0x116,0x117], []),
    ("SUE",    [0x12e,0x12f,0x130,0x131],             [0x134,0x135,0x136,0x137],             []),
    ("FEENA",  [0x11b,0x11c,0x11d,0x11e,0x11f],       [0x124,0x125,0x126,0x127,0x128],       [0x120]),
]
# stat labels: 3 label cells per row (number cells left untouched)
_EXP_STATS = [
    ("STR", [0x103, 0x104, 0x105]),   # 力
    ("VIT", [0x10e, 0x10f, 0x110]),   # 体力
    ("AGI", [0x118, 0x119, 0x11a]),   # す早さ
    ("MOV", [0x121, 0x122, 0x123]),   # 走力  (DM stat; review-flagged)
]
# HP/SP/MP/LV/EXP/LEVEL labels (lane W3): the JP disc drew these as baked Latin glyphs with
# the blue body ink; re-authored with the house 5x7 font at the yellow label ink so the
# bank-5 template flip colours them like G1. Several cells are SHARED by design (12b is the
# 'P' of both HP and MP, 142 the 'L' of both LV2 and LV3, 12c the tail of HP and SP), so
# these are authored per-cell (one character per 8x8 cell), keeping every sharing exact.
_EXP_CHAR_CELLS = [   # (cell, char)
    (0x12a, 'H'), (0x12b, 'P'),                      # HP   (12b shared with MPLV1)
    (0x132, 'S'), (0x133, 'P'),                      # SP
    (0x138, 'M'),                                    # MP   (P = shared 12b)
    (0x139, 'L'), (0x13a, 'v'), (0x13b, '1'),        # Lv1 (G1 form: lowercase v)
    (0x142, 'L'), (0x143, 'v'), (0x144, '2'),        # Lv2  (142 shared with Lv3)
    (0x14b, 'v'), (0x14c, '3'),                      # Lv3 (panels 1/3: cells 142,14b,14c)
]
_EXP_GROUP_CELLS = [  # (text, cells, ink) — one string centred across a cell run
    ("Lv3",  [0x153, 0x16d, 0x16e, 0x16f], INK_LABEL),   # panel-2 Lv3 variant (4 cells)
    ("EXP,", [0x15b, 0x15c, 0x15d, 0x15e], INK_LABEL),   # bottom EXP total label
    ("/",    [0x15f],                       INK_VALUE),  # the total's n/m separator
    ("LEVEL",[0x170, 0x171, 0x172, 0x173], INK_LABEL),   # LEVEL banner text
]
# wedge lead-in cells before the stat/HP rows ("(" shaped blue deco) + the HP/SP wedge
# TAIL cell 0x12c: blanked — the wedge body inside the label cells was already dropped by
# N6, this removes the leftover tips.
_EXP_BLANK_CELLS = [0x102, 0x129, 0x12c]

def _build_block_patches():
    """Return {const: {char#: 32B cell}} for the SKILL (0x5D4C) and EXP (0xAD48) blocks."""
    skill, exp = {}, {}
    # SKILL: element labels + shared Skill (chunky font, blue ink)
    for text, ids in _SKILL_ELEMENTS:
        skill.update(_cells_1row(text, ids, INK_LABEL))
    # G1's Skills page draws the shared skill word as lowercase WHITE "skill"
    # (element name yellow + "skill" white); its cells stay bank 3 (not flipped).
    skill.update(_cells_1row("skill", _SKILL_SKILL_CELLS, INK_NAME))
    # SKILL: 16px names (white)
    for name, top, bot in _SKILL_NAMES:
        skill.update(_cells_2row(name, top, bot, INK_NAME))
    # EXP: 16px names (white, 2 rows — see _EXP_NAMES2 note)
    blank = _pack_cell(np.zeros((8, 8), dtype=np.uint8), 0)
    for name, top, bot, extra in _EXP_NAMES2:
        n = min(len(top), len(bot))
        exp.update(_cells_2row(name, top[:n], bot[:n], INK_NAME))
        for c in list(top[n:]) + list(extra):
            exp[c] = blank
    # EXP: stat labels (yellow)
    for text, ids in _EXP_STATS:
        exp.update(_cells_1row(text, ids, INK_LABEL))
    # EXP: HP/SP/MP/LV/EXP/LEVEL labels (yellow; per-cell where cells are shared)
    for cell, ch in _EXP_CHAR_CELLS:
        exp.update(_cells_1row(ch, [cell], INK_LABEL))
    for text, ids, ink in _EXP_GROUP_CELLS:
        exp.update(_cells_1row(text, ids, ink))
    for c in _EXP_BLANK_CELLS:
        exp[c] = blank
    return {CONST_SKILL: skill, CONST_EXP: exp}

def build_patches():
    """Return a flat list of (endw_abs_offset, 32B cell), sorted by offset."""
    out = []
    for const, cells in _build_block_patches().items():
        for ch, cell in cells.items():
            out.append((ch*CELL_LEN + const, cell))
    out.sort()
    return out

def patch_endw(data: bytes) -> bytes:
    b = bytearray(data)
    for off, cell in build_patches():
        if off + CELL_LEN > len(b):
            raise ValueError(f"cell offset {off:#x} past ENDW.DAT end {len(b):#x}")
        b[off:off + CELL_LEN] = cell
    return bytes(b)

def _english_md5() -> str:
    return hashlib.md5(b"".join(cell for _, cell in build_patches())).hexdigest()

def cmd_patch_file(inp: str, out: str):
    Path(out).write_bytes(patch_endw(Path(inp).read_bytes()))
    print(f"patched {inp} -> {out}")

def cmd_fold(track: str):
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    with open(track, "r+b") as f:
        rec = iso.find_record(f, "ENDW.DAT")
        lba, size = rec["lba"], rec["size"]
        data = iso.read_bytes(f, lba, size)
        new = patch_endw(data)
        if new == data:
            print("ENDW.DAT: skill/exp screens already English — skip"); return
        for i in range(0, len(new), U):
            sec = lba + i // U
            f.seek(sec * RAW + SYNC)
            f.write(new[i:i + U])
    print(f"ENDW.DAT: skill-gain + EXP/stat screens -> English ({len(build_patches())} cells)")

def cmd_preview(out_png: str):
    """QA: render every authored cell back onto a labelled sheet (no disc touch)."""
    from PIL import Image, ImageDraw
    patches = build_patches()
    cols = 16; scale = 6; cw = 8*scale+2; ch = 8*scale+14
    rows = (len(patches)+cols-1)//cols
    img = Image.new("RGB", (cols*cw, rows*ch), (20,20,40)); d = ImageDraw.Draw(img)
    pal = {1:(24,136,192), 8:(248,248,0), 15:(248,248,248)}
    for i,(off,cell) in enumerate(patches):
        cx=(i%cols)*cw; cy=(i//cols)*ch
        d.text((cx,cy),f"{off:05x}",fill=(200,200,120))
        for y in range(8):
            for x in range(0,8,2):
                b=cell[y*4+x//2]
                for j,pv in enumerate((b>>4,b&0xf)):
                    col=(0,0,0) if pv==0 else pal.get(pv,(255,0,255))
                    for sy in range(scale):
                        for sx in range(scale):
                            img.putpixel((cx+(x+j)*scale+sx,cy+12+y*scale+sy),col)
    img.save(out_png); print("saved", out_png, f"({len(patches)} cells)")

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fold":
        cmd_fold(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "patch-file":
        cmd_patch_file(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "preview":
        cmd_preview(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "md5":
        print(_english_md5())
    else:
        print("usage: battle_skillgain_gfx.py fold TRACK1.bin | patch-file IN OUT | preview OUT.png | md5")
