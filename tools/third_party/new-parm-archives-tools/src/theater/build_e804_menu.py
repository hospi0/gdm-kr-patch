#!/usr/bin/env python3
"""Dedicated E804 theater test-disc builder (theater lane; NOT subst.py / _fit.py).

Builds E804.MDT in place (equal-length, no growth) on a fresh JP track so it is testable from the
VANILLA savestates (relocated/grown builds aren't — the savestate's resident dir points at the old
LBA). Translates the room banners via the normal names path, and rebuilds the 600a *menu box*
byte-exact: each line becomes one `0x03`(8x16)+ASCII run padded to the JP line's byte length, so the
※※ 16x16 decorations (which garble under 8x16) are replaced and the op tables after the box are
untouched. Renders English on vanilla SCNRL via the per-run 0x03 switch (same as the "THEATER"
banner). Output: output/<attempt>/  (default t002).

  python3 src/theater/build_e804_menu.py --attempt t002
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "script"))
import build_mdt  # noqa: E402  (sh, java, find_bin, apply_en, RECON_PARTS)
import iso  # noqa: E402


def line(text: str, n: int) -> bytes:
    """0x03 (switch to 8x16) + ASCII centered in (n-1) bytes (so the run is exactly n bytes)."""
    body = text.center(n - 1)[: n - 1]
    return b"\x03" + body.encode("ascii")


def build_600a_box() -> bytes:
    """The 74-byte menu box content: 0x05 + L1(21) + 0x01 + L2(24) + 0x01 + L3(24) + 0x07 + 0x00.
    Lengths match the vanilla JP box exactly (in-place, no shift)."""
    box = b"\x05" + line("** Back **", 21) + b"\x01" \
        + line("** Listen to drama **", 24) + b"\x01" \
        + line("** View the guide **", 24) + b"\x07\x00"
    assert len(box) == 74, len(box)
    return box


def build_desc_box() -> bytes:
    """The 50-byte guide-description box (shown by 'View the guide'). JP:
    ドラマを聞くには チケットが必要です / チケットは ギドのアイテムショップで / 売っています.
    Equal length (50B): 0x03 + L1 + 0x01 + 0x03 + L2 + 0x07 + 0x00 (1+L1+1+1+L2+1+1).
    ギド = "Guido" per the dictionary (src/dict_cli.py lookup), matching E804_en.py RUN_TEXTS."""
    box = b"\x03" + b"Tickets to hear a drama" + b"\x01" \
        + b"\x03" + b"sold at Guido's shop. " + b"\x07\x00"
    assert len(box) == 50, len(box)
    return box


def patch_600a(piece: bytes) -> bytes:
    """Rebuild 600a replacing BOTH text boxes (menu 74B + guide-desc 50B) with English,
    byte-exact, preserving every cmd/op token between them."""
    import subst
    toks = subst.parse_box_commands(piece)
    out = bytearray()
    menu_done = desc_done = False
    for kind, payload in toks:
        if kind == "box" and len(payload) == 0x4A and not menu_done:
            out += b"\x20\x4a" + build_600a_box(); menu_done = True
        elif kind == "box" and len(payload) == 0x32 and not desc_done:
            out += b"\x20\x32" + build_desc_box(); desc_done = True
        elif kind == "box":
            out += (0x2000 | len(payload)).to_bytes(2, "big") + payload
        else:
            out += payload
    assert menu_done and desc_done, f"menu={menu_done} desc={desc_done}"
    assert len(out) == len(piece), f"{len(out)} != {len(piece)}"
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt", default="t002")
    a = ap.parse_args()

    base, name = "E804", "E804.MDT"
    outdir = ROOT / f"output/{a.attempt}"
    outdir.mkdir(parents=True, exist_ok=True)
    bin1 = build_mdt.find_bin(1)
    bin2 = build_mdt.find_bin(2)
    work_track = outdir / "Track1.bin"
    shutil.copy(bin1, work_track)
    shutil.copy(bin2, outdir / "Track2.bin")
    (outdir / "Grandia-DM-patched.cue").write_text(
        'FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
        'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')

    wd = outdir / "work" / base
    for d in ["", "parts", "pieces", "recon", "mdtout"]:
        (wd / d).mkdir(parents=True, exist_ok=True)
    build_mdt.sh(sys.executable, str(ROOT / "src/iso.py"), "extract", str(work_track), name, str(wd / name))
    orig_size = (wd / name).stat().st_size
    build_mdt.java("parse-mdt", str(wd), str(wd / "parts"), ".MDT", "big")
    build_mdt.java("parse-script", str(wd / f"parts/{base}.SCN"), str(wd / f"parts/{base}.OFS"), str(wd / "pieces"))

    # banners (c000/d000/e001) via the normal equal-length names path; SKIP 600a (prefix "6")
    build_mdt.apply_en(base, wd / "pieces", names_only=True, skip_prefixes=("6",))
    # custom 600a menu box (byte-exact, equal-length)
    p600a = wd / "pieces" / "600a"
    new = patch_600a(p600a.read_bytes())
    assert len(new) == p600a.stat().st_size, "600a length changed!"
    p600a.write_bytes(new)
    print("  E804 600a: menu box rebuilt (English, equal-length)")

    build_mdt.java("reconstruct-script", str(wd / "pieces"), str(wd / f"parts/{base}.OFS"), str(wd / "recon"))
    for ext in build_mdt.RECON_PARTS:
        shutil.copy(wd / f"parts/{base}.{ext}", wd / "recon")
    build_mdt.java("reconstruct-mdt", str(wd / "recon"), str(wd / "mdtout"))

    fixed = wd / "mdtout" / name
    mdt = fixed.read_bytes()
    if len(mdt) > orig_size:
        raise SystemExit(f"E804 grew ({len(mdt)} > {orig_size}); would relocate (not savestate-testable)")
    with open(work_track, "rb") as f:
        rec = iso.find_record(f, name)
    build_mdt.sh(sys.executable, str(ROOT / "src/inject.py"), "--bin", str(work_track), "--mdt",
                 str(fixed), "--lba", str(rec["lba"]), "--out", str(work_track) + ".tmp",
                 "--max-bytes", str(orig_size))
    shutil.move(str(work_track) + ".tmp", work_track)
    print(f"built {outdir}/  (E804 in place at LBA {rec['lba']}, {len(mdt)}B <= {orig_size}B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
