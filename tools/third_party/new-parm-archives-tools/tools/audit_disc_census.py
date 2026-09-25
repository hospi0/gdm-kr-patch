#!/usr/bin/env python3
"""Lane R audit: disc-wide Japanese-text census, rc_24 vs vanilla.

Walks every file on both discs, hashes them, and scans for Japanese text in the
encodings the project knows:
  - SJIS double-byte runs (kana/kanji, decode-validated)
  - JIS X0201 half-width katakana runs (0xA6..0xDF)
  - EUC-JP double-byte runs (decode-validated)
Outputs a per-file table (JSON + text) so hits can be classified:
translated / known-open / newly-found / non-rendered junk.

Usage: audit_disc_census.py <vanilla_track1.bin> <rc_track1.bin> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import iso  # noqa: E402

# SJIS double-byte JP char: lead 0x81-0x9F / 0xE0-0xEA, trail 0x40-0x7E / 0x80-0xFC
SJIS_PAIR = rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc])"
SJIS_RUN = re.compile(SJIS_PAIR + b"{3,}")
# JIS X0201 half-width katakana (0xA6-0xDF; exclude 0xA1-0xA5 punctuation to cut noise)
HWK_RUN = re.compile(rb"[\xa6-\xdf]{6,}")
# EUC-JP double-byte run
EUC_PAIR = rb"(?:[\xa1-\xfe][\xa1-\xfe])"
EUC_RUN = re.compile(EUC_PAIR + b"{3,}")

# decoded chars that count as "Japanese" (not full-width Roman/digits/space)
def jp_char(ch: str) -> bool:
    o = ord(ch)
    return (
        0x3041 <= o <= 0x30FF  # hiragana + katakana
        or 0x4E00 <= o <= 0x9FFF  # kanji
        or 0x3005 <= o <= 0x3007  # 々〆〇
        or o == 0x30FC  # ー
    )


def scan_sjis(data: bytes, max_samples=6):
    """Return (jp_char_count, samples) of decode-validated SJIS runs."""
    total = 0
    samples = []
    for m in SJIS_RUN.finditer(data):
        try:
            s = m.group().decode("shift_jis")
        except UnicodeDecodeError:
            continue
        njp = sum(1 for ch in s if jp_char(ch))
        # require the run to be mostly-JP to avoid binary coincidences
        if njp >= 3 and njp / len(s) >= 0.6:
            total += njp
            if len(samples) < max_samples:
                samples.append((m.start(), s[:40]))
    return total, samples


def scan_euc(data: bytes, max_samples=4):
    total = 0
    samples = []
    for m in EUC_RUN.finditer(data):
        try:
            s = m.group().decode("euc_jp")
        except UnicodeDecodeError:
            continue
        njp = sum(1 for ch in s if jp_char(ch))
        if njp >= 3 and njp / len(s) >= 0.7:
            total += njp
            if len(samples) < max_samples:
                samples.append((m.start(), s[:40]))
    return total, samples


def scan_hwk(data: bytes, max_samples=4):
    """Half-width kana runs. Very noise-prone in binary: require >=6 bytes and
    that the run isn't a constant-byte fill."""
    total = 0
    samples = []
    for m in HWK_RUN.finditer(data):
        b = m.group()
        if len(set(b)) < 3:  # constant fill / palette-ish
            continue
        s = b.decode("shift_jis", "replace")
        total += len(b)
        if len(samples) < max_samples:
            samples.append((m.start(), s[:30]))
    return total, samples


def census(track: Path):
    out = {}
    with open(track, "rb") as f:
        files = list(iso.walk(f))
        for path, lba, size in files:
            if size == 0:
                out[path] = dict(lba=lba, size=size, md5="", sjis=0, euc=0, hwk=0,
                                 sjis_samples=[], euc_samples=[], hwk_samples=[])
                continue
            data = iso.read_bytes(f, lba, size)
            md5 = hashlib.md5(data).hexdigest()
            sj, sjs = scan_sjis(data)
            eu, eus = scan_euc(data)
            hw, hws = scan_hwk(data)
            out[path] = dict(lba=lba, size=size, md5=md5, sjis=sj, euc=eu, hwk=hw,
                             sjis_samples=[[o, s] for o, s in sjs],
                             euc_samples=[[o, s] for o, s in eus],
                             hwk_samples=[[o, s] for o, s in hws])
            print(f"  {path}: size={size} sjis={sj} euc={eu} hwk={hw}", file=sys.stderr)
    return out


def main():
    van_track, rc_track, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    print("== vanilla ==", file=sys.stderr)
    van = census(Path(van_track))
    print("== rc ==", file=sys.stderr)
    rc = census(Path(rc_track))
    result = {"vanilla": van, "rc": rc}
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    # summary table
    print(f"{'path':38} {'size':>10} {'mod?':>5} {'van_sjis':>8} {'rc_sjis':>8} {'rc_hwk':>7}")
    for path in sorted(set(van) | set(rc)):
        v, r = van.get(path), rc.get(path)
        if v is None or r is None:
            print(f"{path:38} {'MISSING on ' + ('rc' if r is None else 'vanilla')}")
            continue
        mod = "SAME" if v["md5"] == r["md5"] and v["size"] == r["size"] else "MOD"
        if v["sjis"] or r["sjis"] or r["hwk"] > 50 or v["hwk"] > 50:
            print(f"{path:38} {r['size']:>10} {mod:>5} {v['sjis']:>8} {r['sjis']:>8} {r['hwk']:>7}")


if __name__ == "__main__":
    main()
