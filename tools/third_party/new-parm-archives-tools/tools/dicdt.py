#!/usr/bin/env python3
"""dicdt.py — translate the Monster-Encyclopedia text in FIELD/DICDT.DAT.

DICDT.DAT ("dictionary data") is the museum monster-encyclopedia's data file. Its
header is an 8-entry BE-u32 **section table** (offsets into the file):
  [0]=0x20 [1].. [4]=0x29bd0 [5]=0x29c3c NAMES [6]=0x2a0e8 LOCALES [7]=0x2a71c .. EOF
Section 5 = the monster NAME list, section 6 = the habitat/LOCALE list — each a
**packed, NUL-separated** list of strings in the **standard Grandia 16x16 font
encoding** (`Grandia16x16.tbl`; kanji 2 B, kana/Roman 1 B). The viewer indexes
entries by ordinal (sequential NUL walk) — verified there is NO pointer table and
NO absolute reference into these sections except the header — so entries may be any
length; on a size change we just rewrite the block and fix the header offsets for
all later sections (a clean relocate).

English uses the tbl's **full-width UPPERCASE Roman** (A-Z=0x2B..0x44, space=0x20,
digits=0x21..0x2A, !=0xED ?=0xEC); there is no half-width/lowercase in this tbl.

Subcommands:
  dump   DICDT.DAT [--section 5|6]      print the section's strings (idx, hex, JP)
  patch  DICDT.DAT MAP.json OUT.DAT [--section 5]
         MAP.json = {"<idx>": "ENGLISH", ...}; rebuilds the section (untouched
         entries kept verbatim), relocates later sections, fixes the header.
"""
import json
import struct
import sys
from pathlib import Path

TBL = (Path(__file__).resolve().parent / "vendor/GrandiaTranslation/"
       "GrandiaTranslationTools/Grandia16x16.tbl")
NAMES_SECTION = 5


def load_tbl():
    fwd = {}
    for line in open(TBL, encoding="utf-8", errors="replace"):
        if "=" not in line:
            continue
        code, _, ch = line.rstrip("\n").partition("=")
        code = code.strip()
        if ch and len(code) in (2, 4):
            try:
                fwd[bytes.fromhex(code)] = ch
            except ValueError:
                pass
    rev = {}
    for code, ch in fwd.items():
        rev.setdefault(ch, code)
    return fwd, rev


FWD, REV = load_tbl()


def decode(b):
    # 0x03 = switch to 8x16 half-width ASCII for the rest of the entry (English names).
    if b[:1] == b"\x03":
        try:
            return b[1:].decode("ascii")
        except UnicodeDecodeError:
            pass
    out = ""
    i = 0
    while i < len(b):
        two, one = b[i:i + 2], b[i:i + 1]
        if two in FWD and not (one in FWD and b[i] < 0x80):
            out += FWD[two]; i += 2
        elif one in FWD:
            out += FWD[one]; i += 1
        else:
            out += f"<{b[i]:02x}>"; i += 1
    return out


# The encyclopedia text renderer honours control 0x03 = switch to the 8x16
# half-width ASCII font (proven in-game: mixed-case, lowercase, long names fit
# the list box without clipping — unlike the full-width 16x16 Roman, which the
# tbl maps at 0x2B.. but which clips past ~9 chars). So English = 0x03 + ASCII.
def encode(text, halfwidth=True):
    if halfwidth:
        return b"\x03" + text.encode("ascii")
    # full-width fallback (16x16 tbl, UPPERCASE only, clips past ~9 chars)
    out = bytearray()
    for ch in text.upper():
        if ch == " ":
            out += REV.get(" ", REV.get("　")); continue
        full = chr(ord(ch) + 0xFEE0) if "0" <= ch <= "9" or "A" <= ch <= "Z" else ch
        code = REV.get(full) or REV.get(ch)
        if code is None:
            raise ValueError(f"cannot encode {ch!r} (text={text!r})")
        out += code
    return bytes(out)


def sections(d):
    hdr = list(struct.unpack_from(">8I", d, 0))
    spans = []
    for i, off in enumerate(hdr):
        end = hdr[i + 1] if i + 1 < len(hdr) else len(d)
        spans.append((off, end))
    return hdr, spans


def split_names(block):
    """Split a packed NUL-separated block into (entries, trailing_pad_bytes)."""
    entries = []
    i = 0
    while i < len(block):
        e = block.find(b"\x00", i)
        if e < 0:
            entries.append(block[i:]); i = len(block); break
        if e == i:
            # run of NULs from here = trailing pad
            if all(x == 0 for x in block[i:]):
                return entries, len(block) - i
            entries.append(b""); i = e + 1; continue
        entries.append(block[i:e]); i = e + 1
    return entries, 0


def cmd_dump(args):
    d = Path(args.dat).read_bytes()
    hdr, spans = sections(d)
    s = args.section
    off, end = spans[s]
    entries, pad = split_names(d[off:end])
    print(f"section {s}: 0x{off:x}..0x{end:x} ({end-off} B), "
          f"{len(entries)} entries, {pad} pad")
    for i, e in enumerate(entries):
        print(f"  {i:3d}: {decode(e)}")


def cmd_patch(args):
    d = Path(args.dat).read_bytes()
    hdr, spans = sections(d)
    s = args.section
    off, end = spans[s]
    entries, pad = split_names(d[off:end])
    mapping = json.loads(Path(args.map).read_text())
    for k, en in mapping.items():
        i = int(k)
        if not (0 <= i < len(entries)):
            sys.exit(f"index {i} out of range (0..{len(entries)-1})")
        entries[i] = encode(en)
    new_block = b"\x00".join(entries) + b"\x00"
    delta = len(new_block) - (end - off)
    # rebuild file: head + new section + tail (later sections), fix header offsets
    out = bytearray(d[:off]) + new_block + d[end:]
    for i in range(s + 1, len(hdr)):
        struct.pack_into(">I", out, i * 4, hdr[i] + delta)
    Path(args.out).write_bytes(out)
    print(f"section {s}: {len(entries)} entries, block {end-off} -> {len(new_block)} B "
          f"(delta {delta:+d}); file {len(d)} -> {len(out)} B")
    print(f"  patched {len(mapping)} entries; later section offsets += {delta}")


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    du = sub.add_parser("dump"); du.add_argument("dat")
    du.add_argument("--section", type=int, default=NAMES_SECTION); du.set_defaults(fn=cmd_dump)
    pa = sub.add_parser("patch"); pa.add_argument("dat"); pa.add_argument("map"); pa.add_argument("out")
    pa.add_argument("--section", type=int, default=NAMES_SECTION); pa.set_defaults(fn=cmd_patch)
    a = p.parse_args(argv[1:]); a.fn(a)


if __name__ == "__main__":
    main(sys.argv)
