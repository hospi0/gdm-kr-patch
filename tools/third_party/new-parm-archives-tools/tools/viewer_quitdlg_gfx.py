#!/usr/bin/env python3
"""viewer_quitdlg_gfx.py — English re-author of the museum viewers' QUIT dialog ART.

The Start/pause confirm dialog (終了しますか？ / はい / いいえ = "Quit? / Yes / No")
is BAKED as a 128x48 8bpp VDP1 sprite (NOT editable tbl text — proven absent from
every disc file + RAM in every encoding, Lane O). It renders in TWO cursor states
(はい-highlighted and いいえ-highlighted) via a red highlight bar baked into the art.

Lane ART (rc_26) located the sources by tracing the field-sprite codec (0x0601A716)
on fresh viewer entries (headless YMIR):

  * DESIGN-MATERIALS viewer -> MTOUT.DAT slot 2 sub-blob 6 (the SAME field-codec
    stream Lane K re-authors for the banner+labels). The two dialog variants sit at
    DECODED offsets +0x2d00 (はい/YES highlighted) and +0x4500 (いいえ/NO highlighted),
    128x48 each. This module redraws BOTH inside that decoded block; the caller
    (viewer_mtout_gfx.build_english_mtout) re-encodes the whole block once.

  * MONSTER-GUIDE viewer -> B255.BBG (see viewer_quitdlg_monst.py). Separate path.

Redraw method (per 128x48 variant): the JP text is pure WHITE (palette idx 0xff) on
a textured brown box with a RED (0xbc) highlight bar. We INPAINT the white strokes
(iterative mode-fill from non-white 8-neighbours -> the box texture + red bar survive
untouched) then stamp English "QUIT?" (top), "YES"/"NO" (bottom, at the はい/いいえ
anchors) in white with the Pillow default bitmap font auto-sized to each region
(same authoring family as Lane K's banner redraw). The red bar is left in place, so
the selected option stays highlighted in each variant.

Dictionary: 終了->Quit, はい->Yes, いいえ->No (dictionary/terms.json, Lane O). UI is
UPPERCASE. Idempotent: redraw_block() is a no-op if the block is already English
(detected by the absence of the JP top-text white pixels at the kana columns).
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

WHITE = 0xFF          # glyph colour (near-white palette index)
RED = 0xBC            # highlight-bar colour

# decoded-block offsets of the two 128x48 dialog variants (design MTOUT sub-blob 6)
DESIGN_VARIANTS = (0x2D00, 0x4500)
DLG_W, DLG_H = 128, 48

# English label anchors inside a 128x48 variant (x0, x1, y-mid); font auto-sized to fit
TOP_BOX = (6, 120, 12)     # 終了しますか？  -> QUIT?
YES_BOX = (22, 58, 32)     # はい  (over the left highlight anchor)   -> YES
NO_BOX = (72, 118, 32)     # いいえ (over the right anchor)           -> NO


def _inpaint_white(a: np.ndarray) -> np.ndarray:
    """Remove WHITE (text) pixels, filling each from the modal non-white 8-neighbour.
    Preserves the box texture, border and red highlight bar."""
    a = a.astype(int).copy()
    for _ in range(30):
        wy, wx = np.nonzero(a == WHITE)
        if len(wy) == 0:
            break
        upd = {}
        for y, x in zip(wy.tolist(), wx.tolist()):
            ne = []
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < DLG_H and 0 <= nx < DLG_W and a[ny, nx] != WHITE:
                        ne.append(int(a[ny, nx]))
            if ne:
                upd[(y, x)] = max(set(ne), key=ne.count)
        if not upd:
            break
        for (y, x), v in upd.items():
            a[y, x] = v
    return a


def _draw_label(a: np.ndarray, text: str, box, maxh: int) -> None:
    x0, x1, ymid = box
    w = x1 - x0
    img = Image.new("L", (w, 20), 0)
    dr = ImageDraw.Draw(img)
    f = ImageFont.load_default(size=maxh)
    for size in range(maxh, 6, -1):
        f = ImageFont.load_default(size=size)
        bb = dr.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= w and bb[3] - bb[1] <= maxh:
            break
    bb = dr.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    dr.text(((w - tw) // 2 - bb[0], (20 - th) // 2 - bb[1]), text, fill=255, font=f)
    px = img.load()
    for yy in range(20):
        for xx in range(w):
            if px[xx, yy] >= 128:
                Y = ymid - 10 + yy
                if 0 <= Y < DLG_H:
                    a[Y, x0 + xx] = WHITE


def _is_english(a: np.ndarray) -> bool:
    """Heuristic idempotence check: the JP top text fills the kana columns with white
    across x in ~[4,120]; English 'QUIT?' is narrower/centred. If the far-left kana
    column (x 4..10, y 4..20) has no white, treat as already redrawn."""
    band = a[4:20, 4:12]
    return int(np.count_nonzero(band == WHITE)) < 4


def redraw_block(dec: bytearray, variants=DESIGN_VARIANTS) -> int:
    """Redraw the QUIT-dialog variants inside a decoded field-codec block, in place.
    Returns the number of variants redrawn (0 if already English)."""
    n = 0
    for off in variants:
        a = np.frombuffer(bytes(dec[off:off + DLG_W * DLG_H]), np.uint8).reshape(DLG_H, DLG_W)
        if _is_english(a):
            continue
        a = _inpaint_white(a)
        _draw_label(a, "QUIT?", TOP_BOX, 16)
        _draw_label(a, "YES", YES_BOX, 15)
        _draw_label(a, "NO", NO_BOX, 15)
        dec[off:off + DLG_W * DLG_H] = a.astype("uint8").tobytes()
        n += 1
    return n


# ---------------------------------------------------------------- MTOUT builder
def build_english_mtout(vanilla_mtout: str, out_path: str, hwram=None, lwram=None,
                        cram=None) -> None:
    """Produce the FULL English MTOUT.DAT = Lane K's banner+labels (viewer_mtout_gfx)
    PLUS the two English QUIT dialogs (this module), a superset of Lane K's output.
    Same file size; sub-blob 6 re-encoded once; round-trip byte-exact via the oracle.
    Needs the work/pK/base RAM oracles (like viewer_mtout_gfx.build)."""
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(ROOT / "src" / "theater"))
    import gfx_plate
    import viewer_mtout_gfx as vk

    hwram = Path(hwram or vk.HWRAM_DEF).read_bytes()
    lwram = Path(lwram or vk.LWRAM_DEF).read_bytes()
    cram = Path(cram or (ROOT / "work/pK/base/cram-final.bin")).read_bytes()
    mtout = bytearray(Path(vanilla_mtout).read_bytes())

    lw = bytearray(lwram)
    lw[vk.LWRAM_MTOUT - 0x200000:vk.LWRAM_MTOUT - 0x200000 + len(mtout)] = mtout
    dec = bytearray(gfx_plate.decode_plate(
        hwram, bytes(lw), vk.LWRAM_MTOUT + vk.SUB6_OFF, vk.SUB6_SIZE, 256,
        (vk.DEC_SIZE + 255) // 256, dst_vram_off=0x1000)[:vk.DEC_SIZE])

    # Lane K: banner + six selected-label strips
    ban = bytearray(dec[vk.BANNER_OFF:vk.BANNER_OFF + vk.BAN_W * vk.BAN_H])
    vk.redraw_banner(ban, cram, vk.BANNER_TEXT)
    dec[vk.BANNER_OFF:vk.BANNER_OFF + vk.BAN_W * vk.BAN_H] = ban
    for i, text in enumerate(vk.LABELS):
        strip = vk.render_strip(hwram, lwram, text, i in vk.ALIGN_RIGHT)
        off = vk.STRIPS_OFF + i * vk.STRIP_W * vk.STRIP_H
        dec[off:off + vk.STRIP_W * vk.STRIP_H] = strip

    # Lane ART: the two QUIT-dialog variants
    n = redraw_block(dec)
    if n != len(DESIGN_VARIANTS):
        raise SystemExit(f"expected {len(DESIGN_VARIANTS)} JP dialogs, redrew {n}")

    blob = vk.encode_block(bytes(dec))
    if len(blob) > vk.SUB6_SIZE:
        raise SystemExit(f"encoded blob {len(blob)} > slot {vk.SUB6_SIZE}")
    blob = blob.ljust(vk.SUB6_SIZE, b"\x00")
    mtout[vk.SUB6_OFF:vk.SUB6_OFF + vk.SUB6_SIZE] = blob
    lw[vk.LWRAM_MTOUT - 0x200000:vk.LWRAM_MTOUT - 0x200000 + len(mtout)] = mtout
    rt = gfx_plate.decode_plate(hwram, bytes(lw), vk.LWRAM_MTOUT + vk.SUB6_OFF,
                                vk.SUB6_SIZE, 256, (vk.DEC_SIZE + 255) // 256,
                                dst_vram_off=0x1000)[:vk.DEC_SIZE]
    if bytes(rt) != bytes(dec):
        bad = next(i for i, (a, b) in enumerate(zip(rt, dec)) if a != b)
        raise SystemExit(f"round-trip mismatch at +{bad:#x}")
    Path(out_path).write_bytes(mtout)
    print(f"OK: blob {len(blob)} B (fits {vk.SUB6_SIZE}), round-trip byte-exact, "
          f"{n} English dialogs -> {out_path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["build-mtout"])
    ap.add_argument("vanilla_mtout")
    ap.add_argument("out")
    ap.add_argument("--hwram")
    ap.add_argument("--lwram")
    ap.add_argument("--cram")
    a = ap.parse_args()
    build_english_mtout(a.vanilla_mtout, a.out, a.hwram, a.lwram, a.cram)
