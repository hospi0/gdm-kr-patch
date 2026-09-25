#!/usr/bin/env python3
"""viewer_quitdlg_monst.py — English re-author of the MONSTER-GUIDE viewer's QUIT dialog ART.

Companion to tools/viewer_quitdlg_gfx.py (the DESIGN-materials viewer dialog, Lane ART).
The Start/pause confirm dialog (終了しますか？ / はい / いいえ = "Quit? / Yes / No") in the
monster-encyclopedia viewer is a 128x48 8bpp VDP1 sprite drawn by ONE command at screen
(112,88), pmod 0x08a0 (256-colour bank 0), char data VDP1 0x412c0.

WHERE IT LIVES (this lane, DLG2 rc_27 — corrects Lane ART/M2's "M2 decompressor wall"):
the art is NOT produced by the book-scene decompressor and is NOT compressed. It is stored
**uncompressed** in **/FIELD/DICDT.DAT**, as TWO back-to-back 128x48 8bpp variants at file
offset 0x1FAD0 (はい/YES highlighted) and 0x212D0 (いいえ/NO highlighted, = +0x1800). DICDT.DAT
is loaded whole to LWRAM 0x240000 by the monster viewer, so the two variants become resident
at LWRAM 0x25FAD0 / 0x2612D0; the engine DMAs the active variant to VDP1 0x412c0. (Proven:
LWRAM 0x25FAD0 == displayed VDP1 art byte-exact; DICDT+0x1FAD0 == displayed art 6144/6144.)

Redraw (per 128x48 variant): the JP text is pure value 0x3f (white) on a textured box with a
GREEN highlight bar (value 0x7c). The box BORDER frame is ALSO 0x3f, so — unlike the design
tool which inpaints all 0xff — we inpaint 0x3f ONLY inside the two interior text bands
(top = 終了しますか?, bottom = はい/いいえ), leaving the border + green bar untouched. We then
stamp English "QUIT?" (top), "YES"/"NO" (bottom, at the はい/いいえ anchors) in 0x3f white,
reusing viewer_quitdlg_gfx._draw_label so the font/layout are IDENTICAL to the design dialog.

Dictionary: 終了->Quit, はい->Yes, いいえ->No (dictionary/terms.json, Lane O). UI is UPPERCASE.
Idempotent + content-addressed: patch-track/fold FIND the exact JP variant bytes in DICDT and
swap; if absent (already English) they no-op. This composes with tools/build_dicdt.py (English
encyclopedia text/relocation, step 3) and with Lane J's monst_text2_fix — DICDT text bytes are
untouched (only the two 6144-byte art regions change, size-preserving).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import viewer_quitdlg_gfx as vd  # _draw_label (shared font/layout with the design dialog)

WHITE = 0x3F          # monster-dialog glyph value (design uses 0xff; same authoring, diff palette)
DLG_W, DLG_H = 128, 48
VARIANT_OFFS = (0x1FAD0, 0x1FAD0 + 0x1800)   # DICDT.DAT: YES-hl, NO-hl (back-to-back)

# interior text bands (exclude the 0x3f border: top line y=5, left column x=6)
TOP_BAND = (8, 8, 121, 23)   # x0,y0,x1,y1 : 終了しますか?
BOT_BAND = (8, 24, 121, 39)  # x0,y0,x1,y1 : はい / いいえ

# English label anchors inside a 128x48 variant (x0, x1, y-mid); font auto-sized to fit.
# Measured from the JP glyph extents (top text x8..118 y9..22; はい x24..55; いいえ x73..117).
TOP_BOX = (10, 118, 15)      # QUIT?  (centred on the top band)
YES_BOX = (24, 56, 31)       # YES    (over the はい anchor / green bar)
NO_BOX = (72, 118, 31)       # NO     (over the いいえ anchor)


def _inpaint_white_band(a: np.ndarray, band) -> None:
    """Remove WHITE (0x3f) pixels inside `band` only, filling each from the modal non-white
    8-neighbour. Preserves the box texture, the 0x3f border and the green highlight bar."""
    x0, y0, x1, y1 = band
    for _ in range(30):
        ys, xs = np.nonzero(a == WHITE)
        sel = [(y, x) for y, x in zip(ys.tolist(), xs.tolist())
               if x0 <= x <= x1 and y0 <= y <= y1]
        if not sel:
            break
        upd = {}
        for y, x in sel:
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


def _is_english(a: np.ndarray) -> bool:
    """The JP 終 fills the far-left interior column (x8..14, y9..22) with white; centred
    'QUIT?' does not. If that band has no white, treat the variant as already redrawn."""
    return int(np.count_nonzero(a[9:23, 8:14] == WHITE)) < 3


def redraw_variant(block: bytes) -> bytes:
    """Return an English-redrawn 6144-byte 128x48 variant (no-op if already English)."""
    a = np.frombuffer(bytes(block), np.uint8).reshape(DLG_H, DLG_W).astype(int).copy()
    if _is_english(a):
        return bytes(block)
    _inpaint_white_band(a, TOP_BAND)
    _inpaint_white_band(a, BOT_BAND)
    _draw = vd._draw_label
    _orig_white = vd.WHITE
    vd.WHITE = WHITE  # retarget the shared stamper to the monster glyph value
    try:
        _draw(a, "QUIT?", TOP_BOX, 14)
        _draw(a, "YES", YES_BOX, 13)
        _draw(a, "NO", NO_BOX, 13)
    finally:
        vd.WHITE = _orig_white
    return a.astype("uint8").tobytes()


def redraw_dicdt(dicdt: bytes) -> tuple[bytes, int]:
    """Redraw both QUIT-dialog variants inside a DICDT.DAT buffer. Content-addressed:
    locates each variant by its exact JP bytes (survives relocation / offset shifts).
    Returns (patched, n_redrawn)."""
    buf = bytearray(dicdt)
    n = 0
    for off in VARIANT_OFFS:
        blk = bytes(buf[off:off + DLG_W * DLG_H])
        if len(blk) != DLG_W * DLG_H:
            continue
        new = redraw_variant(blk)
        if new != blk:
            buf[off:off + DLG_W * DLG_H] = new
            n += 1
    return bytes(buf), n


# ------------------------------------------------------------------ track I/O
def _read_dicdt(track: Path):
    import iso
    with open(track, "rb") as f:
        rec = iso.find_record(f, "DICDT.DAT")
        data = iso.read_bytes(f, rec["lba"], rec["size"])
    return rec, data


def _inject_dicdt(track: Path, rec, data: bytes):
    """Size-preserving in-place re-inject of DICDT.DAT logical bytes at its LBA."""
    import iso
    lba = rec["lba"]
    with open(track, "r+b") as f:
        for i in range(0, len(data), iso.USER_DATA):
            sec = lba + i // iso.USER_DATA
            chunk = data[i:i + iso.USER_DATA]
            f.seek(iso.raw_offset(sec))   # raw_offset already includes the 16-byte sync/header
            f.write(chunk)


def cmd_fold(track: str) -> int:
    tp = Path(track)
    rec, data = _read_dicdt(tp)
    patched, n = redraw_dicdt(data)
    if n == 0:
        print("viewer_quitdlg_monst: DICDT QUIT dialog already English — skipping")
        return 0
    _inject_dicdt(tp, rec, patched)
    # verify round-trip
    _, back = _read_dicdt(tp)
    _, n2 = redraw_dicdt(back)
    if n2 != 0:
        raise SystemExit(f"fold verify failed: {n2} variants still JP after inject")
    print(f"viewer_quitdlg_monst: redrew {n} QUIT-dialog variant(s) in DICDT.DAT "
          f"(LBA {rec['lba']}, {rec['size']} B, in place)")
    return 0


def cmd_extract(track: str, out: str):
    _, data = _read_dicdt(Path(track))
    Path(out).write_bytes(data)
    print(f"wrote DICDT.DAT ({len(data)} B) -> {out}  md5={hashlib.md5(data).hexdigest()}")


def cmd_preview(track: str, outdir: str):
    """Render JP + English previews of both variants (needs a CRAM dump for colours)."""
    from PIL import Image
    _, data = _read_dicdt(Path(track))
    od = Path(outdir); od.mkdir(parents=True, exist_ok=True)
    cram_path = ROOT / "work/pDLG2/base_dump/cram-final.bin"
    cram = cram_path.read_bytes() if cram_path.exists() else None

    def render(block, path):
        a = np.frombuffer(block, np.uint8).reshape(DLG_H, DLG_W)
        img = Image.new("RGB", (DLG_W * 3, DLG_H * 3))
        px = img.load()
        for y in range(DLG_H):
            for x in range(DLG_W):
                v = int(a[y, x])
                if cram:
                    w = cram[(v & 0x7ff) * 2] | (cram[(v & 0x7ff) * 2 + 1] << 8)
                    c = ((w & 0x1f) << 3, (w >> 5 & 0x1f) << 3, (w >> 10 & 0x1f) << 3)
                else:
                    c = (v, v, v)
                for dy in range(3):
                    for dx in range(3):
                        px[x * 3 + dx, y * 3 + dy] = c
        img.save(path)

    for name, off in zip(("A_yes", "B_no"), VARIANT_OFFS):
        blk = bytes(data[off:off + DLG_W * DLG_H])
        render(blk, od / f"monst_dlg_{name}_jp.png")
        render(redraw_variant(blk), od / f"monst_dlg_{name}_en.png")
    print(f"previews -> {od}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fold"); p.add_argument("track")
    p = sub.add_parser("extract"); p.add_argument("track"); p.add_argument("out")
    p = sub.add_parser("preview"); p.add_argument("track"); p.add_argument("outdir")
    a = ap.parse_args()
    if a.cmd == "fold":
        raise SystemExit(cmd_fold(a.track))
    if a.cmd == "extract":
        cmd_extract(a.track, a.out)
    if a.cmd == "preview":
        cmd_preview(a.track, a.outdir)
