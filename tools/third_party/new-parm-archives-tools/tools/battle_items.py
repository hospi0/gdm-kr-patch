#!/usr/bin/env python3
"""battle_items.py — translate the in-battle ITEM-menu item NAMES embedded in every /BATLE/*.BBG.

LANE BAT2 FINDING (rc_27, see docs/lanes/laneBAT2-battle.md):
  The in-battle ITEM menu (command ring -> Item) lists the party's items. The user saw the names
  in JP (かいぞくナイフ …). Those names live in the SAME 9-section BBG embedded text file that
  battle_sec0/moves_sec1/battle_skills patch (loads to LWRAM 0x239000 + mirror 0x2c3700). Sections:
    * sec5 = the 512-slot item-name master table in the game-native half-width KANA encoding
      (like sec0/sec1). sec5[63] = 'かいぞくﾅｲﾌ' == exactly what the user saw -> **sec5 is the
      item-menu render source.**  *** THIS TOOL OWNS sec5. ***
    * sec6 = the SAME item table in 16x16 tbl (KANJI, cleanly dicdt-decodable): sec6[63]='海賊ナイフ'.
      Used here ONLY as the decode KEY (kanji -> terms.json English). Left JP (inert for the menu).
  sec5[i] <-> sec6[i] are index-aligned (byte-verified: i=63 = Pirate Knife in both). We decode
  sec6[i] (tbl) -> JP kanji name -> the shipped English from dictionary/terms.json (the SAME source
  the FIELD item menu uses, so battle names == field names). 266/512 slots map to a real item; the
  rest are placeholders (きんし/禁止/empty) left verbatim.

FONT ROUTING: sec5 is the native syllabary, which contains plain ASCII (proven for sec0 by
  battle_sec0) -> English is written as raw ASCII, NO 0x03 font switch (unlike the tbl sec4).

SECTION OWNERSHIP (folds stay disjoint; all share the sec7 runtime-placeholder donor and compose):
    sec0 -> tools/battle_sec0.py    (command panel, native)
    sec1 -> tools/moves_sec1.py     (spell/skill names, native)      [Lane MOV]
    sec4 -> tools/battle_skills.py  (spell/skill descriptions, tbl)  [Lane BAT]
    sec5 -> tools/battle_items.py   (ITEM names, native)             [THIS TOOL, Lane BAT2]
    M_DAT -> tools/battle_mdat.py   (enemy names)

EDIT MODEL (identical to battle_skills.py, one section over):
  root archive -> child[last] -> item[1] = 9x uint32 BE section header (offsets RELATIVE to item).
  English sec5 is byte-longer than the dense JP kana; GROW sec5 and SHRINK the trailing runtime-
  placeholder sec7 by the delta, keeping item + file size identical. Only the item header + sec5 +
  sec7 change. sec5 is byte-identical across all 33 gameplay BBGs (BTEST handled the same, keyed).
  Reads the CURRENT header so it composes after battle_sec0 (+sec0) / moves_sec1 (+sec1) /
  battle_skills (+sec4). Idempotent (English ASCII entries are skipped on re-run).

Usage:
    python3 tools/battle_items.py plan                 # decode + translation + size deltas
    python3 tools/battle_items.py patch-bytes IN OUT   # translate one raw .BBG file
    python3 tools/battle_items.py fold TRACK1.bin      # md5-agnostic, idempotent, in-place disc fold
"""
from __future__ import annotations
import struct, sys, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
import iso     # noqa: E402
import dicdt   # noqa: E402
import battle_sec0 as bs  # reuse the archive locator + native decoder  # noqa: E402


def _tbl_decode(b: bytes):
    try:
        return dicdt.decode(b)
    except Exception:
        return None


def split_nul(seg: bytes):
    """Split a native (single-byte) NUL-separated block into entries (separators removed)."""
    out = []
    i = 0
    while i < len(seg):
        e = seg.find(b"\x00", i)
        if e < 0:
            out.append(seg[i:]); break
        out.append(seg[i:e]); i = e + 1
    return out


# tbl sec6 uses 2-byte codes whose low byte may be 0x00 -> a NUL-aware ordinal walk (from
# battle_skills) is required so sec6 indices align with sec5's NUL-split indices.
FWD = dicdt.FWD


def ordwalk_tbl(seg: bytes):
    out = []
    i = 0
    cur = bytearray()
    n = len(seg)
    while i < n:
        two = seg[i:i + 2]
        one = seg[i:i + 1]
        if two in FWD and not (one in FWD and seg[i] < 0x80):
            cur += two; i += 2; continue
        if one in FWD and seg[i] != 0:
            cur += one; i += 1; continue
        if seg[i] == 0:
            out.append(bytes(cur)); cur = bytearray(); i += 1
        else:
            cur.append(seg[i]); i += 1
    out.append(bytes(cur))  # trailing entry (may be empty)
    return out


def _load_terms():
    t = json.loads((ROOT / "dictionary/terms.json").read_text(encoding="utf-8"))["terms"]
    return t


def _english_for(jp: str, terms):
    if not jp or jp not in terms:
        return None
    e = terms[jp]
    en = e.get("field_name") or e.get("en")
    if not en:
        return None
    return en.strip()


def _is_ascii(b: bytes):
    return all(0x20 <= x < 0x7f for x in b) and len(b) > 0


def translate_item(secs):
    """secs = list of 8 section byte-strings (sec0..sec7). Returns new sec5 bytes, or None if
    nothing changed. ONLY sec5 (item names) is rewritten."""
    terms = _load_terms()
    o5 = split_nul(secs[5])
    o6 = ordwalk_tbl(secs[6])
    en_by_idx = {}
    for i in range(min(len(o5), len(o6))):
        jp = _tbl_decode(o6[i])
        en = _english_for(jp, terms)
        if en is not None and o5[i]:
            # only accept plain-ASCII English (native font path)
            try:
                enb = en.encode("ascii")
            except UnicodeEncodeError:
                continue
            # Lane X3 (2026-07-07): CONVERGENT fold — rewrite JP entries AND already-English
            # entries whose text no longer matches terms.json (e.g. the Papa's Charm ->
            # Papa's Amulet rename). Still idempotent: once o5[i] == the current English
            # bytes nothing is queued, so a re-run is a no-op.
            if (not _is_ascii(o5[i])) or (o5[i] != enb):
                en_by_idx[i] = en
    if not en_by_idx:
        return None
    out = bytearray()
    for i, e in enumerate(o5):
        en = en_by_idx.get(i)
        if en is not None:
            out += en.encode("ascii") + b"\x00"
        else:
            out += e + b"\x00"
    # split_nul on a block WITHOUT a trailing NUL keeps the final entry; the original ended on the
    # last real byte (no trailing NUL) OR a trailing NUL. Reconstruct to match: original had N
    # entries joined by NUL. Our rebuild adds a NUL after every entry incl. the last -> strip one
    # trailing NUL iff the original did not end in NUL.
    if secs[5] and secs[5][-1] != 0 and out and out[-1] == 0:
        out = out[:-1]
    new5 = bytes(out)
    if new5 == secs[5]:
        return None
    return new5


def patch_bbg(b: bytes) -> bytes:
    b = bytearray(b)
    item_off, item_len = bs._locate(b)
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    secs = [bytes(b[item_off + hdr[i]: item_off + hdr[i + 1]]) for i in range(8)]
    new5 = translate_item(secs)
    if new5 is None:
        return bytes(b)  # already English / nothing to do
    d5 = len(new5) - len(secs[5])
    sec7 = secs[7]
    if d5 > len(sec7) - 4:
        raise ValueError(f"sec5 delta {d5} too large for sec7 donor ({len(sec7)} B)")
    new7 = sec7[: len(sec7) - d5] if d5 >= 0 else sec7 + b"\x00" * (-d5)
    # only sec5 grows: sec0..sec5 starts unchanged; sec6/sec7 shift +d5; sec8 start unchanged.
    new_hdr = [
        hdr[0], hdr[1], hdr[2], hdr[3], hdr[4], hdr[5],
        hdr[6] + d5, hdr[7] + d5, hdr[8],
    ]
    body = bytearray()
    for v in new_hdr:
        body += struct.pack(">I", v)
    body = body[: hdr[0]]
    body += secs[0] + secs[1] + secs[2] + secs[3] + secs[4] + new5 + secs[6] + new7
    body += bytes(b[item_off + hdr[8]: item_off + item_len])  # sec8 tail unchanged
    if len(body) != item_len:
        raise ValueError(f"item size changed {item_len}->{len(body)} (delta {d5})")
    b[item_off: item_off + item_len] = body
    return bytes(b)


BBG_NAMES = bs.BBG_NAMES


def cmd_plan():
    van = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
    with open(van, "rb") as f:
        rec = iso.find_record(f, "B001.BBG")
        b = iso.read_bytes(f, rec["lba"], rec["size"])
    item_off, item_len = bs._locate(bytearray(b))
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    secs = [bytes(b[item_off + hdr[i]: item_off + hdr[i + 1]]) for i in range(8)]
    terms = _load_terms()
    o5 = split_nul(secs[5]); o6 = ordwalk_tbl(secs[6])
    n = 0
    for i in range(min(len(o5), len(o6))):
        jp = _tbl_decode(o6[i]); en = _english_for(jp, terms)
        if en is not None and o5[i] and not _is_ascii(o5[i]):
            try:
                en.encode("ascii")
            except UnicodeEncodeError:
                continue
            if n < 30:
                print(f"  [{i:3d}] {jp!s:12s} -> {en}")
            n += 1
    new5 = translate_item(secs)
    print(f"\nmatched {n} item names; sec5 {len(secs[5])}->{len(new5)} "
          f"({len(new5)-len(secs[5]):+d}); sec7 donor {len(secs[7])} B")


def cmd_fold(track):
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    done = skipped = 0
    for name in BBG_NAMES:
        with open(track, "rb") as f:
            rec = iso.find_record(f, name)
            if not rec:
                continue
            data = iso.read_bytes(f, rec["lba"], rec["size"])
        try:
            new = patch_bbg(data)
        except Exception as ex:
            print(f"  WARN {name}: {ex}")
            skipped += 1
            continue
        if new == data:
            skipped += 1
            continue
        assert len(new) == len(data), f"{name} size changed!"
        lba = rec["lba"]
        span = (len(new) + U - 1) // U
        with open(track, "r+b") as f:
            for i in range(span):
                chunk = new[i * U:(i + 1) * U]
                if len(chunk) < U:
                    chunk = chunk + b"\x00" * (U - len(chunk))
                f.seek((lba + i) * RAW + SYNC)
                f.write(chunk)
        done += 1
    print(f"battle_items fold: patched {done} BBG(s), skipped {skipped}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "plan":
        cmd_plan()
    elif cmd == "patch-bytes":
        Path(argv[3]).write_bytes(patch_bbg(Path(argv[2]).read_bytes()))
        print(f"patched {argv[2]} -> {argv[3]}")
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(f"unknown command {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
