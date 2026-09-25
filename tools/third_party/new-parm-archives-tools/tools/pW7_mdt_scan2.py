#!/usr/bin/env python3
"""Lane W7 pass 2: refined residual-JP filter over the pW7 MDT piece cache.

The rc build ships an 8x16-ASCII default font (SCNRL patch), so English dialogue is
raw ASCII bytes 0x20-0x7E — which the vanilla Grandia16x16.tbl glosses as kana
("the" -> hiragana). pW7_mdt_scan.py therefore over-reports. REAL residual Japanese
in a text run is evidence of either:
  - a 2-byte tbl code (lead 0x10-0x1F) that maps to kana/kanji, or
  - a single byte >= 0x7F that maps to kana/katakana in the tbl.
This pass re-walks output/.extract_work_pW7/<MDT>/pieces and reports only those.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import decode as decode_mod  # noqa: E402
import subst  # noqa: E402

WORK = ROOT / "output/.extract_work_pW7"


def jp_char(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch[0])
    return (0x3041 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF
            or o in (0x3005, 0x30FC, 0x3001, 0x3002))


def scan_piece(data: bytes, table) -> list[tuple[int, str]]:
    """Return (offset, decoded-context) for each real-JP cluster in the piece."""
    hits = []
    i, n = 0, len(data)
    run_jp = []  # (off, glyph)
    ascii_font = False
    while i < n:
        c = data[i]
        if subst._is_portrait(data, i):
            i += 6
            continue
        if c == 0x03:
            ascii_font = True; i += 1; continue
        if c == 0x04:
            ascii_font = False; i += 1; continue
        if c <= 0x0F:
            i += 1; continue
        if ascii_font:
            i += 1; continue
        if 0x10 <= c <= 0x1F and i + 1 < n:
            g = table.get((c << 8) | data[i + 1], "")
            if jp_char(g):
                run_jp.append((i, g))
            i += 2
            continue
        if c >= 0x7F:
            g = table.get(c, "")
            if jp_char(g):
                run_jp.append((i, g))
        i += 1
    # cluster: >=3 JP glyphs within a 40-byte window = a real string
    k = 0
    while k < len(run_jp):
        j = k
        while j + 1 < len(run_jp) and run_jp[j + 1][0] - run_jp[j][0] <= 6:
            j += 1
        if j - k + 1 >= 3:
            off = run_jp[k][0]
            ctx = "".join(g for _, g in run_jp[k:j + 1])
            hits.append((off, ctx[:60]))
        k = j + 1
    return hits


def main() -> int:
    table = decode_mod.load_table()
    total = 0
    for mdtdir in sorted(WORK.iterdir()):
        pieces = mdtdir / "pieces"
        if not pieces.is_dir():
            continue
        mdt_hits = []
        for pf in sorted(pieces.iterdir()):
            for off, ctx in scan_piece(pf.read_bytes(), table):
                mdt_hits.append((pf.name, off, ctx))
        if mdt_hits:
            print(f"== {mdtdir.name}: {len(mdt_hits)} real-JP clusters")
            for name, off, ctx in mdt_hits[:40]:
                print(f"   piece={name} @{off:#x}: {ctx}")
            if len(mdt_hits) > 40:
                print(f"   ... +{len(mdt_hits)-40}")
        else:
            print(f"== {mdtdir.name}: clean")
        total += len(mdt_hits)
    print(f"TOTAL real-JP clusters: {total}")
    return 0


if __name__ == "__main__":
    main()
