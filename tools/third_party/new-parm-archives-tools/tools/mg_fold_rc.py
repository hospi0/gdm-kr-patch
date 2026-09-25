#!/usr/bin/env python3
"""Fold the English minigame assets into an RC track (in place, size-preserving).

The 8 authored files (all-English arcade title screens, docs/mgame-format.md sessions 3-9)
ship as xdelta3 deltas in patches/mgame/<NAME>.xdelta3 against the VANILLA file bytes. The
RC pipeline never touches these files, so the copy already on the track IS vanilla: extract
it, apply the delta, verify size, and write it back over the same sectors (no relocation, so
this composes with the theater integration's track-derived FAD constants in any order).

  mg_fold_rc.py --track output/rc_NN/Track1.bin
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import iso

ROOT = Path(__file__).resolve().parent.parent
PATCH_DIR = ROOT / "patches/mgame"


def extract(f, name):
    hit = iso.find(f, name)
    if not hit:
        raise SystemExit(f"{name}: not found in track ISO directory")
    _, lba, size = hit
    out = bytearray()
    for s in range((size + iso.USER_DATA - 1) // iso.USER_DATA):
        f.seek(iso.raw_offset(lba + s))
        out += f.read(iso.USER_DATA)
    return bytes(out[:size]), lba, size


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track", required=True, help="Track1.bin to patch in place")
    a = ap.parse_args()

    import json
    manifest = json.loads((PATCH_DIR / "manifest.json").read_text())
    deltas = sorted(PATCH_DIR.glob("*.xdelta3"))
    if not deltas:
        raise SystemExit(f"no deltas under {PATCH_DIR}")
    with open(a.track, "r+b") as f, tempfile.TemporaryDirectory() as td:
        for delta in deltas:
            name = delta.name[: -len(".xdelta3")]
            m = manifest[name]
            cur, lba, size = extract(f, name)
            cur_md5 = hashlib.md5(cur).hexdigest()
            # post_fold_md5s = states where a LATER build step (e.g. step 5b
            # pW7_mgame_text_fold) patched text on top of the English art —
            # equally final; skip on re-runs so the chain stays idempotent.
            if cur_md5 == m["english_md5"] or cur_md5 in m.get("post_fold_md5s", []):
                print(f"{name}: already English on this track — skipping")
                continue
            if cur_md5 != m["vanilla_md5"]:
                raise SystemExit(
                    f"{name}: track bytes are neither vanilla nor English (md5 {cur_md5}) — "
                    "another step modified this file; refusing to patch")
            src = Path(td) / f"src_{name}"
            dst = Path(td) / f"dst_{name}"
            src.write_bytes(cur)
            subprocess.run(["xdelta3", "-d", "-f", "-s", src, delta, dst], check=True)
            data = dst.read_bytes()
            if len(data) != size or hashlib.md5(data).hexdigest() != m["english_md5"]:
                raise SystemExit(f"{name}: delta output doesn't match the recorded English asset")
            for i in range((size + iso.USER_DATA - 1) // iso.USER_DATA):
                f.seek(iso.raw_offset(lba + i))
                f.write(data[i * iso.USER_DATA:(i + 1) * iso.USER_DATA])
            print(f"{name}: English asset folded in place @LBA {lba} ({size}B)")
    print(f"minigame fold complete -> {a.track}")


if __name__ == "__main__":
    main()
