#!/usr/bin/env python3
"""mg_stb.py — (un)pack the Game-Room minigame archive format.

The minigame engine's asset containers (`MG*.STB`, and the `MG*.BIN` overlays)
all share one container layout: a **big-endian uint32 offset table** at the
file head. The FIRST offset is where the table ends / the first resource begins,
so `table_size/4` = number of table slots. Slots are filled with absolute file
offsets (BE u32), terminated by `0xffffffff`, then zero-padded to the table size.

Each used slot i points at sub-blob i; its length = offset[i+1] - offset[i]
(the terminator/EOF supplies the final length). Sub-blobs are raw resources
(graphics tiles, palettes, possibly a font + a text-index blob).

Subcommands:
  list   FILE                       print the offset table + per-blob size
  unpack FILE OUTDIR                 dump every sub-blob to OUTDIR/NNN.bin
  repack FILE OUTDIR NEWFILE        rebuild a container from OUTDIR/NNN.bin,
                                     CONSTANT-SIZE per blob (offsets unchanged).
                                     Refuses to write if any blob changed size.

Constant-size repack keeps every offset identical, which is the safe path for
in-place disc injection (no pointer recalputation, no growth-freeze).
"""
import struct
import sys
from pathlib import Path


def parse_table(data: bytes):
    """Return (offsets, table_size). offsets = list of (slot, off) used slots."""
    table_size = struct.unpack(">I", data[0:4])[0]
    if table_size % 4 != 0 or table_size < 4 or table_size > len(data):
        raise ValueError(f"implausible table_size {table_size:#x}")
    nslots = table_size // 4
    offsets = []
    for i in range(nslots):
        v = struct.unpack(">I", data[i * 4:i * 4 + 4])[0]
        if v == 0xFFFFFFFF:
            break
        if v == 0 and i > 0:
            break
        offsets.append((i, v))
    return offsets, table_size


def blob_spans(data: bytes):
    """Return list of (slot, start, end) for each sub-blob."""
    offsets, table_size = parse_table(data)
    spans = []
    for idx, (slot, off) in enumerate(offsets):
        end = offsets[idx + 1][1] if idx + 1 < len(offsets) else len(data)
        spans.append((slot, off, end))
    return spans


def cmd_list(path):
    data = Path(path).read_bytes()
    offsets, table_size = parse_table(data)
    print(f"{path}: {len(data)} bytes, table_size={table_size:#x} "
          f"({table_size//4} slots), {len(offsets)} used")
    for slot, start, end in blob_spans(data):
        size = end - start
        head = data[start:start + 12].hex()
        print(f"  [{slot:3d}] off={start:#08x} size={size:8d}  head={head}")


def cmd_unpack(path, outdir):
    data = Path(path).read_bytes()
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for slot, start, end in blob_spans(data):
        (out / f"{slot:03d}.bin").write_bytes(data[start:end])
    print(f"unpacked {path} -> {outdir} "
          f"({len(blob_spans(data))} blobs)")


def cmd_repack(path, outdir, newfile):
    data = bytearray(Path(path).read_bytes())
    out = Path(outdir)
    for slot, start, end in blob_spans(data):
        bp = out / f"{slot:03d}.bin"
        if not bp.exists():
            continue
        blob = bp.read_bytes()
        if len(blob) != end - start:
            raise SystemExit(
                f"slot {slot}: size changed {end-start} -> {len(blob)}; "
                f"constant-size repack only")
        data[start:end] = blob
    Path(newfile).write_bytes(data)
    print(f"repacked {path} -> {newfile} (constant-size)")


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "list":
        cmd_list(argv[2])
    elif cmd == "unpack":
        cmd_unpack(argv[2], argv[3])
    elif cmd == "repack":
        cmd_repack(argv[2], argv[3], argv[4])
    else:
        print(f"unknown command {cmd}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
