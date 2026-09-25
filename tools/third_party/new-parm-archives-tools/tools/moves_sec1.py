#!/usr/bin/env python3
"""moves_sec1.py — translate the spell/skill NAME list rendered by the "Moves LEVEL n"
character-growth screen (and the in-battle MAGIC/SKILL menu) to Grandia-1 canon.

LANE MOV FINDING (rc_26, docs/lanes/laneMOV-moves.md):
  The "Moves LEVEL n" growth screen headers are already English (Moves / STR/VIT/WIT/AGI /
  MAGIC / LV UP PARAM), but the spell-name COLUMN renders JP half-width katakana. That column
  does NOT come from WDATA.DAT sec7 (the 16x16-tbl copy that menus/build_full_disc.py already
  translates) — it comes from **sec1 of the 9-section text sub-resource embedded in every
  /BATLE/*.BBG**, a 127-entry list (117 real spell/skill names + 10 blank " " pads) in the SAME
  game-native half-width-kana encoding as sec0 (battle HUD; see tools/battle_sec0.py). The list
  is index-aligned to WDATA sec7 / BATLE/TEXT2.BIN sec4, so g1-terms-aligned.json[idx] maps
  1:1 by ordinal. Proven: sec1[4] = ｹﾛﾏ (ケロマ) = "Heal" — the doc's "クロマ/Kuroma" was a
  screenshot mis-transcription of ケロマ (RESOLVED). The moves menu loads this block resident at
  LWRAM 0x2e0000 (contiguous after the sec0 HUD block) and reads names by index.

FONT ROUTING: the sec1/sec0 font renders plain ASCII 0x20-0x7E directly (vanilla sec1 already
  stores "V-Slash"/"W-Break" as ASCII 'V'/'W'); English is written as raw ASCII, NO 0x03 switch.

EDIT MODEL (size-preserving, no disc relayout — identical to tools/battle_sec0.py):
  English sec1 is byte-longer than the dense kana, so GROW sec1 and SHRINK the trailing
  runtime-placeholder sec7 by the same delta; the 9-uint item header (sec2..sec7 offsets) shifts
  by +delta and the item/file size is unchanged.

COMPOSITION WITH LANE BAT (#29) / battle_sec0:
  battle_sec0 edits sec0 (+ shrinks sec7 + shifts hdr[1..7]); this tool edits sec1 (+ shrinks
  sec7 + shifts hdr[2..7]) — DISJOINT sections, both idempotent, header re-read fresh each run,
  so they compose in either order (combined sec7 shrink << donor). This same sec1 is the source
  for #29's in-battle MAGIC/SKILL name list, so BAT should NOT re-translate sec1 spell names —
  only the skill-submenu chrome + description boxes.

IDEMPOTENT / gated: each entry is translated only if it still holds JP kana bytes (>0x7E); an
  already-ASCII entry is left as-is. If nothing changes, the BBG is skipped (no write).

Usage:
    python3 tools/moves_sec1.py plan                 # decode + show translation + delta (B001)
    python3 tools/moves_sec1.py patch-bytes IN OUT   # translate one raw .BBG file
    python3 tools/moves_sec1.py fold TRACK1.bin      # in-place disc fold (all BBGs)
"""
from __future__ import annotations
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
import iso  # noqa: E402
from battle_sec0 import _locate, decode as hk_decode  # reuse the proven container parse + decoder

ALIGNED = ROOT / "docs/menus/g1-terms-aligned.json"
BBG_NAMES = [f"B{n:03d}.BBG" for n in range(1, 33)] + ["B255.BBG", "BTEST.BBG"]


def load_idx2en() -> dict[int, str]:
    """Ordinal (WDATA sec7 idx) -> G1 canonical English, for spell + skill categories only."""
    g = json.loads(ALIGNED.read_text(encoding="utf-8"))
    idx2en: dict[int, str] = {}
    for term in g["terms"]:
        if term.get("category") not in ("spell", "skill"):
            continue
        m = re.search(r"sec4 \[idx (\d+)\]", term.get("g1_source_file", ""))
        if not m:
            continue
        i = int(m.group(1))
        en = term["en"]
        if not all(0x20 <= ord(c) <= 0x7E for c in en):
            raise SystemExit(f"idx {i}: EN {en!r} is not pure ASCII — sec1 font is kana/ASCII only")
        idx2en[i] = en
    return idx2en


IDX2EN = load_idx2en()


def translate_sec1(sec1: bytes, prefix03: bool = False):
    """Return (new_sec1, notes). Preserves the NUL structure exactly; ordinal position of each
    non-empty token == its spell index. Only kana tokens are translated (idempotent).

    prefix03: when True, author each English name as 0x03+ASCII (font-switch to the 8x16 ASCII
    font) instead of raw ASCII. Required for **BBG sec1** because lane BANNER (O3) reroutes the
    mid-attack action banner to read sec1 NAMES, and that banner draw honours 0x03 (renders raw
    non-0x03 bytes in the tbl-kanji font -> garbage); the battle skill MENU tolerates the 0x03
    (proven). The **WDATA sec6** pause-menu list (lane N1/N2) keeps raw ASCII (prefix03=False) —
    that renderer takes ASCII directly and was shipped/validated without 0x03."""
    tokens = sec1.split(b"\x00")
    out = []
    notes = []
    ordn = 0
    for tk in tokens:
        if tk == b"":
            out.append(tk)
            continue
        # already-English (idempotent): no bytes > 0x7E (a 0x03+ASCII or raw-ASCII token)
        if ordn in IDX2EN and any(x > 0x7E for x in tk):
            en = IDX2EN[ordn].encode("ascii")
            if prefix03:
                en = b"\x03" + en
            out.append(en)
            notes.append(("EN", ordn, hk_decode(tk), IDX2EN[ordn]))
        else:
            out.append(tk)
            if any(x > 0x7E for x in tk):
                notes.append(("KEEP", ordn, hk_decode(tk)))
        ordn += 1
    return b"\x00".join(out), notes


def patch_bbg(b: bytes) -> bytes:
    b = bytearray(b)
    item_off, item_len = _locate(b)
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    sec1 = bytes(b[item_off + hdr[1]: item_off + hdr[2]])
    new_sec1, _ = translate_sec1(sec1, prefix03=True)  # BBG sec1: 0x03+ASCII for the O3 banner reroute
    delta = len(new_sec1) - len(sec1)
    if delta == 0 and new_sec1 == sec1:
        return bytes(b)  # already English / nothing to do
    sec7 = bytes(b[item_off + hdr[7]: item_off + hdr[8]])
    if delta > len(sec7) - 4:
        raise ValueError(f"sec1 delta {delta} too large for sec7 donor ({len(sec7)} B)")
    new_sec7 = sec7[: len(sec7) - delta] if delta > 0 else sec7 + b"\x00" * (-delta)
    # sec0 unchanged; sec2..sec7 offsets shift by +delta; sec8/item end unchanged.
    new_hdr = [hdr[0], hdr[1]] + [hdr[i] + delta for i in range(2, 8)] + [hdr[8]]
    parts = bytearray()
    for v in new_hdr:
        parts += struct.pack(">I", v)
    parts = parts[: hdr[0]]
    body = bytearray(b[item_off + hdr[0]: item_off + item_len])
    H = hdr[0]

    def splice(dst, lo, hi, new):
        return dst[:lo] + new + dst[hi:]

    # sec7 first (higher offset), then sec1 (lower) — same order discipline as battle_sec0.
    body = splice(body, hdr[7] - H, hdr[8] - H, new_sec7)
    body = splice(body, hdr[1] - H, hdr[2] - H, new_sec1)
    new_item = bytes(parts) + bytes(body)
    if len(new_item) != item_len:
        raise ValueError(f"item size changed {item_len}->{len(new_item)} (delta {delta})")
    b[item_off: item_off + item_len] = new_item
    return bytes(b)


def cmd_plan():
    van = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
    with open(van, "rb") as f:
        rec = iso.find_record(f, "B001.BBG")
        b = iso.read_bytes(f, rec["lba"], rec["size"])
    item_off, item_len = _locate(bytearray(b))
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    sec1 = b[item_off + hdr[1]: item_off + hdr[2]]
    new_sec1, notes = translate_sec1(bytes(sec1), prefix03=True)
    print(f"sec1 {len(sec1)} -> {len(new_sec1)} B (delta {len(new_sec1)-len(sec1):+d}); "
          f"sec7 donor {hdr[8]-hdr[7]} B; {sum(1 for n in notes if n[0]=='EN')} translated")
    for nt in notes:
        if nt[0] == "EN":
            print(f"   [{nt[1]:3d}] {nt[2]!r} -> {nt[3]!r}")
        else:
            print(f"   [{nt[1]:3d}] KEEP {nt[2]!r}")


def cmd_fold(track):
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    done = skipped = 0
    for name in BBG_NAMES:
        with open(track, "rb") as f:
            rec = iso.find_record(f, name)
            if not rec:
                continue
            data = iso.read_bytes(f, rec["lba"], rec["size"])
        new = patch_bbg(data)
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
    print(f"moves_sec1 fold: patched {done} BBG(s), skipped {skipped} (already-EN/absent)")


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
