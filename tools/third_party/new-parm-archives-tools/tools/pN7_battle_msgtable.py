#!/usr/bin/env python3
"""pN7_battle_msgtable.py — translate the in-battle MESSAGE TABLE embedded in every /BATLE/*.BBG.

TASK N7 (rc_33 playtest): running from a battle showed JP escape taunts (じゃーねーっ バイバーイ …).
That taunt is one row of a whole battle-MESSAGE TABLE. LANE FINDING (corrects the OUTSTANDING premise
"a SEPARATE block at ~0x47a00"): the table is **sec2 of the SAME 9-section BBG text item** that
tools/battle_bbg_repack.py repacks (item @ B001.BBG 0x4739c; sec2 = item off 0x420..0x674, 596 B,
bytes 0x477bc..0x47a10). The taunt string じゃーねーっ バイバーイ is unique to sec2 (byte-searched the
BBG), so sec2 IS the live render source for the escape/skill/element/revival messages.

  sec2 is NUL-separated Grandia-16x16 tbl strings, ordinal-indexed (no pointer table). The message
  renderer honours control 0x03 (switch to 8x16 half-width ASCII) — the identical mechanism proven by
  battle_mdat's enemy banner and battle_skills' sec4 descriptions. So English = 0x03 + ASCII per entry.

  Entries 0..21 duplicate the sec0 party-names / command verbs (rendered elsewhere; left vanilla).
  Entries 22..70 are the message table:
    22           skill-level-up   (『<cat>』 + this)
    23..29       weapon categories 短剣/刀剣/メイス/オノ/ムチ/射撃/未使用 (terms.json canon)
    30..33       elements ファイヤー/ウォーター/エアー/アース (Fire/Water/Wind/Earth, skillgain-consistent)
    34..36,21    skill-LEARN glue fragments (numbers+particles) — LEFT JP (unsafe to reorder; flagged)
    37,38        逃走成功/逃走失敗 escape success/failure
    39..49       サンプル placeholders (11×)
    50..65       per-character escape taunts (natural English; DM-original flavour -> exceptions.json)
    66,67,68     通常/先制攻撃/不意をつかれた battle-open messages
    69,70        Revival-Gem messages (composed with the char name between the two fragments)

SIZE / DONOR: sec2 lives INSIDE the size-locked 9-section item. English (0x03+ASCII) is longer than
the dense tbl. This tool MUST run AFTER tools/battle_bbg_repack.py (which NUL-stubs the inert sec3+sec6
as a donor pool). We GROW sec2 and SHRINK the sec6 NUL stub by the same delta, keeping item + file size
identical (sec7 descriptions untouched). Requires sec6 to be the all-NUL repack stub (asserted).

Idempotent: translated entries are 0x03+ASCII, so their JP keys no longer match on re-run -> no change.
md5-agnostic in-place disc fold across all 34 BBGs (battle_sec0.BBG_NAMES).

Usage:
    python3 tools/pN7_battle_msgtable.py plan                 # decode + translation + size delta
    python3 tools/pN7_battle_msgtable.py patch-bytes IN OUT   # translate one raw (repacked) .BBG
    python3 tools/pN7_battle_msgtable.py fold TRACK1.bin      # idempotent in-place disc fold
"""
from __future__ import annotations
import struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
import iso                 # noqa: E402
import dicdt               # noqa: E402
import battle_sec0 as bs   # _locate, BBG_NAMES  # noqa: E402

# --- translation map, keyed on ORDINAL index into sec2 (robust vs 0x03-embedded entries) ----------
# Values are the visible English; each is emitted as 0x03 + ASCII (8x16 half-width font).
# *** MIRRORED VERBATIM from the SIBLING copy in /FIELD/TEXT2.BIN *** (menus/work/text2_map.json,
# shipped since rc_24). These are the SAME battle-message strings in a second on-disc copy; the game
# renders the taunts from BBG sec2 (this table) — proven: rc_33's TEXT2.BIN taunts are already English
# yet the user still saw JP じゃーねーっ. Mirroring TEXT2's wording keeps the two copies consistent
# (CLAUDE rule 5). Composition fragments (idx21/34/35/36/69/70) reuse TEXT2's exact glue choices.
# NOTE the weapon-category / element labels here are TEXT2 canon (Knife/Shot/Axe, 'Air') which DIVERGE
# from terms.json item names (Dagger/Bow/Ax) and the skill-gain screen (Wind) — a pre-existing
# cross-surface divergence inherited from TEXT2, flagged for review, NOT introduced here.
TRANS = {
    21: "'s ",                   # の  connector: [category]+'s +[Skill level rose!]
    22: "Skill level rose!",
    23: "'Knife'",
    24: "'Sword'",
    25: "'Mace'",
    26: "'Axe'",
    27: "'Whip'",
    28: "'Shot'",
    29: "'Unused'",
    30: "'Fire'",
    31: "'Water'",
    32: "'Air'",
    33: "'Earth'",
    34: ' learned "',            # skill-LEARN glue (は１)
    35: '"',                     # 『
    36: '"!',                    # を習得
    37: "Escaped!",
    38: "Can't escape!",
    # 39..49 サンプル placeholders -> "Sample"
    50: "Yikes! Retreat!",
    51: "Let's fall back for now!",
    52: "See ya~! Bye-bye!",
    53: "What! You mean to flee?",
    54: "Back, back! We're pulling out!",
    55: "Everyone, run~!",
    56: "Waaah, run away!",
    57: "Let us retreat for now.",
    58: "Dammit, can't get away!",
    59: "Did they cut us off?",
    60: "No good! We can't flee!",
    61: "Unbelievable! We can't escape!",
    62: "Tch, missed our chance to run!",
    63: "Drat! There's no escape route!",
    64: "Drat! There are foes this way too!",
    65: "Oh dear, we can't escape like this...",
    66: "Normal!",
    67: "First strike!",
    68: "Ambushed!",
    69: "With the Revival Stone,",   # composed: idx69 + <char name> + idx70
    70: "was revived!",
}
for i in range(39, 50):
    TRANS[i] = "Sample"


def _split_nul(seg: bytes):
    out = []
    i = 0
    while i < len(seg):
        e = seg.find(b"\x00", i)
        if e < 0:
            out.append(seg[i:]); break
        out.append(seg[i:e]); i = e + 1
    return out


def translate_sec2(sec2: bytes):
    """JP sec2 -> EN sec2. Preserves entry count + exact NUL structure incl. trailing pad. Returns
    new bytes (or sec2 unchanged if already English / nothing to change)."""
    pad = len(sec2) - len(sec2.rstrip(b"\x00"))         # trailing NUL padding beyond the last entry
    core = sec2[: len(sec2) - pad]                       # does NOT end in NUL (unless empty)
    entries = _split_nul(core)
    assert b"\x00".join(entries) + b"\x00" * pad == sec2, "sec2 NUL reconstruction mismatch"
    changed = False
    out = []
    for i, e in enumerate(entries):
        en = TRANS.get(i)
        if en is not None and not (e[:1] == b"\x03"):   # idempotent: skip already-0x03 English
            out.append(b"\x03" + en.encode("ascii"))
            changed = True
        else:
            out.append(e)
    new = b"\x00".join(out) + b"\x00" * pad
    return new if changed else sec2


def _already_done(sec2: bytes):
    entries = _split_nul(sec2)
    # entry 52 (escape taunt) is our canary: vanilla tbl (high byte) vs our 0x03 English.
    return len(entries) > 52 and entries[52][:1] == b"\x03"


def repack_with_sec2(b: bytes) -> bytes:
    b = bytearray(b)
    item_off, item_len = bs._locate(b)
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    secs = [bytes(b[item_off + hdr[i]: item_off + hdr[i + 1]]) for i in range(8)]
    sec8 = bytes(b[item_off + hdr[8]: item_off + item_len])
    if _already_done(secs[2]):
        return bytes(b)  # idempotent
    # donor = the sec6 NUL stub produced by battle_bbg_repack. Require it (this tool runs AFTER repack).
    if not (len(secs[6]) and all(x == 0 for x in secs[6])):
        raise ValueError("sec6 is not the all-NUL repack stub — run battle_bbg_repack first")
    new2 = translate_sec2(secs[2])
    delta = len(new2) - len(secs[2])
    if delta < 0:
        raise ValueError("English sec2 shorter than JP?! unexpected")
    if delta > len(secs[6]):
        raise ValueError(f"sec2 grow {delta} > sec6 donor {len(secs[6])}")
    new6 = secs[6][:len(secs[6]) - delta]              # shrink the NUL stub; sec7 start unchanged
    parts = [secs[0], secs[1], new2, secs[3], secs[4], secs[5], new6, secs[7]]
    new_hdr = [0x24]
    off = 0x24
    for p in parts:
        off += len(p)
        new_hdr.append(off)
    header = bytearray()
    for v in new_hdr:
        header += struct.pack(">I", v)
    header = header[:0x24]
    body = bytes(header) + b"".join(parts) + sec8
    if len(body) != item_len:
        raise ValueError(f"item size changed {item_len}->{len(body)}")
    b[item_off: item_off + item_len] = body
    return bytes(b)


BBG_NAMES = bs.BBG_NAMES


def cmd_plan():
    import battle_bbg_repack as rp
    van = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
    with open(van, "rb") as f:
        rec = iso.find_record(f, "B001.BBG")
        b = iso.read_bytes(f, rec["lba"], rec["size"])
    rep = rp.repack_item(bytes(b))                     # simulate post-repack state
    bb = bytearray(rep)
    item_off, item_len = bs._locate(bb)
    hdr = [struct.unpack_from(">I", bb, item_off + i * 4)[0] for i in range(9)]
    sec2 = bytes(bb[item_off + hdr[2]: item_off + hdr[3]])
    sec6 = bytes(bb[item_off + hdr[6]: item_off + hdr[7]])
    entries = _split_nul(sec2)
    for i, e in enumerate(entries):
        en = TRANS.get(i)
        if en is not None:
            print(f"  [{i:2d}] {dicdt.decode(e)!r:40s} -> {en!r}")
    new2 = translate_sec2(sec2)
    print(f"\nsec2 {len(sec2)} -> {len(new2)} ({len(new2)-len(sec2):+d}); "
          f"sec6 NUL donor {len(sec6)} B; fits={len(new2)-len(sec2) <= len(sec6)}")


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
            new = repack_with_sec2(data)
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
    print(f"pN7_battle_msgtable fold: patched {done} BBG(s), skipped {skipped}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "plan":
        cmd_plan()
    elif cmd == "patch-bytes":
        Path(argv[3]).write_bytes(repack_with_sec2(Path(argv[2]).read_bytes()))
        print(f"patched {argv[2]} -> {argv[3]}")
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(f"unknown command {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
