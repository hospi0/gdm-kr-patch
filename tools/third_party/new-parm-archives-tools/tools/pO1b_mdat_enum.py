#!/usr/bin/env python3
"""pO1b_mdat_enum.py — enumerate DM-original enemy/boss NAME slots in /BATLE/M_DAT.BIN that
battle_mdat._load_names() does NOT currently cover.

LANE O1b (rc_40 coverage pass). Background: docs/lanes/laneQ2-battle-hud.md "Lane O1b addendum".
battle_mdat.plan_patches() finds a name/action slot by searching for the tbl-encoding of every
name it KNOWS (G1 canon + battle_text.MON + exceptions.json "enem" heuristic). DM-original bosses
that are absent from all three never get searched, so their M_DAT tbl name-slot stays JP.

This tool inverts the search: it scans M_DAT for every NUL-bounded tbl-decodable run (>= MIN chars,
using the SAME slot-anchor test plan_patches uses) and reports the ones whose offset battle_mdat
would NOT patch. Those are candidate DM-original names for review → dictionary/exceptions.json.

It reuses battle_mdat's plan_patches (covered set) + dicdt.decode / tbl_enc (decode/encode). It is
read-only; it never writes the disc. It does NOT invent English — decoding + offsets only.

Usage:
    python3 tools/pO1b_mdat_enum.py [TRACK1.bin]     # default: vanilla input disc
    python3 tools/pO1b_mdat_enum.py --exc PATH ...   # use an alt exceptions.json (test coverage)

Output columns: offset | chars | script-class | decoded-JP  (name/action heuristic in the class).
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "menus"))

import dicdt          # noqa: E402
import battle_mdat    # noqa: E402
import iso            # noqa: E402

MIN_TBL_CHARS = 4     # mirror battle_mdat.MIN_TBL_LEN semantics (>=4 tbl code units)
HEADER_END = 0xd000   # M_DAT's 6-section header/stat tables precede the first record (0xd018);
                      # everything below is filler that decodes as tbl noise → skip it.
ACTION_DELTA = 0x34   # in a per-monster record the NAME tbl-slot is followed by the ACTION
                      # tbl-slot exactly 0x34 bytes later (verified across 294 covered records).


def _script_class(s: str) -> str:
    """Rough classifier so a human can triage: kana-only names are safe transliterations;
    kanji-bearing names are ambiguous and must go to the user (CLAUDE.md rule 6)."""
    has_kanji = any("一" <= c <= "鿿" for c in s)
    has_kata = any("゠" <= c <= "ヿ" or c == "ー" for c in s)
    has_hira = any("぀" <= c <= "ゟ" for c in s)
    if has_kanji:
        return "kanji" + ("+kana" if (has_kata or has_hira) else "")
    if has_kata and not has_hira:
        return "katakana"
    if has_hira and not has_kata:
        return "hiragana"
    if has_kata or has_hira:
        return "kana-mix"
    return "other"


def _decodes_clean(run: bytes):
    """Return decoded str if run decodes fully via the 16x16 tbl (no <xx> fallbacks, not the 0x03
    ascii branch) and every char is a plausible JP name glyph; else None."""
    if not run or run[0] == 0x03:
        return None
    s = dicdt.decode(run)
    if "<" in s:                      # any un-mapped byte → not a clean tbl string
        return None
    # round-trip through tbl_enc to be certain it is genuine tbl (rejects lucky partial decodes)
    if battle_mdat.tbl_enc(s) != run:
        return None
    # plausible-name charset: kana / kanji / long-vowel / a few JP marks. Reject ASCII/punct noise.
    ok = all(
        ("぀" <= c <= "ヿ") or ("一" <= c <= "鿿") or c in "ー・々〆"
        for c in s
    )
    if not ok:
        return None
    return s


def _preceding_hwkata(b: bytes, start: int) -> bool:
    """True if a half-width-katakana run (>=3 bytes of 0x90 / 0xA1-0xDF) sits immediately before the
    tbl slot (allowing a few NUL pad bytes). This is the per-monster record's PANEL name copy; every
    genuine enemy/boss NAME (and subtitle) slot has it, and it is what separates a real record string
    from tbl-decodable filler."""
    j = start - 1
    skipped = 0
    while j >= 0 and b[j] == 0 and skipped < 8:
        j -= 1
        skipped += 1
    if j < 0 or not (b[j] == 0x90 or 0xA1 <= b[j] <= 0xDF):
        return False
    cnt = 0
    while j >= 0 and (b[j] == 0x90 or 0xA1 <= b[j] <= 0xDF):
        j -= 1
        cnt += 1
    return cnt >= 3


def enumerate_uncovered(b: bytes, covered_offsets: set[int]):
    """Yield (offset, decoded, nchars, klass, has_action) for every NUL-bounded tbl name-run
    >=MIN chars that battle_mdat does NOT cover AND that structurally looks like a per-monster
    record NAME slot: past the header, immediately preceded by a hwkata PANEL copy. `has_action`
    flags whether an ACTION tbl-slot sits at +0x34 (the full record signature)."""
    n = len(b)
    out = []
    pieces = b.split(b"\x00")
    starts = []
    p = 0
    for pc in pieces:
        starts.append(p)
        p += len(pc) + 1               # +1 for the NUL delimiter split consumed
    runmap = {starts[i]: pieces[i] for i in range(len(pieces))}
    for i, piece in enumerate(pieces):
        start = starts[i]
        if start < HEADER_END or not piece:
            continue
        end = start + len(piece)
        if end >= n or b[end] != 0:     # trailing NUL required
            continue
        s = _decodes_clean(piece)
        if s is None or len(s) < MIN_TBL_CHARS:
            continue
        if start in covered_offsets:
            continue
        if not _preceding_hwkata(b, start):
            continue                    # structural gate: must be a real record PANEL+banner pair
        has_action = _decodes_clean(runmap.get(start + ACTION_DELTA, b"")) is not None
        out.append((start, s, len(s), _script_class(s), has_action))
    return out


def _covered_offsets(b: bytes) -> set[int]:
    """Offsets battle_mdat would patch (its tbl slots) — the 'already covered' set."""
    return {off for off, old, new, kind, jp, en in battle_mdat.plan_patches(b) if kind == "tbl"}


def _read_mdat(track: str):
    with open(track, "rb") as f:
        rec = iso.find_record(f, "M_DAT.BIN")
        return iso.read_bytes(f, rec["lba"], rec["size"])


def main(argv):
    track = None
    exc_override = None
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--exc":
            exc_override = args[i + 1]; i += 2
        else:
            track = args[i]; i += 1
    if track is None:
        track = str(ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin")

    if exc_override:
        # monkeypatch battle_mdat._load_names to read an alternate exceptions.json (test-only).
        import json
        _orig = battle_mdat._load_names
        real_exc = ROOT / "dictionary/exceptions.json"
        _saved = real_exc.read_text(encoding="utf-8") if real_exc.exists() else None
        # simplest: temporarily point plan_patches at the override by swapping the file content in
        # memory via a shim. We instead re-implement by reading override into the same code path.
        override_data = json.loads(Path(exc_override).read_text(encoding="utf-8"))

        def _patched():
            names = _orig.__wrapped__() if hasattr(_orig, "__wrapped__") else None
            return names
        # Cleaner: read names as usual then merge override's enem entries on top.
        base = _orig()
        for e in override_data.get("exceptions", []):
            jp, en = e.get("jp"), e.get("en")
            if jp and en and "enem" in (e.get("reason", "").lower()):
                base.setdefault(jp, en)
        battle_mdat._load_names = lambda: base

    b = _read_mdat(track)
    covered = _covered_offsets(b)
    rows = enumerate_uncovered(b, covered)
    # dedup by decoded name (same name may recur across records); keep the first offset + all offs.
    from collections import OrderedDict
    byname = OrderedDict()
    for off, s, nch, klass, act in sorted(rows):
        e = byname.setdefault(s, {"offs": [], "nch": nch, "klass": klass, "act": False})
        e["offs"].append(off)
        e["act"] = e["act"] or act
    print(f"# M_DAT uncovered record NAME-slots (hwkata-anchored, >= {MIN_TBL_CHARS} chars): "
          f"{len(rows)} slots / {len(byname)} distinct names  "
          f"(covered tbl slots: {len(covered)})  track={Path(track).name}")
    print(f"# cols: firstOff | #recs | chars | script-class | action@+0x34? | decoded-JP")
    for s, e in byname.items():
        print(f"  0x{e['offs'][0]:07x}  x{len(e['offs']):<2d} {e['nch']:2d}  "
              f"{e['klass']:11s}  act={'Y' if e['act'] else 'n'}  {s!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
