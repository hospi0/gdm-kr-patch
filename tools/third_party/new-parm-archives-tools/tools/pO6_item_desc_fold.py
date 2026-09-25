#!/usr/bin/env python3
"""pO6_item_desc_fold.py — SHIP full-English in-battle ITEM DESCRIPTIONS (BBG sec7) by GROWING the
embedded text item, G1-style, instead of the (false) fixed-size-window assumption.

============================================================================================
LANE O6 rc_40 BREAKTHROUGH — the "size wall" was a misread, PROVEN live (see docs/lanes/laneO6-*):
  The prior DEFER said the item is copied to a FIXED LWRAM window 0x239000..0x23d424 and 0x23d424
  holds "unrelated live data", so the item can't grow. TRACED LIVE (fresh battle, pQ-field-earthfloor
  + longbattle):
    * The item is copied by a GENERIC word-memcpy at 0x06010414 with dst=0x239000, src=0x2C339C,
      len = **r6 = 0x4424 = item_len read from the archive** (NOT a hardcoded constant; 0x4424 /
      0x23d424 appear as literals NOWHERE in MGDAT/BATLE/resident). => the copy length is DATA-DRIVEN.
    * A full 4200-frame battle read/write-watch on 0x23D440 / 0x23E800 / 0x23F800 fired **0 times**:
      the region past the item (0x23D424 .. next anchor 0x240000, ~11 KB) is DEAD during battle. The
      "live data" the prior lane saw at 0x23d424 was STALE savestate content, never used.
    * The only hardcoded anchors around the item are 0x239000 (item base, 21 refs) and 0x240000; the
      ~0x2BDC (11228 B) gap between item-end and 0x240000 is free headroom — far more than the +2445 B
      (B001) / +4180 (B005) / +1242 (BTEST) full-English needs.
  => Grow the on-disc item and the memcpy naturally copies the larger item into the dead headroom.

WHY THIS MATCHES G1 (the user's hypothesis, CONFIRMED): the upstream TrekkiesUnite BBGFileReconstructor
  (tools/vendor/.../file/BBGFileReconstructor.java) GROWS the BBG text portion freely and RECOMPUTES
  the file pointer table on size change — it does NO engine RE (the only vendor patches are field/menu:
  jaxb, headless-cli, pathsep, menu-editor, widen-script-offsets). That only works if the Grandia
  battle engine sizes the LWRAM item copy from the archive — which DM inherits (proven above). This
  tool ports that reconstruction: grow item entry[1], shift the trailing text-portion entries, grow
  the BBG file, and relocate it in the ISO (src/relayout.py, same as facer_quips' FACE2 relocation).

ARCHIVE SHAPE (B001; _locate chain, verified):
  lvl0 BBG root: 10 ptrs, entry[9] (0x46a38) = the text portion (== G1 TEXT_OFFSET 36). LAST entry,
                 so file growth just appends — no lvl0 ptr edit needed.
  lvl1 text portion @0x46a38: 8 ptrs [0x20,0x964,0x4d88,...]; entry[1] (0x4739c, len 0x4424) = the
                 9-section text ITEM the battle box reads. Growing it by `delta` => ptr[2..7] += delta.
  lvl2 item @0x4739c: 9-section header (sec0..sec8); rebuilt with full-English sec7 (0x03+ASCII).

Commands:
  plan                         per-BBG grow delta + new item_len + new file size.
  emit-grown-bbg IN OUT        write a GROWN .BBG (full-English item) — file bigger by delta.
  emit-grown-item IN OUT       just the grown item bytes (for live-injection validation).
  fold TRACK1.bin              idempotent disc fold: grow every gameplay BBG's item to full English
                               and relocate via src/relayout.py. Runs AFTER battle_bbg_repack (step 8).
"""
from __future__ import annotations
import struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "menus"))
import iso                    # noqa: E402
import battle_sec0 as bs      # _locate / LEADER_SIG / translate_sec0  # noqa: E402
import moves_sec1 as m1       # noqa: E402
import battle_skills as bk    # noqa: E402
import battle_items as bi     # noqa: E402
import battle_item_desc as bid  # build_sec7 / _sections  # noqa: E402

VAN = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
GAMEPLAY_BBGS = None  # filled lazily = all B*.BBG that carry the standard item


def _chain(b):
    """Return (lvl0_offsets, textportion_off, textportion_offsets, item_idx, item_off, item_len).
    Mirrors battle_sec0._locate but exposes the enclosing text-portion pointer table so we can grow."""
    target = b.find(bs.LEADER_SIG)
    if target < 0:
        raise ValueError("not a battle BBG (no leader sig)")
    chain = []

    def is_dir(base, size):
        if base + 4 > len(b):
            return None
        first = struct.unpack_from(">I", b, base)[0]
        if first % 4 or not (8 <= first <= min(size, 0x100)):
            return None
        n = first // 4
        offs = [struct.unpack_from(">I", b, base + i * 4)[0] for i in range(n)]
        if any(o > size for o in offs):
            return None
        return offs

    def rec(base, size):
        offs = is_dir(base, size)
        if offs is None:
            return
        ends = offs + [size]
        for i in range(len(offs)):
            cs, ce = base + offs[i], base + ends[i + 1]
            if cs <= target < ce:
                chain.append((base, i, cs, ce - cs, offs))
                rec(cs, ce - cs)
                return
    rec(0, len(b))
    # chain[-2] = the item entry; its dir_base = the text portion
    tp_base, item_idx, item_off, item_len, tp_offs = chain[-2]
    return tp_base, item_idx, item_off, item_len, tp_offs


def _grow_full_item(secs, sec8, orig_item_len):
    """Compose a FULL-English item: PRESERVE every input section verbatim and only swap sec7
    (JP -> full-English 0x03+ASCII), then let the item GROW by the sec7 delta.

    Runs on the output of tools/battle_bbg_repack.py (build_rc step 8), where sec0/1/4/5 are already
    the shipped English (sec1 carries the O3-banner 0x03 prefix) and sec3/sec6 are already NUL stubs.
    We must NOT re-translate those (re-running translate_sec1 on already-English input drops the 0x03
    prefix -> banner-font regression). So sec7 is the ONLY section rebuilt; everything else is kept
    byte-identical. This is what makes the fold compose exactly on top of the repack, idempotently."""
    new7, nt, cap, growth = bid.build_sec7(secs[7], budget=None)   # full English (0x03+ASCII)
    parts = [secs[0], secs[1], secs[2], secs[3], secs[4], secs[5], secs[6], new7]
    hdr = [0x24]
    off = 0x24
    for p in parts:
        off += len(p)
        hdr.append(off)               # hdr[1..8]
    header = b"".join(struct.pack(">I", v) for v in hdr)[:0x24]
    body = header + b"".join(parts) + sec8
    # *** ALIGNMENT INVARIANT (rc_47 root-cause fix, Lane W5): every text-portion pointer-table
    # offset in the vanilla archives is 4-byte aligned (item_off too), and the engine copies the
    # sibling entries with word/longword loops (e.g. the word-memcpy at 0x06010414). Growing the
    # item by a non-multiple-of-4 delta shifts entries[2..7] onto misaligned staged addresses ->
    # SH-2 address errors in the sprite-setup copies -> the rc_40 "empty floor" regression.
    # (rc_40 blamed absolute-address sibling readers; re-tracing the watch hits showed both
    # "proven sites" were correctly-shifted archive-driven copies merely sweeping the watched
    # addresses — the real breaker was this alignment: B001 delta 0x98D %4=1, BTEST 0x4DA %4=2.)
    body += b"\x00" * (-len(body) % 4)
    return body, nt, cap


def grow_bbg(b: bytes):
    """Return (new_bbg_bytes, delta, info). Grows the embedded item to full English, shifting the
    trailing text-portion entries and appending `delta` bytes to the file (G1 reconstruction)."""
    b = bytearray(b)
    tp_base, item_idx, item_off, item_len, tp_offs = _chain(b)
    hdr, secs, sec8 = bid._sections(b, item_off, item_len)
    grown_item, nt, cap = _grow_full_item(secs, sec8, item_len)
    new_len = len(grown_item)
    delta = new_len - item_len
    if delta < 0:
        # English somehow smaller (already grown / all placeholders): pad to keep >= orig so idempotent
        delta = 0
    # idempotent: if item is already full English (sec6 stub + sec7 has 0x03 ASCII entries), skip
    if _already_grown(secs):
        return bytes(b), 0, {"skip": True, "item_len": item_len}
    # item ends at item_off+item_len; everything after shifts by delta
    tail_start = item_off + item_len
    new_b = bytes(b[:item_off]) + grown_item + bytes(b[tail_start:])
    # rewrite the text-portion pointer table: entries after item_idx += delta
    nb = bytearray(new_b)
    for j in range(item_idx + 1, len(tp_offs)):
        v = tp_offs[j] + delta
        struct.pack_into(">I", nb, tp_base + j * 4, v)
    info = {"item_len": item_len, "new_item_len": new_len, "delta": delta,
            "translated": nt, "translatable": cap, "old_file": len(b), "new_file": len(nb)}
    return bytes(nb), delta, info


def _already_grown(secs):
    """True if the item already carries a full-English sec7 (sec7 entries start with 0x03)."""
    ents = bk.ordwalk(secs[7])
    en = sum(1 for e in ents if e[:1] == b"\x03")
    return en > 50  # full English has ~288; JP has 0


# ---------------- CLI ----------------
def cmd_plan():
    import iso as _iso
    names = _bbg_names()
    with open(VAN, "rb") as f:
        for name in ["B001.BBG", "B005.BBG", "BTEST.BBG"]:
            rec = _iso.find_record(f, name)
            if not rec:
                continue
            b = bytearray(_iso.read_bytes(f, rec["lba"], rec["size"]))
            _, delta, info = grow_bbg(b)
            print(f"{name}: item_len 0x{info['item_len']:x} -> 0x{info.get('new_item_len',0):x} "
                  f"(+{info.get('delta',0)} B); file {info.get('old_file')} -> {info.get('new_file')}; "
                  f"{info.get('translated')}/{info.get('translatable')} English")


def _bbg_names():
    return None


def cmd_emit_bbg(inp, out):
    b = Path(inp).read_bytes()
    nb, delta, info = grow_bbg(b)
    Path(out).write_bytes(nb)
    print(f"grew {inp} -> {out}: +{delta} B, item_len -> 0x{info.get('new_item_len',0):x}, "
          f"{info.get('translated')}/{info.get('translatable')} English")


def cmd_emit_item(inp, out):
    b = bytearray(Path(inp).read_bytes())
    _, _, item_off, item_len, _ = _chain(b)
    hdr, secs, sec8 = bid._sections(b, item_off, item_len)
    grown, nt, cap = _grow_full_item(secs, sec8, item_len)
    Path(out).write_bytes(grown)
    print(f"grown item: 0x{item_len:x} -> 0x{len(grown):x} B (+{len(grown)-item_len}); "
          f"{nt}/{cap} English -> {out}")


FOLD_ENABLED = True  # ENABLED rc_47 (Lane W5): the rc_40 "absolute sibling refs" wall was a
# misdiagnosis — the real breaker was grow-delta ALIGNMENT (see _grow_full_item). Wired into
# build_rc.py step 8 (after battle_bbg_repack + pN7_battle_msgtable + battle_mdat).


def cmd_fold(track, force=False):
    """Idempotent disc fold: grow every /BATLE gameplay BBG's embedded text item to FULL-English sec7
    and relocate the grown file (append at track end + repoint its ISO dir record — src/relayout.py's
    technique). Composes on top of tools/battle_bbg_repack.py + pN7_battle_msgtable (build_rc step 8):
    reads the repacked item, preserves sec0..6/sec8 byte-identical, only enlarges sec7.

    HISTORY of the rc_40 gate (LIFTED rc_47, Lane W5 — docs/lanes/laneO6-item-desc.md):
      rc_40 blamed battle-setup code reading text-portion siblings at ABSOLUTE pre-shift addresses
      (pc 0x06010420 @0x2C7800, pc 0x060608EC @0x2D6E30) for the empty-floor sprite regression on
      grown discs. Re-tracing those watch events (the harness logs R0-R15 + PR per hit) showed BOTH
      were archive-driven copies that had CORRECTLY followed the shift and merely swept past the
      watched addresses mid-copy (site 1 = the item word-memcpy itself: src start r11=0x2C339C,
      cursor passing 0x2C7800, total r7*2 = the GROWN item_len; site 2 = the entry[5]->sound-RAM
      0x05A15200 byte-memmove: src 0x2D25C0+delta — correctly shifted — len 0x4870 = entry[5] size
      exactly). There are NO absolute sibling refs; the engine is archive-driven throughout.
      The real breaker: rc_40's grow delta (B001 +0x98D) was not a multiple of 4, shifting
      entries[2..7] onto misaligned staged addresses — vanilla pointer tables are universally
      4-aligned and the setup copies use word/long loops -> SH-2 address errors -> dead sprite
      pipeline. _grow_full_item now pads the grown item to 4 bytes; a fresh battle from the folded
      disc renders sprites, opens the item menu, shows English descriptions, completes, and the
      post-battle screens are fine (PNG-proven: docs/lanes/laneO6-fold-*.png)."""
    if not (FOLD_ENABLED or force):
        raise SystemExit(
            "pO6 fold is disabled (FOLD_ENABLED=False). It is ship-enabled since rc_47; "
            "see docs/lanes/laneO6-item-desc.md.")
    import relayout as RL
    from battle_sec0 import BBG_NAMES
    done = skipped = appended_sectors = 0
    with open(track, "r+b") as f:
        for name in BBG_NAMES:
            rec = iso.find_record(f, name)
            if not rec:
                continue
            b = bytearray(iso.read_bytes(f, rec["lba"], rec["size"]))
            try:
                nb, delta, info = grow_bbg(b)
            except Exception as e:
                print(f"  {name}: SKIP ({e})")
                skipped += 1
                continue
            if delta == 0 or info.get("skip"):
                skipped += 1
                continue
            # sanity: grown item must stay under the proven LWRAM ceiling (0x240000-0x239000=0x7000)
            _, _, _, new_item_len, _ = _chain(bytearray(nb))
            if new_item_len > 0x7000:
                raise ValueError(f"{name}: grown item_len 0x{new_item_len:x} exceeds LWRAM ceiling 0x7000")
            # append the grown BBG at track end
            f.seek(0, 2)
            new_lba = f.tell() // RL.RAW_SECTOR
            n_sectors = (len(nb) + RL.USER_DATA - 1) // RL.USER_DATA
            for i in range(n_sectors):
                chunk = nb[i * RL.USER_DATA:(i + 1) * RL.USER_DATA]
                f.write(RL.make_raw_sector(new_lba + i, chunk))
            # repoint this BBG's dir record (extent LBA @+2, data length @+10)
            RL._patch_u32_both(f, rec["rec_raw"] + 2, new_lba)
            RL._patch_u32_both(f, rec["rec_raw"] + 10, len(nb))
            appended_sectors += n_sectors
            done += 1
        # bump PVD volume space size once to cover all appended sectors
        f.seek(0, 2)
        total = f.tell() // RL.RAW_SECTOR
        RL._patch_u32_both(f, iso.pvd_volume_space_raw(), total)
    print(f"pO6 item-desc fold: grew+relocated {done} BBG(s), skipped {skipped}; "
          f"+{appended_sectors} sectors; volume now {total} sectors")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "plan":
        cmd_plan()
    elif cmd == "emit-grown-bbg":
        cmd_emit_bbg(argv[2], argv[3])
    elif cmd == "emit-grown-item":
        cmd_emit_item(argv[2], argv[3])
    elif cmd == "fold":
        cmd_fold(argv[2], force=("--force" in argv))
    else:
        print(f"unknown command {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
