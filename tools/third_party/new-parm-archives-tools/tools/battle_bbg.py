#!/usr/bin/env python3
"""battle_bbg.py — translate the in-battle UI text embedded in every /BATLE/B*.BBG.

WHY THIS FILE EXISTS (source map, proven in Lane Q — see docs/lanes/laneQ-battle.md):
  The live battle renderer does NOT read /BATLE/TEXT2.BIN (that file is a dead duplicate;
  rc_24 even relocated it, to no effect). Instead, every battle-background bundle
  `/BATLE/B001..B032.BBG`, `B255.BBG`, `BTEST.BBG` embeds its OWN copy of a small
  TEXT2-shaped text file, and the engine loads THAT (to LWRAM ~0x239000 / 0x2c3700) and
  pre-rasterises the UI strings into a VDP1 sprite atlas at battle start.

CONTAINER (per BBG, all offsets big-endian; found by a generic recursive parser):
  root archive  ->  child[last]  = the text sub-resource (ends at EOF)
                    within it, item[1] = the text file (a 9-uint32 section header + data)
  The 9-uint header's entries are offsets RELATIVE TO THE ITEM. Section map:
    sec0/1  : spell/skill short names        sec2 : PARTY NAMES + COMMANDS + Critical/Combo
    sec3    : spell names                          + "Command" + escape/battle/revive messages
    sec4    : spell descriptions              sec5 : (runtime-overwritten placeholder)
    sec6/7  : (runtime-overwritten placeholders — item names / descriptions get written here
              at battle start from the player's inventory)
    sec8    : AI tactics menu
  sec2 is BYTE-IDENTICAL across all 33 gameplay BBGs (BTEST differs slightly downstream).

EDIT MODEL (safe, in-place, no disc relayout — see report for the reasoning):
  Correct English is byte-longer than the dense JP, so sec2 must grow. We keep the ITEM
  (and therefore the FILE) exactly the same size by GROWING sec2 and SHRINKING the trailing
  runtime-placeholder section sec7 by the same delta. Only the 9-uint item header + sec2 +
  sec7 bytes change; the container/root/ISO offsets are untouched, so this fits inside every
  BBG's existing sector span (some have <300 B slack) and needs no pointer surgery.

  This assumes the runtime item-description fill honours the (rewritten) sec7 header offset.
  VALIDATE in a FRESH battle (Lane Q route: save `pQ-field-earthfloor`, walk into the enemy)
  that (a) party/command text is English and (b) the in-battle item menu is not corrupted.

Usage:
    python3 tools/battle_bbg.py plan                 # show translated sec2 + delta
    python3 tools/battle_bbg.py patch-bytes IN OUT   # translate one raw .BBG file
    python3 tools/battle_bbg.py fold TRACK1.bin      # md5-gated in-place patch of a disc track
"""
from __future__ import annotations
import struct, sys, hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "menus"))
import iso                       # noqa: E402
import dicdt                     # noqa: E402
import battle_text               # noqa: E402

FWD, REV = dicdt.FWD, dicdt.REV


def _enc16(s: str):
    out = bytearray()
    for ch in s:
        if ch not in REV:
            return None
        out += REV[ch]
    return bytes(out)


# Anchor = the leader-name slot (sec2 entry #1, the byte string that renders as the party
# leader's name). It is KEPT verbatim by the translator, so it survives patching — which makes
# _locate work on both vanilla and already-English BBGs (needed for idempotent folding).
LEADER_SIG = bytes.fromhex("0397c298a582d004")   # unique in every BBG (verified)


# ---- generic recursive archive parse: find the text item + its container -------------------
def _is_dir(b, base, size):
    if size < 8:
        return None
    first = struct.unpack_from(">I", b, base)[0]
    if first % 4 or not (8 <= first <= min(size, 0x100)):
        return None
    n = first // 4
    offs = [struct.unpack_from(">I", b, base + i * 4)[0] for i in range(n)]
    if any(o > size for o in offs):
        return None
    return offs


def _locate(b):
    """Return (item_off, item_len, sub_dir_off, item_index) for the sec2-bearing text item."""
    target = b.find(LEADER_SIG)
    if target < 0:
        raise ValueError("leader-slot sig not found — not a battle BBG?")
    chain = []

    def rec(base, size):
        offs = _is_dir(b, base, size)
        if offs is None:
            return
        ends = offs + [size]
        for i in range(len(offs)):
            cs, ce = base + offs[i], base + ends[i + 1]
            if cs <= target < ce:
                chain.append((base, i, cs, ce - cs))
                rec(cs, ce - cs)
                return
    rec(0, len(b))
    # chain[-1] = sec2 (dir = the item). chain[-2] = item within sub-resource dir.
    item_dir_base, sec2_idx, sec2_off, sec2_len = chain[-1]
    sub_dir_base, item_idx, item_off, item_len = chain[-2]
    return item_off, item_len, sub_dir_base, item_idx


def translate_sec2(sec2: bytes):
    """JP sec2 -> EN sec2 (0x03 + ASCII). Untranslatable entries kept verbatim.
    Returns (new_bytes, notes)."""
    # Walk maximal non-NUL runs; copy every NUL byte verbatim. This preserves the exact
    # terminator/padding structure (so the transform is idempotent — re-running on already
    # English text is a no-op).
    out = bytearray()
    notes = []
    i = 0
    n = len(sec2)
    while i < n:
        if sec2[i] == 0:
            out += b"\x00"
            i += 1
            continue
        j = sec2.index(0, i) if 0 in sec2[i:] else n
        s = sec2[i:j]
        jp = dicdt.decode(s)
        en = battle_text.translate(jp)
        if en is None:
            out += s                    # verbatim (leader-name slot, "は%d を習得" fmt, English…)
            notes.append(("KEEP", jp))
        else:
            out += b"\x03" + en.encode("ascii")
            notes.append(("EN", jp, en))
        i = j
    return bytes(out), notes


def patch_bbg(b: bytes) -> bytes:
    b = bytearray(b)
    item_off, item_len, sub_dir_base, item_idx = _locate(b)
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    sec = lambda i: b[item_off + hdr[i]: item_off + (hdr[i + 1] if i + 1 < 9 else item_len)]
    sec2 = sec(2)
    new_sec2, _ = translate_sec2(bytes(sec2))
    delta = len(new_sec2) - len(sec2)
    if delta < 0:
        new_sec2 = new_sec2 + b"\x00" * (-delta)       # never shrink sec2 below original
        delta = 0
    sec7 = sec(7)
    if delta > len(sec7) - 4:
        raise ValueError(f"delta {delta} too large for sec7 donor ({len(sec7)} B)")
    new_sec7 = sec7[: len(sec7) - delta]               # shrink runtime placeholder by delta
    # rebuild item: header (sec3..sec7 += delta, sec8 unchanged), then sections
    new_hdr = hdr[:3] + [hdr[i] + delta for i in range(3, 8)] + [hdr[8]]
    parts = bytearray()
    for v in new_hdr:
        parts += struct.pack(">I", v)
    parts = parts[: hdr[0]]                              # header occupies hdr[0] bytes (0x24)
    body = bytearray(b[item_off + hdr[0]: item_off + item_len])   # sec0..sec8 concatenated
    # replace sec2 and sec7 within body (offsets relative to item, minus header size)
    def splice(dst, old_lo, old_hi, new):
        return dst[:old_lo] + new + dst[old_hi:]
    H = hdr[0]
    # do sec7 first (higher offset) so sec2 splice indexes stay valid
    body = splice(body, hdr[7] - H, (hdr[8]) - H, new_sec7)
    body = splice(body, hdr[2] - H, hdr[3] - H, new_sec2)
    new_item = bytes(parts) + bytes(body)
    if len(new_item) != item_len:
        raise ValueError(f"item size changed {item_len}->{len(new_item)} (delta {delta})")
    b[item_off: item_off + item_len] = new_item
    return bytes(b)


# ---------------------------------------------------------------------------------------------
def cmd_plan():
    van = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
    with open(van, "rb") as f:
        rec = iso.find_record(f, "B001.BBG")
        b = iso.read_bytes(f, rec["lba"], rec["size"])
    item_off, item_len, _, _ = _locate(bytearray(b))
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    sec2 = b[item_off + hdr[2]: item_off + hdr[3]]
    new_sec2, notes = translate_sec2(bytes(sec2))
    print(f"sec2 {len(sec2)} -> {len(new_sec2)} B (delta {len(new_sec2)-len(sec2)}); "
          f"sec7 donor {hdr[8]-hdr[7]} B")
    for n in notes:
        if n[0] == "EN":
            print(f"   {n[1]!r} -> {n[2]!r}")
        else:
            print(f"   KEEP {n[1]!r}")


def cmd_patch_bytes(inp, out):
    data = Path(inp).read_bytes()
    Path(out).write_bytes(patch_bbg(data))
    print(f"patched {inp} -> {out}")


BBG_NAMES = [f"B{n:03d}.BBG" for n in range(1, 33)] + ["B255.BBG", "BTEST.BBG"]


def cmd_fold(track):
    """In-place, size-preserving, md5-gated patch of every BBG on a disc track."""
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
    print(f"battle_bbg fold: patched {done} BBG(s), skipped {skipped} (already-English/unchanged)")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "plan":
        cmd_plan()
    elif cmd == "patch-bytes":
        cmd_patch_bytes(argv[2], argv[3])
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(f"unknown command {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
