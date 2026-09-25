#!/usr/bin/env python3
"""Decode Grandia dialogue bytes to readable Japanese using Grandia16x16.tbl.

Splits a script piece into dialogue boxes (portrait-started) and decodes each box's text so we can
read the real script and translate it. Control codes are shown as markers; portrait codes show the
speaker position (left/middle/right).

    decode.py <piece_file>            # decode every box in a script piece

This is the Step 2 extraction helper: read the real per-box Japanese (with speaker) so each box can
be translated to match its speaker (fixes "wrong people talking").
"""
from __future__ import annotations

import sys
from pathlib import Path

import subst

TBL = Path(__file__).resolve().parent.parent / \
    "tools/vendor/GrandiaTranslation/GrandiaTranslationTools/Grandia16x16.tbl"
POS = {0x03: "left", 0x12: "middle", 0x21: "right"}


def load_table() -> dict[int, str]:
    table = {}
    for line in TBL.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        try:
            key = int(k, 16)
        except ValueError:
            continue
        table[key] = v
    return table


def decode_box(box: bytes, table: dict[int, str]) -> str:
    out = []
    i = 6  # skip the starting portrait code
    n = len(box)
    ascii_font = False  # 0x03 -> 8x16 ASCII, 0x04 -> 16x16
    while i < n:
        c = box[i]
        if c == subst.END:
            break
        if subst._is_portrait(box, i):
            out.append(f"⟨{POS.get(box[i+1], '?')}⟩"); i += 6
        elif c == 0x03:
            ascii_font = True; i += 1
        elif c == 0x04:
            ascii_font = False; i += 1
        elif c == 0x01:
            out.append("\n      "); i += 1
        elif c == 0x02:
            out.append(" ⟦box⟧ "); i += 1
        elif c == 0x0E:
            out.append("·"); i += 1
        elif c <= 0x0F:
            out.append(""); i += 1
        elif ascii_font:
            out.append(chr(c) if 0x20 <= c <= 0x7E else "□"); i += 1
        elif 0x10 <= c <= 0x1F:
            key = (c << 8) | box[i + 1]
            out.append(table.get(key, table.get(key & 0xFFFF, "□"))); i += 2
        else:
            out.append(table.get(c, "□")); i += 1
    return "".join(out)


def main() -> int:
    table = load_table()
    data = Path(sys.argv[1]).read_bytes()
    i = 0
    box_no = 0
    while i < len(data):
        if subst._is_portrait(data, i):
            try:
                end = data.index(subst.END, i + 6)
            except ValueError:
                break
            speaker = POS.get(data[i + 1], "?")
            text = decode_box(data[i:end + 1], table)
            print(f"[{box_no:2}] portrait={speaker:6} | {text}")
            box_no += 1
            i = end + 1
        else:
            i += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
