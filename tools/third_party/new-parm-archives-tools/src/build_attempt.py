#!/usr/bin/env python3
"""Reusable Step 1 build driver: extract E800 -> (optionally edit) -> reconstruct -> inject.

Keeps attempts reproducible and reduces hand-error while we isolate the black-screen bug.

    build_attempt.py --attempt 004 --mode inplace  --text "HELLO ..."
    build_attempt.py --attempt 003 --mode relocate            # no --text => unmodified E800
    build_attempt.py --attempt 005 --mode relocate --text-words 100

Modes:
    inplace   inject the rebuilt MDT at E800's original LBA (only valid if it still fits 246 sectors)
    relocate  append the rebuilt MDT at the track end and repoint its directory record

Output: a full bootable build in output/<attempt>/ (Track1.bin, Track2.bin, cue).
"""
from __future__ import annotations

import argparse
import glob
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CP = ROOT / "tools/vendor/GrandiaTranslation/GrandiaTranslationTools/target/classes"
E800_LBA = 31115
E800_ORIG_SIZE = 503808
DLG_HEADER = bytes([0x0F, 0x03, 0x0A, 0x0C, 0x00, 0x02])
FONT_SWITCH = 0x03
END_DLG = 0x07


def sh(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(f"command failed: {' '.join(map(str, args))}")
    return r.stdout


def java(*args):
    return sh("java", "-cp", str(CP), "com.grandia.cli.MDTParserCLI", *args)


def find_bin(which):
    return glob.glob(str(ROOT / f"input/**/*Track {which}*.bin"), recursive=True)[0]


LINE_BREAK = 0x01
SEG_BREAK = 0x02


def format_dialogue(text: str, wrap: int, seg_lines: int) -> bytes:
    """Build a native-structured dialogue body from plain words.

    Each line = 0x03 (font switch) + <=wrap ASCII chars; lines joined by 0x01 (line break);
    every seg_lines lines start a new screen separated by 0x02 (segment break). No leading
    0x07 (the caller keeps the box terminator).
    """
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > wrap:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)

    out = bytearray()
    for idx, line in enumerate(lines):
        if idx > 0:
            out.append(SEG_BREAK if idx % seg_lines == 0 else LINE_BREAK)
        out.append(FONT_SWITCH)
        out += line.encode("ascii", "replace")
    return bytes(out)


def edit_piece0(pieces_dir: Path, repl: bytes):
    p = pieces_dir / "0"
    b = bytearray(p.read_bytes())
    i = b.find(DLG_HEADER)
    if i < 0:
        raise SystemExit("dialogue header not found in piece 0")
    start = i + len(DLG_HEADER)
    end = b.index(END_DLG, start)
    old = end - start
    b[start:end] = repl
    p.write_bytes(b)
    return old, len(repl)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--attempt", required=True)
    ap.add_argument("--mode", choices=["inplace", "relocate"], required=True)
    ap.add_argument("--text", default=None, help="ASCII to inject (omit to leave E800 unmodified)")
    ap.add_argument("--text-words", type=int, default=None, help="use N words of marked filler")
    ap.add_argument("--wrap", type=int, default=0,
                    help="if >0, format text into lines of <=N chars with native control codes")
    ap.add_argument("--seg-lines", type=int, default=3, help="lines per screen segment when wrapping")
    a = ap.parse_args()

    out = ROOT / f"output/{a.attempt}"
    w = out / "work"
    if w.exists():
        shutil.rmtree(w)
    for d in ["", "parts", "pieces", "recon", "mdtout"]:
        (w / d).mkdir(parents=True, exist_ok=True)

    bin1, bin2 = find_bin(1), find_bin(2)

    # Extract + parse
    sh(sys.executable, str(ROOT / "src/iso.py"), "extract", bin1, "E800.MDT", str(w / "E800.MDT"))
    java("parse-mdt", str(w), str(w / "parts"), ".MDT", "big")

    plain = None
    if a.text_words is not None:
        sys.path.insert(0, str(ROOT / "src"))
        from limits_probe import filler  # type: ignore
        plain = filler(a.text_words)
    elif a.text is not None:
        plain = a.text

    if plain is not None:
        if a.wrap > 0:
            repl = format_dialogue(plain, a.wrap, a.seg_lines)
        else:
            repl = bytes([FONT_SWITCH]) + plain.encode("ascii", "replace")
        java("parse-script", str(w / "parts/E800.SCN"), str(w / "parts/E800.OFS"), str(w / "pieces"))
        old, new = edit_piece0(w / "pieces", repl)
        print(f"piece0 dialogue: {old}B -> {new}B (net {new-old:+d}); wrap={a.wrap} seg_lines={a.seg_lines}")
        java("reconstruct-script", str(w / "pieces"), str(w / "parts/E800.OFS"), str(w / "recon"))
        for ext in ["HEADER", "PRESCRIPT", "GRAPHICS", "FOOTER"]:
            shutil.copy(w / f"parts/E800.{ext}", w / "recon")
        java("reconstruct-mdt", str(w / "recon"), str(w / "mdtout"))
        mdt = w / "mdtout/E800.MDT"
    else:
        mdt = w / "E800.MDT"  # unmodified original

    size = mdt.stat().st_size
    sectors = (size + 2047) // 2048
    print(f"MDT to inject: {size} bytes ({sectors} sectors); original 246 sectors")

    track1_out = out / "Track1.bin"
    if a.mode == "inplace":
        sh(sys.executable, str(ROOT / "src/inject.py"), "--bin", bin1, "--mdt", str(mdt),
           "--lba", str(E800_LBA), "--out", str(track1_out), "--max-bytes", str(E800_ORIG_SIZE))
    else:
        sh(sys.executable, str(ROOT / "src/relayout.py"), "--bin", bin1, "--name", "E800.MDT",
           "--mdt", str(mdt), "--out", str(track1_out))

    shutil.copy(bin2, out / "Track2.bin")
    (out / "Grandia-DM-patched.cue").write_text(
        'FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
        'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n'
    )
    print(f"built output/{a.attempt}/  (mode={a.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
