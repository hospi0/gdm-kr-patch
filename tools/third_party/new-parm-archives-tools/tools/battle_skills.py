#!/usr/bin/env python3
"""battle_skills.py — translate the in-battle MAGIC/SKILL submenu DESCRIPTION boxes embedded in
every /BATLE/*.BBG (sec4).

LANE BAT FINDING (rc_26, see docs/lanes/laneBAT-battlemenus.md):
  The battle Magic/Skill submenu (user savestate `user-battle-skillmenu-jp-rc25`) renders from
  the SAME 9-section BBG embedded text file that battle_sec0.py patches (loads to LWRAM 0x239000
  + mirror). The relevant sections:
    * sec1 = spell/skill NAME list, game-native half-width KANA — this is what the name columns
      rasterise.  *** OWNED BY LANE MOV (tools/moves_sec1.py, build_rc step 8c) — DO NOT TOUCH. ***
    * sec3 = the SAME names in 16x16 tbl (kanji), an inert duplicate for this menu — LEFT ALONE to
      keep name ownership single-sourced in MOV's sec1 fold.
    * sec4 = the DESCRIPTION boxes in tbl (contains kanji -> must be tbl).  ** THIS TOOL OWNS sec4. **
      LIVE-READ PROVEN: poking an English marker into a sec4 slot made the description box render
      English after a cursor move (docs/lanes/laneBAT-battlemenus.md).
  sec1[i] <-> sec3[i] <-> sec4[i] are index-aligned (ordinal i = the same skill).  We decode sec3[i]
  (readable tbl) -> JP name -> canonical G1 description from docs/menus/g1-terms-aligned.json
  spell_descriptions (Lane G1 rip).  All 117 spell/skill descriptions matched.

SECTION OWNERSHIP (folds stay disjoint; all share the sec7 runtime-placeholder donor and compose):
    sec0 -> tools/battle_sec0.py   (command panel, native)
    sec1 -> tools/moves_sec1.py    (spell/skill names, native)   [Lane MOV]
    sec4 -> tools/battle_skills.py  (spell/skill descriptions, tbl) [THIS TOOL]

EDIT MODEL (identical to battle_sec0.py):
  root archive -> child[last] -> item[1] = 9x uint32 BE section header (offsets RELATIVE to item).
  English sec4 is byte-longer than dense JP; we GROW sec4 and SHRINK the trailing runtime-placeholder
  sec7 by the delta, keeping item + file size identical.  Only the item header + sec4 + sec7 change.
  sec4 is byte-identical across all 33 gameplay BBGs (BTEST differs but is handled the same,
  string-keyed).  Reads the CURRENT header so it composes after battle_sec0 / moves_sec1 grow sec0/1.

Usage:
    python3 tools/battle_skills.py plan                 # decode + translation + size deltas
    python3 tools/battle_skills.py patch-bytes IN OUT   # translate one raw .BBG file
    python3 tools/battle_skills.py fold TRACK1.bin      # md5-agnostic, idempotent, in-place disc fold
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
import battle_sec0 as bs  # reuse the archive locator  # noqa: E402

FWD = dicdt.FWD

# ---- ordinal tokeniser (dicdt-aware: a 2-byte tbl code may legitimately contain a 0x00 low byte,
#      e.g. 0x1200 = 幅, so a naive NUL-split would corrupt entry boundaries). ------------------
def ordwalk(seg: bytes):
    """Split a packed NUL-separated string block into ordinal entries, honouring 2-byte codes.
    Returns list of entry byte-strings (NUL separators removed)."""
    out = []
    i = 0
    cur = bytearray()
    n = len(seg)
    while i < n:
        two = seg[i:i + 2]
        one = seg[i:i + 1]
        if two in FWD and not (one in FWD and seg[i] < 0x80):
            cur += two
            i += 2
            continue
        if one in FWD and seg[i] != 0:
            cur += one
            i += 1
            continue
        if seg[i] == 0:
            out.append(bytes(cur))
            cur = bytearray()
            i += 1
        else:
            cur.append(seg[i])
            i += 1
    if cur:
        out.append(bytes(cur))
    return out


def _decode(b: bytes):
    try:
        return dicdt.decode(b)
    except Exception:
        return None


# ---- translation source: G1-aligned canonical spell/skill names + descriptions ----------------
def _load_maps():
    g = json.loads((ROOT / "docs/menus/g1-terms-aligned.json").read_text(encoding="utf-8"))
    name2en = {t["jp"]: t["en"] for t in g["terms"] if t["category"] in ("spell", "skill")}
    jp2desc = {d["spell_jp"]: d["desc_en"] for d in g["spell_descriptions"]}
    return name2en, jp2desc


def _rebuild(ords, en_by_idx, tbl: bool):
    """Rebuild a NUL-separated block; translated entries get English (0x03+ASCII for tbl, raw ASCII
    for the native syllabary), untranslated entries kept verbatim. Idempotent."""
    out = bytearray()
    for i, e in enumerate(ords):
        en = en_by_idx.get(i)
        if en is not None and e:
            payload = (b"\x03" if tbl else b"") + en.encode("ascii")
            out += payload + b"\x00"
        else:
            out += e + b"\x00"
    return bytes(out)


def translate_item(secs):
    """secs = list of 8 section byte-strings (sec0..sec7). Returns new sec4 bytes, or None if
    nothing changed. ONLY sec4 (descriptions) is rewritten; names in sec1/sec3 are left to MOV."""
    name2en, jp2desc = _load_maps()
    s3o, s4o = ordwalk(secs[3]), ordwalk(secs[4])
    desc_en = {}
    for i in range(len(s3o)):
        jp = _decode(s3o[i])
        if jp and jp in name2en and jp in jp2desc:
            desc_en[i] = jp2desc[jp]
    if not desc_en:
        return None
    new4 = _rebuild(s4o, desc_en, tbl=True)
    if new4 == secs[4]:
        return None
    return new4


def patch_bbg(b: bytes) -> bytes:
    b = bytearray(b)
    item_off, item_len = bs._locate(b)
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    secs = [bytes(b[item_off + hdr[i]: item_off + hdr[i + 1]]) for i in range(8)]
    new4 = translate_item(secs)
    if new4 is None:
        return bytes(b)  # already English / nothing to do
    d4 = len(new4) - len(secs[4])
    sec7 = secs[7]
    if d4 > len(sec7) - 4:
        raise ValueError(f"sec4 delta {d4} too large for sec7 donor ({len(sec7)} B)")
    new7 = sec7[: len(sec7) - d4] if d4 >= 0 else sec7 + b"\x00" * (-d4)
    # only sec4 grows: sec0..sec4 starts unchanged; sec5/6/7 shift +d4; sec8 unchanged (donor absorbs)
    new_hdr = [
        hdr[0], hdr[1], hdr[2], hdr[3], hdr[4],
        hdr[5] + d4, hdr[6] + d4, hdr[7] + d4, hdr[8],
    ]
    body = bytearray()
    for v in new_hdr:
        body += struct.pack(">I", v)
    body = body[: hdr[0]]  # header occupies [0, 0x24)
    body += secs[0] + secs[1] + secs[2] + secs[3] + new4 + secs[5] + secs[6] + new7
    # sec8 tail (from hdr[8] to item end) unchanged
    body += bytes(b[item_off + hdr[8]: item_off + item_len])
    if len(body) != item_len:
        raise ValueError(f"item size changed {item_len}->{len(body)} (delta {d4})")
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
    name2en, jp2desc = _load_maps()
    s3o = ordwalk(secs[3])
    n = 0
    for i in range(len(s3o)):
        jp = _decode(s3o[i])
        if jp and jp in name2en and jp in jp2desc:
            n += 1
            print(f"  [{i:3d}] {jp!s:16s} -> {jp2desc[jp]}")
    new4 = translate_item(secs)
    print(f"\nmatched {n} descriptions; sec4 {len(secs[4])}->{len(new4)} "
          f"({len(new4)-len(secs[4]):+d}); sec7 donor {len(secs[7])} B")


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
    print(f"battle_skills fold: patched {done} BBG(s), skipped {skipped}")


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
