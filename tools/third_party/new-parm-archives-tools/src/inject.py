#!/usr/bin/env python3
"""Sector-aware binary injection of a rebuilt .MDT into a MODE1/2352 Saturn track.

The disc is raw 2352-byte sectors (12 sync + 3 addr + 1 mode + 2048 data + 288 EDC/ECC),
NOT a flat 2048 image. So we cannot seek to lba*2048 and write contiguously: each 2048-byte
chunk of the file lives in a separate sector's user-data region at offset lba*2352+16.

We overwrite only the 2048-byte user-data area of each sector and leave the EDC/ECC stale.
Emulators (YMIR, Mednafen) do not verify Mode 1 EDC/ECC, so stale ECC is fine for testing.

In-place injection only works if the rebuilt MDT still fits in the file's original sector span
(its "hole"). E800.MDT butts directly against E804.MDT, leaving ~196 bytes of slack — so larger
text needs relocation/relayout (see docs/step1-limits.md), not this in-place path.

Usage:
    inject.py --bin <track1.bin> --mdt <rebuilt.MDT> --lba <N> --out <patched.bin>
              [--max-bytes <M>] [--allow-overflow]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

RAW_SECTOR = 2352
USER_DATA = 2048
SYNC_HEADER = 16


def inject(bin_path: str, mdt_path: str, lba: int, out_path: str,
           max_bytes: int | None, allow_overflow: bool) -> int:
    mdt = Path(mdt_path).read_bytes()
    if max_bytes is not None and len(mdt) > max_bytes and not allow_overflow:
        print(
            f"REFUSING: rebuilt MDT is {len(mdt)} bytes but the hole is {max_bytes} bytes "
            f"({len(mdt) - max_bytes} over). It would overrun the next file. Use relocation "
            f"or a track relayout, or pass --allow-overflow to force.",
            file=sys.stderr,
        )
        return 2

    shutil.copyfile(bin_path, out_path)
    n_sectors = (len(mdt) + USER_DATA - 1) // USER_DATA
    with open(out_path, "r+b") as f:
        for i in range(n_sectors):
            chunk = mdt[i * USER_DATA:(i + 1) * USER_DATA]
            if len(chunk) < USER_DATA:
                chunk = chunk + b"\x00" * (USER_DATA - len(chunk))
            f.seek((lba + i) * RAW_SECTOR + SYNC_HEADER)
            f.write(chunk)
    print(f"injected {len(mdt)} bytes ({n_sectors} sectors) at LBA {lba} -> {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bin", required=True)
    ap.add_argument("--mdt", required=True)
    ap.add_argument("--lba", required=True, type=int)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-bytes", type=int, default=None,
                    help="size of the file's hole; refuse to overrun it")
    ap.add_argument("--allow-overflow", action="store_true")
    a = ap.parse_args()
    return inject(a.bin, a.mdt, a.lba, a.out, a.max_bytes, a.allow_overflow)


if __name__ == "__main__":
    raise SystemExit(main())
