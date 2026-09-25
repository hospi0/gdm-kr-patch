#!/usr/bin/env python3
"""Minimal ISO9660 reader for a Sega Saturn MODE1/2352 .bin track.

Saturn discs store 2048 bytes of user data inside each 2352-byte raw sector
(12 sync + 3 address + 1 mode + 2048 data + 288 EDC/ECC). This module de-sectors
that layout and walks the ISO9660 filesystem so we can locate/extract files (the
.MDT archives) by name, and map a file back to its raw byte offset for injection.

CLI:
    iso.py list   <track1.bin>                 # list all files (path, LBA, size)
    iso.py find   <track1.bin> <NAME>          # print LBA + size for NAME
    iso.py extract <track1.bin> <NAME> <out>   # extract NAME to <out>
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

RAW_SECTOR = 2352
USER_DATA = 2048
SYNC_HEADER = 16  # 12 sync + 3 address + 1 mode, before user data (Mode 1)


def raw_offset(lba: int) -> int:
    """Raw byte offset of the start of a logical sector's USER DATA in the .bin."""
    return lba * RAW_SECTOR + SYNC_HEADER


def read_sector(f, lba: int) -> bytes:
    f.seek(raw_offset(lba))
    return f.read(USER_DATA)


def read_bytes(f, lba: int, length: int) -> bytes:
    """Read `length` bytes of logical data starting at sector `lba`, spanning sectors."""
    out = bytearray()
    n = (length + USER_DATA - 1) // USER_DATA
    for i in range(n):
        out += read_sector(f, lba + i)
    return bytes(out[:length])


def _both_endian_le(data: int) -> int:
    """ISO9660 stores many fields both-endian; we just read the little-endian half."""
    return data


def _parse_dir_records(block: bytes):
    """Yield (name, lba, size, is_dir) from a directory extent block."""
    i = 0
    while i < len(block):
        rec_len = block[i]
        if rec_len == 0:
            # padding to end of a logical sector; jump to next sector boundary
            next_boundary = ((i // USER_DATA) + 1) * USER_DATA
            if next_boundary >= len(block):
                break
            i = next_boundary
            continue
        rec = block[i:i + rec_len]
        ext_lba = struct.unpack_from("<I", rec, 2)[0]
        size = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        name = rec[33:33 + name_len]
        is_dir = bool(flags & 0x02)
        if name == b"\x00":
            disp = "."
        elif name == b"\x01":
            disp = ".."
        else:
            disp = name.decode("ascii", "replace").split(";")[0]
        yield disp, ext_lba, size, is_dir
        i += rec_len


def walk(f):
    """Yield (path, lba, size) for every file in the ISO9660 tree."""
    # Primary Volume Descriptor at logical sector 16; root dir record at offset 156.
    pvd = read_sector(f, 16)
    if pvd[1:6] != b"CD001":
        raise ValueError("No CD001 signature in PVD; not ISO9660 or wrong sector format.")
    root = pvd[156:156 + 34]
    root_lba = struct.unpack_from("<I", root, 2)[0]
    root_size = struct.unpack_from("<I", root, 10)[0]

    stack = [("", root_lba, root_size)]
    while stack:
        prefix, lba, size = stack.pop()
        block = read_bytes(f, lba, size)
        for name, ext_lba, ext_size, is_dir in _parse_dir_records(block):
            if name in (".", ".."):
                continue
            path = f"{prefix}/{name}"
            if is_dir:
                stack.append((path, ext_lba, ext_size))
            else:
                yield path, ext_lba, ext_size


def find(f, target: str):
    for path, lba, size in walk(f):
        if path.rsplit("/", 1)[-1].upper() == target.upper():
            return path, lba, size
    return None


def iter_dir_records(f, dir_lba: int, dir_size: int):
    """Yield (name_bytes, ext_lba, size, is_dir, rec_raw_off) for a directory extent.

    rec_raw_off is the absolute byte offset in the .bin of the start of the directory
    record, so callers can patch its extent-LBA / size fields in place. ISO9660 records
    never cross a 2048-byte logical-sector boundary, so the field offsets stay in user data.
    """
    block = read_bytes(f, dir_lba, dir_size)
    i = 0
    while i < len(block):
        rec_len = block[i]
        if rec_len == 0:
            next_boundary = ((i // USER_DATA) + 1) * USER_DATA
            if next_boundary >= len(block):
                break
            i = next_boundary
            continue
        rec = block[i:i + rec_len]
        ext_lba = struct.unpack_from("<I", rec, 2)[0]
        size = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        name = rec[33:33 + name_len]
        sec = dir_lba + (i // USER_DATA)
        within = i % USER_DATA
        rec_raw = sec * RAW_SECTOR + SYNC_HEADER + within
        yield name, ext_lba, size, bool(flags & 0x02), rec_raw
        i += rec_len


def walk_records(f):
    """Like walk(), but also yields each file's directory-record raw offset."""
    pvd = read_sector(f, 16)
    root = pvd[156:156 + 34]
    root_lba = struct.unpack_from("<I", root, 2)[0]
    root_size = struct.unpack_from("<I", root, 10)[0]
    stack = [("", root_lba, root_size)]
    while stack:
        prefix, lba, size = stack.pop()
        for name, ext_lba, ext_size, is_dir, rec_raw in iter_dir_records(f, lba, size):
            if name in (b"\x00", b"\x01"):
                continue
            disp = name.decode("ascii", "replace").split(";")[0]
            path = f"{prefix}/{disp}"
            if is_dir:
                stack.append((path, ext_lba, ext_size))
            else:
                yield path, ext_lba, ext_size, rec_raw


def find_record(f, target: str):
    """Return {path, lba, size, rec_raw} for a file by name, or None."""
    for path, lba, size, rec_raw in walk_records(f):
        if path.rsplit("/", 1)[-1].upper() == target.upper():
            return {"path": path, "lba": lba, "size": size, "rec_raw": rec_raw}
    return None


def pvd_volume_space_raw() -> int:
    """Raw .bin offset of the PVD 'volume space size' field (both-endian u32)."""
    return 16 * RAW_SECTOR + SYNC_HEADER + 80


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, bin_path = sys.argv[1], sys.argv[2]
    with open(bin_path, "rb") as f:
        if cmd == "list":
            for path, lba, size in walk(f):
                print(f"{lba:>8}  {size:>10}  {path}")
        elif cmd == "find":
            hit = find(f, sys.argv[3])
            if not hit:
                print(f"NOT FOUND: {sys.argv[3]}", file=sys.stderr)
                return 3
            path, lba, size = hit
            print(f"path={path} lba={lba} size={size} raw_offset={raw_offset(lba)}")
        elif cmd == "extract":
            hit = find(f, sys.argv[3])
            if not hit:
                print(f"NOT FOUND: {sys.argv[3]}", file=sys.stderr)
                return 3
            _, lba, size = hit
            data = read_bytes(f, lba, size)
            Path(sys.argv[4]).write_bytes(data)
            print(f"extracted {sys.argv[3]} ({size} bytes, lba {lba}) -> {sys.argv[4]}")
        else:
            print(f"unknown command: {cmd}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
