#!/usr/bin/env python3
"""battle_item_desc.py — English for the in-battle ITEM-menu DESCRIPTION box (BBG sec7).

LANE O6 (rc_32) verdict, see docs/lanes/laneO6-item-desc.md:
  The in-battle item DESCRIPTION box renders from **sec7** of the 9-section text item embedded in
  every /BATLE/*.BBG (LWRAM 0x239000, header[7]). sec7[i] is index-aligned with the item NAME
  (sec5[i], already English) and the KANJI name key (sec6[i]). Proven live: on the shipped rc_32
  disc, LWRAM 0x239000 header[7]=0x2c64 holds sec7[63]='攻撃十５０ 昔リリィが使っていた' exactly while
  sec5[63]='Pirate Knife' renders — i.e. the box the user photographed reads sec7.

  *** The English SOURCE EXISTS in-repo *** (correcting the earlier "no source" DEFER):
  menus/field_desc.translate (-> wdata_desc4 + wdata_desc8) is keyed by the SAME JP strings sec7
  holds in 16x16 tbl. On the standard gameplay BBG (B001, shared by 30/34 BBGs) ALL 288 real item
  descriptions translate; the other 224 slots are placeholders (きんし/禁/blank). Zero translation gap.

  *** The blocker is SIZE, quantified: ***
  English sec7 (0x03+ASCII, like the sec4 skill descriptions) = +2445 B larger than the dense 2-byte
  JP tbl. The item is size-locked at 0x4424 B (copied to a fixed LWRAM window; 0x239000+0x4424 =
  0x23d424 holds unrelated live data). The unified repack (battle_bbg_repack.py) already spends the
  only inert donor (sec3+sec6) keeping sec7 FULL JP, leaving ~719 B slack (B001) — far short of
  +2445. Even stubbing sec3+sec6 to ZERO the full-English item overflows by 1726 B (B001)/297 B
  (BTEST). => full English descriptions need engine RE to relocate/enlarge the LWRAM item copy
  (out of scope for a data-fold lane).

WHAT THIS TOOL PROVIDES (the translation half, ready for a future relocation unlock):
  * plan                 -> per-BBG coverage + byte budget + overflow (the quantified DEFER).
  * emit-sec7 NAME OUT   -> writes the FULL English sec7 bytes (0x03+ASCII) for a relocation lane.
  * patch-bytes IN OUT   -> full-English size-preserving repack; RAISES with the exact overflow on
                            the current size-locked item (documents the wall in code) and SUCCEEDS
                            automatically once item_len is enlarged by a relocation.
  * patch-bytes IN OUT --partial
                         -> SIZE-SAFE greedy fold: Englishise as many descriptions as fit the inert
                            donor (cheapest-first), rest kept JP; item length preserved, idempotent.
                            Produces a MIXED EN/JP list (~147/288 on B001) — an OPTIONAL coordinator
                            choice, NOT wired into build_rc.py. Zero regression vs the all-JP status quo.

NOT WIRED into tools/build_rc.py (full-English is size-walled; partial is a product decision).
"""
from __future__ import annotations
import struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "menus"))
import iso                 # noqa: E402
import dicdt               # noqa: E402
import battle_sec0 as bs   # _locate, translate_sec0, BBG_NAMES  # noqa: E402
import moves_sec1 as m1    # translate_sec1  # noqa: E402
import battle_skills as bk # translate_item -> sec4, ordwalk  # noqa: E402
import battle_items as bi  # translate_item -> sec5  # noqa: E402
import field_desc          # translate(jp) -> EN item description  # noqa: E402

VAN = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"


def _sections(b, item_off, item_len):
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    secs = [bytes(b[item_off + hdr[i]: item_off + hdr[i + 1]]) for i in range(8)]
    sec8 = bytes(b[item_off + hdr[8]: item_off + item_len])
    return hdr, secs, sec8


def _en_entry(jp: str):
    """English 0x03+ASCII payload for a JP description, or None if untranslatable/non-ASCII."""
    en = field_desc.translate(jp) if jp else None
    if en is None:
        return None
    try:
        return b"\x03" + en.encode("ascii")
    except UnicodeEncodeError:
        return None


def _decode(e: bytes):
    try:
        return dicdt.decode(e)
    except Exception:
        return None


def build_sec7(sec7: bytes, budget=None):
    """Rebuild sec7 with English descriptions.
    budget=None -> full English (all translatable entries).
    budget=int  -> greedy cheapest-first, only entries whose cumulative growth <= budget.
    Returns (new_sec7, n_translated, n_translatable, growth)."""
    ents = bk.ordwalk(sec7)
    trailing_nul = bool(sec7) and sec7[-1] == 0
    # candidate deltas
    cand = {}
    for i, e in enumerate(ents):
        if not e:
            continue
        pay = _en_entry(_decode(e))
        if pay is not None:
            cand[i] = (pay, (len(pay) + 1) - (len(e) + 1))
    chosen = set()
    if budget is None:
        chosen = set(cand)
    else:
        for i, (_, d) in sorted(cand.items(), key=lambda kv: kv[1][1]):
            g = sum(cand[j][1] for j in chosen) + d
            if g <= budget:
                chosen.add(i)
    out = bytearray()
    for i, e in enumerate(ents):
        if i in chosen:
            out += cand[i][0] + b"\x00"
        else:
            out += e + b"\x00"
    if not trailing_nul and out and out[-1] == 0:
        out = out[:-1]
    growth = sum(cand[i][1] for i in chosen)
    return bytes(out), len(chosen), len(cand), growth


def _compose(secs, sec8, item_len, new7):
    """Full size-preserving repack with English sec0/1/4/5 + given sec7; donor = sec3+sec6 stub.
    Raises ValueError(overflow) if it does not fit. Mirrors battle_bbg_repack layout."""
    new0 = bs.translate_sec0(secs[0])[0]
    new1 = m1.translate_sec1(secs[1], prefix03=True)[0]
    new4 = bk.translate_item(secs) or secs[4]
    new5 = bi.translate_item(secs) or secs[5]
    fixed = 0x24 + len(new0) + len(new1) + len(secs[2]) + len(new4) + len(new5) + len(new7) + len(sec8)
    donor = item_len - fixed
    if donor < 0:
        raise ValueError(f"size-lock overflow by {-donor} B (item_len={item_len}); "
                         f"needs engine-RE relocation of the LWRAM item copy")
    n3 = min(4, donor)
    parts = [new0, new1, secs[2], b"\x00" * n3, new4, new5, b"\x00" * (donor - n3), new7]
    hdr = [0x24]
    off = 0x24
    for p in parts:
        off += len(p)
        hdr.append(off)
    header = b"".join(struct.pack(">I", v) for v in hdr)[:0x24]
    body = header + b"".join(parts) + sec8
    assert len(body) == item_len, (len(body), item_len)
    return body


def patch_bbg(b: bytes, partial=False) -> bytes:
    b = bytearray(b)
    item_off, item_len = bs._locate(b)
    hdr, secs, sec8 = _sections(b, item_off, item_len)
    if partial:
        # budget = free space if sec7 stays JP under the composed layout (the repack's donor slack)
        base = _compose(secs, sec8, item_len, secs[7])  # never overflows (this is the shipped repack)
        # measure slack by composing with a zero-growth sec7 then see donor
        new0 = bs.translate_sec0(secs[0])[0]
        new1 = m1.translate_sec1(secs[1], prefix03=True)[0]
        new4 = bk.translate_item(secs) or secs[4]
        new5 = bi.translate_item(secs) or secs[5]
        fixed = 0x24 + len(new0) + len(new1) + len(secs[2]) + len(new4) + len(new5) + len(secs[7]) + len(sec8)
        budget = item_len - fixed
        new7, nt, cap, growth = build_sec7(secs[7], budget=budget)
    else:
        new7, nt, cap, growth = build_sec7(secs[7], budget=None)
    body = _compose(secs, sec8, item_len, new7)
    b[item_off: item_off + item_len] = body
    return bytes(b)


BBG_NAMES = bs.BBG_NAMES


def cmd_plan():
    with open(VAN, "rb") as f:
        for name in ["B001.BBG", "B005.BBG", "BTEST.BBG"]:
            rec = iso.find_record(f, name)
            if not rec:
                continue
            b = bytearray(iso.read_bytes(f, rec["lba"], rec["size"]))
            item_off, item_len = bs._locate(b)
            hdr, secs, sec8 = _sections(b, item_off, item_len)
            full7, nt, cap, g_full = build_sec7(secs[7], budget=None)
            # donor slack with JP sec7
            new0 = bs.translate_sec0(secs[0])[0]
            new1 = m1.translate_sec1(secs[1], prefix03=True)[0]
            new4 = bk.translate_item(secs) or secs[4]
            new5 = bi.translate_item(secs) or secs[5]
            fixed = 0x24 + len(new0) + len(new1) + len(secs[2]) + len(new4) + len(new5) + len(secs[7]) + len(sec8)
            budget = item_len - fixed
            _, np_, _, g_part = build_sec7(secs[7], budget=budget)
            overflow = g_full - budget
            print(f"{name}: item_len={item_len} sec7 JP={len(secs[7])} EN={len(full7)} (+{g_full})")
            print(f"   translatable real descriptions: {cap}   (rest placeholders)")
            print(f"   inert donor budget (sec3+sec6 stub) = {budget} B")
            print(f"   FULL English -> overflow {overflow:+d} B  => {'FITS' if overflow<=0 else 'DOES NOT FIT (engine-RE needed)'}")
            print(f"   PARTIAL (size-safe) -> {np_}/{cap} descriptions English, 0 regression\n")


def cmd_emit(name, out):
    with open(VAN, "rb") as f:
        rec = iso.find_record(f, name)
        b = bytearray(iso.read_bytes(f, rec["lba"], rec["size"]))
    item_off, item_len = bs._locate(b)
    _, secs, _ = _sections(b, item_off, item_len)
    new7, nt, cap, g = build_sec7(secs[7], budget=None)
    Path(out).write_bytes(new7)
    print(f"wrote full English sec7 ({len(new7)} B, {nt}/{cap} translated) -> {out}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "plan":
        cmd_plan()
    elif cmd == "emit-sec7":
        cmd_emit(argv[2], argv[3])
    elif cmd == "patch-bytes":
        partial = "--partial" in argv
        args = [a for a in argv[2:] if not a.startswith("--")]
        Path(args[1]).write_bytes(patch_bbg(Path(args[0]).read_bytes(), partial=partial))
        print(f"repacked {args[0]} -> {args[1]} (partial={partial})")
    else:
        print(f"unknown command {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
