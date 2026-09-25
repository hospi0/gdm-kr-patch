#!/usr/bin/env python3
"""Lane R audit pass 2: extract REAL Japanese strings (not binary coincidences).

Two extractors:
  1. SJIS sentence text: decode-validated double-byte runs REQUIRED to contain
     kana (hiragana or full-width katakana). Binary gibberish decodes to rare
     kanji with no kana; real dialogue/UI text almost always has kana.
  2. JIS X0201 half-width-kana strings: runs of [0x20-0x7E, 0xA1-0xDF] with
     >=3 kana bytes, filtered against monotonic/repetitive byte tables.

Usage: audit_realtext.py <track.bin> [<file-on-disc> ...]   (default: all files)
Prints per-file real strings with offsets.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import iso  # noqa: E402

SJIS_PAIR = rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc])"
SJIS_RUN = re.compile(SJIS_PAIR + b"{2,}")
# consecutive half-width kana (0xA1-0xDF), 5+ bytes: SH2 opcodes interleave
# with low bytes so requiring consecutiveness kills code false-positives
HWK_STR = re.compile(rb"[\xa1-\xdf]{5,}")


def kana(ch):
    o = ord(ch)
    return 0x3041 <= o <= 0x309F or 0x30A1 <= o <= 0x30FF


def jp(ch):
    o = ord(ch)
    return kana(ch) or 0x4E00 <= o <= 0x9FFF


def sjis_strings(data):
    out = []
    for m in SJIS_RUN.finditer(data):
        try:
            s = m.group().decode("shift_jis")
        except UnicodeDecodeError:
            continue
        nk = sum(1 for c in s if kana(c))
        njp = sum(1 for c in s if jp(c))
        # real text: has kana, and is mostly JP chars
        if nk >= 2 and njp / len(s) >= 0.7 and len(s) >= 4:
            # reject repeats of one char (tile fills)
            if len(set(s)) >= max(3, len(s) // 4):
                out.append((m.start(), s))
    return out


def hwk_strings(data):
    out = []
    for m in HWK_STR.finditer(data):
        b = m.group()
        nk = sum(1 for x in b if 0xA6 <= x <= 0xDF)
        if nk < 4:
            continue
        # reject monotonic byte tables (e.g. DE DC DA D8 ...)
        diffs = [b[i + 1] - b[i] for i in range(len(b) - 1)]
        if diffs and (all(d <= 0 for d in diffs) or all(d >= 0 for d in diffs)):
            continue
        if len(set(b)) < 4:
            continue
        # real kana words: dakuten/handakuten (DE/DF) follow a voiceable kana,
        # and the run shouldn't be dominated by punctuation A1-A5
        if sum(1 for x in b if x <= 0xA5) > len(b) // 3:
            continue
        s = b.decode("shift_jis", "replace")
        out.append((m.start(), s))
    return out


def main():
    track = sys.argv[1]
    wanted = set(sys.argv[2:])
    with open(track, "rb") as f:
        for path, lba, size in iso.walk(f):
            if wanted and path not in wanted:
                continue
            if size == 0 or size > 50_000_000:
                continue
            data = iso.read_bytes(f, lba, size)
            sj = sjis_strings(data)
            hw = hwk_strings(data)
            if sj or hw:
                print(f"== {path} ({size} B): {len(sj)} sjis-real, {len(hw)} hwk-real")
                for off, s in sj[:40]:
                    print(f"   SJIS @{off:#7x}: {s[:60]}")
                if len(sj) > 40:
                    print(f"   ... +{len(sj)-40} more SJIS")
                for off, s in hw[:40]:
                    print(f"   HWK  @{off:#7x}: {s[:60]}")
                if len(hw) > 40:
                    print(f"   ... +{len(hw)-40} more HWK")


if __name__ == "__main__":
    main()
