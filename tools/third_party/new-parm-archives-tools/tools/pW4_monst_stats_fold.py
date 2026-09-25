#!/usr/bin/env python3
"""pW4_monst_stats_fold.py — Lane W4 (O5): monster-book detail-page STAT-PANEL labels -> English.

WHAT THIS PATCHES
  The stat panel (ステータス header + レベル/たいきゅうりょく/こうげきりょく/ぼうぎょりょく/
  すばやさ/そうりょく/けいけんち rows) on the Monster Guide detail page.
  English (dictionary-guided, docs/menus/monster-stats-labels-en.json):
  Status / Level / Endurance / Attack / Defense / Agility / Move / Exp.

THE CRACK (supersedes the laneM/M2/O5 "VDP2 rotation bitmap + book-open decompressor" walls)
  * The page pixels are NOT produced by a decompressor: 0x060044F0 is the resident CD file
    STREAMER (3-sector reads, dst advances 0x1800/call). At book-open it streams
    /FIELD/DICDT.DAT linearly to LWRAM 0x240000.
  * The page-interior 8bpp tile store (parchment + labels, 0xF4C0 bytes) therefore sits
    VERBATIM in DICDT.DAT at file offset 0xCFA0 (== LWRAM 0x24CFA0, byte-identical, verified
    0 diffs). Per-monster the engine blits it to VDP2 and overdraws numbers/sprite/header —
    all OUTSIDE the label cells, so a labels-only edit is isolated.
  * The screen->blob byte map was decoded EMPIRICALLY (16 bit-plane LWRAM inject runs ->
    per-pixel 16-bit offset decode; 0.00% reconstruction mismatch). Map committed as
    patches/viewer/pW4_screenmap.npz; authoring rig = work/pW4/author.py (see
    docs/lanes/laneW4-stats-panel.md). Label ink bytes 187 (dark) / 186 (emboss) are used by
    the labels ONLY (0 occurrences elsewhere in the blob) -> erase+restamp is surgical.

WHAT THE FOLD DOES (idempotent, byte-gated, size-preserving)
  Locates /FIELD/DICDT.DAT in the track, reads the 0xF4C0-byte window at file offset 0xCFA0:
    md5 == VANILLA -> applies the 1748-byte edit list patches/viewer/pW4_stats_labels.bin
    md5 == ENGLISH -> skip (idempotent)
    anything else  -> hard error (never guess on unknown bytes)
  Only touched sectors are rewritten; file size unchanged; the rest of DICDT.DAT (encyclopedia
  text, patched by the step-3 DICDT fold) is untouched -> composes in any order.

USAGE
  pW4_monst_stats_fold.py fold   TRACK.bin          # in place (build_rc step)
  pW4_monst_stats_fold.py verify TRACK.bin          # report window state
"""
import os, sys, hashlib, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import iso  # noqa: E402

TARGET = "DICDT.DAT"
WIN_OFF = 0xCFA0           # blob offset inside DICDT.DAT (== LWRAM 0x24CFA0 - 0x240000)
WIN_LEN = 0xF4C0           # tile-store length (the per-monster VDP2 blit length)
MD5_VANILLA = "89f957de6f7bd2bbe93f1ab4b717e9bb"
MD5_ENGLISH = "06c205b651c5d1952547f10ea5584f74"
PATCH = os.path.join(HERE, "..", "patches", "viewer", "pW4_stats_labels.bin")


def _load_edits():
    d = open(PATCH, "rb").read()
    assert d[:4] == b"PW4L", "bad patch magic"
    (n,) = struct.unpack_from(">I", d, 4)
    edits = []
    for i in range(n):
        o, v = struct.unpack_from(">HB", d, 8 + 3 * i)
        assert o < WIN_LEN
        edits.append((o, v))
    return edits


def _window(f):
    rec = iso.find_record(f, TARGET)
    if not rec:
        raise SystemExit(f"{TARGET}: not found in track")
    lba, size = rec["lba"], rec["size"]
    if size < WIN_OFF + WIN_LEN:
        raise SystemExit(f"{TARGET}: too small ({size})")
    data = iso.read_bytes(f, lba, size)
    return rec, data


def cmd_verify(track):
    with open(track, "rb") as f:
        rec, data = _window(f)
        md5 = hashlib.md5(data[WIN_OFF:WIN_OFF + WIN_LEN]).hexdigest()
    state = {MD5_VANILLA: "VANILLA-JP", MD5_ENGLISH: "ENGLISH"}.get(md5, "UNKNOWN")
    print(f"{TARGET} @LBA {rec['lba']} window 0x{WIN_OFF:X}+0x{WIN_LEN:X}: md5 {md5} -> {state}")
    return 0 if state != "UNKNOWN" else 1


def cmd_fold(track):
    edits = _load_edits()
    with open(track, "r+b") as f:
        rec, data = _window(f)
        lba, size = rec["lba"], rec["size"]
        win = data[WIN_OFF:WIN_OFF + WIN_LEN]
        md5 = hashlib.md5(win).hexdigest()
        if md5 == MD5_ENGLISH:
            print("pW4 monst stats: already English — idempotent skip.")
            return 0
        if md5 != MD5_VANILLA:
            raise SystemExit(f"pW4 monst stats: UNEXPECTED window md5 {md5} — refusing to patch.")
        new = bytearray(data)
        for o, v in edits:
            new[WIN_OFF + o] = v
        got = hashlib.md5(bytes(new[WIN_OFF:WIN_OFF + WIN_LEN])).hexdigest()
        if got != MD5_ENGLISH:
            raise SystemExit(f"pW4 monst stats: post-edit md5 {got} != expected — aborting (file untouched).")
        # rewrite only changed sectors
        n_sec = 0
        for s in range((size + iso.USER_DATA - 1) // iso.USER_DATA):
            a, b = s * iso.USER_DATA, min((s + 1) * iso.USER_DATA, size)
            if data[a:b] != bytes(new[a:b]):
                f.seek(iso.raw_offset(lba + s))
                f.write(bytes(new[a:b]))
                n_sec += 1
        f.seek(0)
        check = iso.read_bytes(f, lba, size)
        if hashlib.md5(check[WIN_OFF:WIN_OFF + WIN_LEN]).hexdigest() != MD5_ENGLISH:
            raise SystemExit("pW4 monst stats: re-read verification FAILED")
        print(f"pW4 monst stats: {len(edits)} bytes -> English over {n_sec} sectors "
              f"(Status/Level/Endurance/Attack/Defense/Agility/Move/Exp).")
    return 0


def main(argv):
    if len(argv) != 3 or argv[1] not in ("fold", "verify"):
        print(__doc__)
        return 2
    return {"fold": cmd_fold, "verify": cmd_verify}[argv[1]](argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
