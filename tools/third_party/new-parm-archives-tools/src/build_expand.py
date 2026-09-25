#!/usr/bin/env python3
"""Text-EXPANSION build permutations for Digital Museum E800.

Findings (docs/attempts-step1.md): in-place/equal works, but growing a file crashes unless the
MDT header CD-sector fields are corrected. Triangulated: header 0x180 = (A, B) and 0x1F4.w0 = A,
where A = ceil(end_of_graphics / 2048), B = footer sectors, A + B = total file sectors. Our
reconstructor updates end_of_graphics (0x1FC) but not 0x180/0x1F4 -> stale sector count -> the
game reads one sector short on a grown file -> crash. This tool fixes those fields, then relocates
the (now larger) file to the end of the track.

Modes:
  pad   : keep dialogue ORIGINAL, pad the SCN by N bytes to force a bigger file (clean test).
  grow  : replace the first dialogue box with ~N bytes of English (practical test).

Flags: --fix-sectors {full,w0,none}, and always relocates (expansion needs room).
"""
from __future__ import annotations

import argparse, glob, shutil, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CP = ROOT / "tools/vendor/GrandiaTranslation/GrandiaTranslationTools/target/classes"
sys.path.insert(0, str(ROOT / "src"))
import iso  # noqa: E402
import relayout  # noqa: E402

DLG = bytes([0x0F, 0x03, 0x0A, 0x0C, 0x00, 0x02])


def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr); raise SystemExit("cmd failed: " + " ".join(map(str, a)))
    return r.stdout


def java(*a): return sh("java", "-cp", str(CP), "com.grandia.cli.MDTParserCLI", *a)
def find_bin(n): return glob.glob(str(ROOT / f"input/**/*Track {n}*.bin"), recursive=True)[0]


def fix_sectors(mdt: bytearray, how: str):
    total = (len(mdt) + 2047) // 2048
    end_graphics = struct.unpack(">I", mdt[0x1FC:0x200])[0]
    A = (end_graphics + 2047) // 2048
    B = total - A
    if how in ("full", "w0"):
        struct.pack_into(">I", mdt, 0x180, A)
        struct.pack_into(">I", mdt, 0x1F4, A)
    if how == "full":
        struct.pack_into(">I", mdt, 0x184, B)
    return A, B, total


SCREEN_BREAKS = {
    "native": bytes([0x02, 0x0F, 0x03, 0x0A, 0x0C, 0x00, 0x00]),       # 016's (artifacts)
    "min":    bytes([0x02]),                                            # bare new-box
    "cfg":    bytes([0x02, 0x0F, 0x03, 0x0A, 0x0C, 0x00, 0x02]),        # reuse box-1 config
    "pause":  bytes([0x0E]),                                            # pause, no box reset
}


def grow_first_box(piece0: Path, n_bytes: int, seg_lines: int = 0, brk: str = "native"):
    """Grow the first box to ~n_bytes English. If seg_lines>0, paginate with native screen
    breaks (0x02 + sub-header) every seg_lines lines to avoid vertical overflow."""
    b = bytearray(piece0.read_bytes())
    i = b.find(DLG); s = i + 6; e = b.index(0x07, s)
    words = ("Hello brave traveler this is the expanded English intro proving that a dialogue box "
             "can now hold far more text than the original Japanese after they fell into the "
             "ancient ruins below where forgotten secrets sleep and a grand adventure begins now").split()
    out = bytearray([0x03]); line = ""; nlines = 0
    for w in words:
        if len(out) + len(line) + len(w) + 3 > n_bytes:
            break
        if line and len(line) + 1 + len(w) > 22:
            out += line.encode(); nlines += 1
            if seg_lines and nlines % seg_lines == 0:
                out += SCREEN_BREAKS[brk]
            else:
                out.append(0x01)
            out.append(0x03); line = w
        else:
            line = (line + " " + w).strip()
    out += line.encode()
    b[s:e] = bytes(out)
    piece0.write_bytes(b)
    return e - s, len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt", required=True)
    ap.add_argument("--mode", choices=["pad", "grow"], required=True)
    ap.add_argument("--n", type=int, default=2300, help="pad bytes, or target English bytes for first box")
    ap.add_argument("--fix-sectors", choices=["full", "w0", "none"], default="full")
    ap.add_argument("--seg-lines", type=int, default=0, help="paginate every N lines with a screen break")
    ap.add_argument("--break", dest="brk", choices=["native","min","cfg","pause"], default="native")
    a = ap.parse_args()

    out = ROOT / f"output/{a.attempt}"; w = out / "work"
    if w.exists(): shutil.rmtree(w)
    for d in ["in", "parts", "pieces", "recon", "mdtout"]:
        (w / d).mkdir(parents=True, exist_ok=True)
    bin1, bin2 = find_bin(1), find_bin(2)

    sh(sys.executable, str(ROOT / "src/iso.py"), "extract", bin1, "E800.MDT", str(w / "in/E800.MDT"))
    java("parse-mdt", str(w / "in"), str(w / "parts"), ".MDT", "big")

    if a.mode == "pad":
        scn = w / "parts/E800.SCN"; scn.write_bytes(scn.read_bytes() + b"\x00" * a.n)
        for ext in ["HEADER", "PRESCRIPT", "OFS", "SCN", "GRAPHICS", "FOOTER"]:
            shutil.copy(w / f"parts/E800.{ext}", w / "recon")
    else:
        java("parse-script", str(w / "parts/E800.SCN"), str(w / "parts/E800.OFS"), str(w / "pieces"))
        old, new = grow_first_box(w / "pieces/0", a.n, a.seg_lines, a.brk)
        print(f"first box {old}B -> {new}B (+{new-old})")
        java("reconstruct-script", str(w / "pieces"), str(w / "parts/E800.OFS"), str(w / "recon"))
        for ext in ["HEADER", "PRESCRIPT", "GRAPHICS", "FOOTER"]:
            shutil.copy(w / f"parts/E800.{ext}", w / "recon")

    java("reconstruct-mdt", str(w / "recon"), str(w / "mdtout"))
    mdt = bytearray((w / "mdtout/E800.MDT").read_bytes())
    sectors = (len(mdt) + 2047) // 2048
    A, B, total = fix_sectors(mdt, a.fix_sectors)
    (w / "mdtout/E800.fixed.MDT").write_bytes(mdt)
    print(f"MDT {len(mdt)}B = {sectors} sectors; fix={a.fix_sectors} -> 0x180=({A},{B}) total={total}")

    # relocate (always) to end of track
    relayout.relocate_and_grow(bin1, "E800.MDT", str(w / "mdtout/E800.fixed.MDT"), str(out / "Track1.bin"))
    shutil.copy(bin2, out / "Track2.bin")
    (out / "Grandia-DM-patched.cue").write_text(
        'FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
        'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')
    print(f"built output/{a.attempt}  mode={a.mode} n={a.n} fix={a.fix_sectors}")


if __name__ == "__main__":
    main()
