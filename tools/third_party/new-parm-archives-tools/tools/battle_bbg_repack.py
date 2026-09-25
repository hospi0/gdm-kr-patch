#!/usr/bin/env python3
"""battle_bbg_repack.py — UNIFIED, size-preserving repack of the 9-section text item embedded in
every /BATLE/*.BBG. Supersedes the four separate BBG folds (battle_sec0 / moves_sec1 / battle_skills
/ battle_items) by composing all of their translations in ONE pass and — critically — sourcing the
extra English bytes from the truly-inert **sec3 + sec6** donor pool instead of **sec7**.

LANE BAT2 (rc_28) — why this exists:
  sec7 was assumed a "runtime placeholder" by Lanes Q/BAT, so battle_sec0(+10)/moves_sec1(+345)/
  battle_skills(+1387) grew their sections by SHRINKING sec7. But sec7 is the **512-entry item
  DESCRIPTIONS table** (real content to index 511: 火のレベルを+5 etc.), copied verbatim to LWRAM and
  indexed by the in-battle ITEM menu. Those folds therefore TRUNCATED descriptions for items ~238-511
  (Herbs/Panacea/Walnuts/magic-books) in shipped rc_24-rc_27 — a latent regression. This repack fixes
  it: sec7 is kept at its FULL vanilla length, and the donor is the pair of battle-INERT sections:
    * sec3 = a 16x16-tbl duplicate of the sec1 spell/skill names — never rendered (Lanes BAT/Q).
    * sec6 = a 16x16-tbl (KANJI) duplicate of the item-name table; the item menu renders sec5 (KANA,
      matches the user's screenshot) — sec6 is unread in battle (proven: read-watch across sec6 in
      both LWRAM copies fired 0 times over a full battle; the menu shows kana not kanji).
  Both are stubbed to NUL blocks (empty strings → blank if ever read, never garbage/crash).

TRANSLATIONS (content identical to the four legacy tools — their translate fns are reused verbatim,
so sec0/sec1/sec4 output is byte-for-byte what shipped; only the item LAYOUT/donor changes):
    sec0 -> battle_sec0.translate_sec0   (command panel, native+ASCII)
    sec1 -> moves_sec1.translate_sec1    (spell/skill names, native+ASCII)
    sec4 -> battle_skills.translate_item (spell/skill descriptions, tbl+0x03)
    sec5 -> battle_items.translate_item  (ITEM names, native+ASCII)  [NEW this round]
    sec2, sec7, sec8 kept vanilla;  sec3, sec6 -> NUL stub (donor).

EDIT MODEL: item total length is size-locked (copied to a fixed LWRAM region). We recompute the
9-uint BE header + rebuild the body so the sections sum to the SAME item length. No ISO relayout.
MUST run on vanilla-state BBGs (sec7 full) — i.e. this REPLACES the four legacy fold steps in
build_rc.py; do not also run them. Idempotent (re-run detects the sec6 NUL stub and skips).

Usage:
    python3 tools/battle_bbg_repack.py plan                 # budgets + deltas for B001/BTEST
    python3 tools/battle_bbg_repack.py patch-bytes IN OUT   # repack one raw .BBG file
    python3 tools/battle_bbg_repack.py fold TRACK1.bin      # md5-agnostic, idempotent, in-place
"""
from __future__ import annotations
import struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
import iso                 # noqa: E402
import battle_sec0 as bs   # _locate, translate_sec0, BBG_NAMES  # noqa: E402
import moves_sec1 as m1    # translate_sec1  # noqa: E402
import battle_skills as bk  # translate_item -> new sec4  # noqa: E402
import battle_items as bi   # translate_item -> new sec5  # noqa: E402

STUB3 = 4  # bytes kept for the sec3 stub (rest of the donor slack lands in sec6)


def _sections(b, item_off, item_len):
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    secs = [bytes(b[item_off + hdr[i]: item_off + hdr[i + 1]]) for i in range(8)]
    sec8 = bytes(b[item_off + hdr[8]: item_off + item_len])
    return hdr, secs, sec8


def _already_repacked(secs):
    # sec6 (kanji item names) is NUL-stubbed by us -> all zero. Vanilla sec6 has tbl bytes.
    return len(secs[6]) == 0 or all(x == 0 for x in secs[6])


def repack_item(b: bytes) -> bytes:
    b = bytearray(b)
    item_off, item_len = bs._locate(b)
    hdr, secs, sec8 = _sections(b, item_off, item_len)
    if _already_repacked(secs):
        return bytes(b)  # idempotent: already done

    new0 = bs.translate_sec0(secs[0])[0]
    new1 = m1.translate_sec1(secs[1], prefix03=True)[0]  # 0x03+ASCII: O3 banner reroute reads sec1 names
    new4 = bk.translate_item(secs)
    new4 = secs[4] if new4 is None else new4
    new5 = bi.translate_item(secs)
    new5 = secs[5] if new5 is None else new5
    sec2, sec7 = secs[2], secs[7]                 # sec7 kept FULL (restores descriptions)

    fixed = 0x24 + len(new0) + len(new1) + len(sec2) + len(new4) + len(new5) + len(sec7) + len(sec8)
    donor = item_len - fixed                       # bytes available for the sec3+sec6 stub
    if donor < 0:
        raise ValueError(f"repack overflow by {-donor} B (item {item_len}); need a bigger donor")
    n3 = min(STUB3, donor)
    new3 = b"\x00" * n3
    new6 = b"\x00" * (donor - n3)

    parts = [new0, new1, sec2, new3, new4, new5, new6, sec7]   # sec0..sec7
    new_hdr = [0x24]
    off = 0x24
    for p in parts:
        off += len(p)
        new_hdr.append(off)                        # hdr[1..8] = cumulative starts of sec1..sec8
    # new_hdr now has 9 entries hdr[0..8]; hdr[8] = start of sec8
    header = bytearray()
    for v in new_hdr:
        header += struct.pack(">I", v)
    header = header[:0x24]
    body = bytes(header) + b"".join(parts) + sec8
    if len(body) != item_len:
        raise ValueError(f"repack size {len(body)} != item_len {item_len}")
    b[item_off: item_off + item_len] = body
    return bytes(b)


BBG_NAMES = bs.BBG_NAMES


def cmd_plan():
    van = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
    with open(van, "rb") as f:
        for name in ["B001.BBG", "BTEST.BBG"]:
            rec = iso.find_record(f, name)
            b = iso.read_bytes(f, rec["lba"], rec["size"])
            item_off, item_len = bs._locate(bytearray(b))
            hdr, secs, sec8 = _sections(bytearray(b), item_off, item_len)
            new0 = bs.translate_sec0(secs[0])[0]
            new1 = m1.translate_sec1(secs[1], prefix03=True)[0]  # 0x03+ASCII: O3 banner reroute reads sec1 names
            new4 = bk.translate_item(secs) or secs[4]
            new5 = bi.translate_item(secs) or secs[5]
            fixed = 0x24 + len(new0) + len(new1) + len(secs[2]) + len(new4) + len(new5) + \
                len(secs[7]) + len(sec8)
            donor = item_len - fixed
            print(f"{name}: item={item_len}  sec0 {len(secs[0])}->{len(new0)}  "
                  f"sec1 {len(secs[1])}->{len(new1)}  sec4 {len(secs[4])}->{len(new4)}  "
                  f"sec5 {len(secs[5])}->{len(new5)}  sec7 FULL {len(secs[7])}  "
                  f"| sec3+sec6 stub budget {donor}  (was {len(secs[3])+len(secs[6])})  "
                  f"fits={donor >= 0}")


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
            new = repack_item(data)
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
    print(f"battle_bbg_repack fold: repacked {done} BBG(s), skipped {skipped}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "plan":
        cmd_plan()
    elif cmd == "patch-bytes":
        Path(argv[3]).write_bytes(repack_item(Path(argv[2]).read_bytes()))
        print(f"repacked {argv[2]} -> {argv[3]}")
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(f"unknown command {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
