#!/usr/bin/env python3
"""Relocate-and-grow a file on a MODE1/2352 Saturn track to allow arbitrary-length content.

The data track is full and files butt against each other, so a larger rebuilt .MDT cannot fit
in place. The lowest-risk fix: append fresh sectors at the END of the track, write the larger
MDT there, and repoint ONLY that file's ISO9660 directory record (extent LBA + data length).
Every other file keeps its original LBA, so nothing else shifts. We also bump the PVD volume
space size so the filesystem covers the appended sectors.

This works IF the game loads the file through the CD filesystem (by name) rather than a
hardcoded LBA. The YMIR test on the output build confirms which.

Synthesized sectors get a valid sync + BCD MSF address + mode byte + 2048 data, with the
EDC/ECC area left zero (emulators don't verify it — confirmed by the output/001 test).

Usage:
    relayout.py --bin <track1.bin> --name <FILE.MDT> --mdt <rebuilt.MDT> --out <patched.bin>
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys

import iso

RAW_SECTOR = iso.RAW_SECTOR
USER_DATA = iso.USER_DATA


def _bcd(n: int) -> int:
    return ((n // 10) << 4) | (n % 10)


def make_raw_sector(lba: int, data: bytes) -> bytes:
    """Build a full 2352-byte Mode 1 sector (sync + MSF + mode + data + zeroed EDC/ECC)."""
    if len(data) > USER_DATA:
        raise ValueError("data exceeds 2048 bytes")
    s = bytearray(RAW_SECTOR)
    # 12-byte sync: 00 FF*10 00
    s[0] = 0x00
    for i in range(1, 11):
        s[i] = 0xFF
    s[11] = 0x00
    # MSF address (absolute = lba + 150), BCD
    amin = lba + 150
    s[12] = _bcd(amin // (60 * 75))
    s[13] = _bcd((amin // 75) % 60)
    s[14] = _bcd(amin % 75)
    s[15] = 0x01  # mode 1
    s[16:16 + len(data)] = data  # remaining EDC/ECC bytes stay zero
    return bytes(s)


def _patch_u32_both(f, off: int, value: int) -> None:
    """Write an ISO9660 both-endian u32 (LE then BE) at raw offset `off`."""
    f.seek(off)
    f.write(struct.pack("<I", value))
    f.seek(off + 4)
    f.write(struct.pack(">I", value))


def relocate_and_grow(bin_in: str, name: str, mdt_path: str, bin_out: str) -> int:
    new_mdt = open(mdt_path, "rb").read()
    shutil.copyfile(bin_in, bin_out)

    with open(bin_out, "r+b") as f:
        if name.startswith("/"):
            # full-path match disambiguates duplicate basenames (e.g. /BATLE/TEXT2.BIN
            # vs /FIELD/TEXT2.BIN). walk_records yields (path, lba, size, rec_raw).
            rec = None
            for path, lba, size, rec_raw in iso.walk_records(f):
                if path.upper() == name.upper():
                    rec = {"path": path, "lba": lba, "size": size, "rec_raw": rec_raw}
                    break
        else:
            rec = iso.find_record(f, name)
        if not rec:
            print(f"NOT FOUND in filesystem: {name}", file=sys.stderr)
            return 3
        f.seek(0, 2)
        size_bytes = f.tell()
        if size_bytes % RAW_SECTOR != 0:
            print(f"WARNING: track size {size_bytes} not a multiple of {RAW_SECTOR}", file=sys.stderr)
        new_lba = size_bytes // RAW_SECTOR
        n_sectors = (len(new_mdt) + USER_DATA - 1) // USER_DATA

        # Append synthesized sectors at the end of the track.
        f.seek(0, 2)
        for i in range(n_sectors):
            chunk = new_mdt[i * USER_DATA:(i + 1) * USER_DATA]
            f.write(make_raw_sector(new_lba + i, chunk))

        # Repoint this file's directory record: extent LBA (off+2) and data length (off+10).
        _patch_u32_both(f, rec["rec_raw"] + 2, new_lba)
        _patch_u32_both(f, rec["rec_raw"] + 10, len(new_mdt))

        # Extend the PVD volume space size to cover the appended sectors.
        new_total = new_lba + n_sectors
        _patch_u32_both(f, iso.pvd_volume_space_raw(), new_total)

    print(f"relocated {name}: {rec['lba']} (size {rec['size']}) -> LBA {new_lba} "
          f"(size {len(new_mdt)}, {n_sectors} sectors); volume now {new_total} sectors")
    print(f"wrote {bin_out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bin", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--mdt", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    return relocate_and_grow(a.bin, a.name, a.mdt, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
