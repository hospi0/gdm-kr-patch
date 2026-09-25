#!/usr/bin/env python3
"""save_browser_en.py — translate the SAVE-DATA BROWSER stat/equip labels to English.

The DM save-data browser subsystem (Lane O7) is three FIELD overlays that share one
JIS X0201 half-width label table:

    /FIELD/SVLD.BIN   (loads to HWRAM 0x060b2000; the save-data viewer)   table @ 0xacf8
    /FIELD/SAVER.BIN  (the save/write overlay)                            table @ 0xf334
    /FIELD/CNFIG.BIN  (config/options overlay)                            table @ 0x94e0

RENDERER / FONT ROUTING (reverse-engineered + PROVEN in-harness, docs/lanes/laneO7-*.md):
the browser font is a single 8-bit JIS X0201 face — ASCII (0x20-0x7e) in the low range,
half-width katakana (0xa1-0xdf) in the high range — drawn straight from the byte stream.
It does NOT use the 0x03 8x16 switch. Proof: the vanilla browser already mixes ASCII
labels ("STATUS", "ITEM", "MP", "HP", "SP", "-GOOD-", "Not Initialized!") with katakana
stat labels, and both render (see the "Save System RAM / Not Initialized!" PNG). We further
injected our own authored ASCII ("atk def Weapon !") over a live browser string and it drew
cleanly. So translating a label == replacing its katakana bytes with ASCII, in place.

Each label is a fixed-stride, NUL-terminated, space-padded record. We replace the katakana
TEXT bytes (up to the 0x00 terminator) with English of the SAME byte length, so file size,
LBA, and sector count are all unchanged — no relocation, works on stale savestates' baked
file-index. Terms are aligned to the live status/equip screen (CMDMN.BIN, already shipped
English & validated in-game): atk/def/act/str/vit/agi and weapon/shield/armor/helmet/shoes.

Two labels have no confident canonical English and are FLAGGED for user review (see
UNCERTAIN below): そうりょく (souryoku) -> "pow", げんざい (genzai) -> "now".

Usage:
  save_browser_en.py verify TRACK.bin           # report JP vs EN state of the 3 files
  save_browser_en.py dump   TRACK.bin           # show the decoded label table
  save_browser_en.py patch  IN.bin OUT.bin      # copy IN->OUT, translate in place
  save_browser_en.py fold   TRACK.bin           # translate in place (RC build step; idempotent)

All commands are idempotent and byte-gated: file size must be unchanged, every mapped JP
record must be present exactly once before patching (or already English after), and after
patching the English form must be present and the JP form absent.
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import iso

# --- The translation table -------------------------------------------------
# jp_text_bytes (katakana, exactly as stored, up to but not incl. the 0x00) -> english
# english MUST be the same byte length as the katakana it replaces (space-padded to fit).
# Canonical source: CMDMN.BIN live status/equip label table (shipped English, in-game proven).
MAP = {
    # 6-byte stat labels
    "bab3b9deb720": b"atk   ",   # こうげき kougeki  -> atk   (CMDMN "atk")
    "cedeb3b7deae": b"def   ",   # ぼうぎょ bougyo   -> def   (CMDMN "def")
    "bab3c4deb320": b"act   ",   # こうどう koudou   -> act   (CMDMN "act"/ACT-ANIME)
    "b2c4deb32020": b"mov   ",   # いどう   idou     -> mov   (Grandia MOV = move speed)
    "c1b6d7202020": b"str   ",   # ちから   chikara  -> str   (CMDMN "str")
    "c0b2d8aeb820": b"vit   ",   # たいりょく tairyoku-> vit   (CMDMN "vit")
    "bdcaded4bb20": b"agi   ",   # すばやさ subayasa -> agi   (CMDMN "agi", quickness)
    "bfb3d8aeb820": b"pow   ",   # そうりょく souryoku-> pow   (UNCERTAIN: 総力/overall power)
    # 9-byte equipment labels (CMDMN forms)
    "ccdeb7202020202020": b"weapon   ",  # ぶき     buki
    "c0c320202020202020": b"shield   ",  # たて     tate
    "d6dbb2202020202020": b"armor    ",  # よろい   yoroi
    "b6ccdec42020202020": b"helmet   ",  # かぶと   kabuto
    "b8c220202020202020": b"shoes    ",  # くつ     kutsu
    "b1b8bebbd8b0202020": b"accessory",  # アクセサリー accessory (fits exactly, 9)
    # 6-byte currency / misc
    "badeb0d9c4de": b"Gold  ",   # ゴールド gold
    "b9deddbbdeb2": b"now   ",   # げんざい genzai   -> now   (UNCERTAIN, SAVER only)
}
UNCERTAIN = {"bfb3d8aeb820", "b9deddbbdeb2"}  # そうりょく, げんざい — flagged for user review

TARGETS = ["SVLD.BIN", "SAVER.BIN", "CNFIG.BIN"]


def _jdec(b: bytes) -> str:
    try:
        return bytes(b).decode("shift_jis")
    except Exception:
        return b.hex()


def _read_file(f, name):
    rec = iso.find_record(f, name)
    if not rec:
        raise SystemExit(f"{name}: not found on track")
    data = iso.read_bytes(f, rec["lba"], rec["size"])
    return rec, bytearray(data)


def _classify(data: bytes):
    """Return (jp_present, en_present) counts across the MAP for one file's bytes."""
    jp = {}
    en = {}
    for hexjp, enb in MAP.items():
        jpb = bytes.fromhex(hexjp)
        jp[hexjp] = data.count(jpb + b"\x00")
        en[hexjp] = data.count(enb + b"\x00")
    return jp, en


def cmd_verify(track):
    with open(track, "rb") as f:
        allclean = True
        for name in TARGETS:
            rec, data = _read_file(f, name)
            jp, en = _classify(data)
            njp = sum(v for v in jp.values())
            nen = sum(v for k, v in en.items() if jp[k] == 0)  # english where jp gone
            state = "ENGLISH" if njp == 0 and nen > 0 else ("JAPANESE" if njp > 0 else "n/a")
            print(f"{name:10s} LBA {rec['lba']:>7} size {rec['size']:>6}  "
                  f"jp_labels={njp:2d} en_labels={nen:2d}  -> {state}")
            if njp > 0:
                allclean = False
        return 0 if allclean else 1


def cmd_dump(track):
    with open(track, "rb") as f:
        for name in TARGETS:
            rec, data = _read_file(f, name)
            print(f"=== {name} @LBA {rec['lba']} ({rec['size']} B) ===")
            for hexjp, enb in MAP.items():
                jpb = bytes.fromhex(hexjp)
                loc = data.find(jpb + b"\x00")
                loc_en = data.find(enb + b"\x00")
                if loc >= 0:
                    flag = "  [UNCERTAIN-review]" if hexjp in UNCERTAIN else ""
                    print(f"  @{loc:#07x} JP [{_jdec(jpb):8s}] -> [{enb.decode()}]{flag}")
                elif loc_en >= 0:
                    print(f"  @{loc_en:#07x} already-EN [{enb.decode()}]")


def _patch_file_in_track(f, name):
    """Translate one file's labels in place in an open r+b track. Returns n_changed."""
    rec = iso.find_record(f, name)
    if not rec:
        raise SystemExit(f"{name}: not found")
    lba, size = rec["lba"], rec["size"]
    data = bytearray(iso.read_bytes(f, lba, size))
    orig = bytes(data)
    changed = 0
    for hexjp, enb in MAP.items():
        jpb = bytes.fromhex(hexjp)
        pat = jpb + b"\x00"
        n = data.count(pat)
        if n == 0:
            # either absent from this file, or already English -> idempotent skip
            continue
        if n != 1:
            raise SystemExit(f"{name}: {_jdec(jpb)} found {n}x (expected 1) — aborting")
        assert len(enb) == len(jpb)
        idx = data.find(pat)
        data[idx:idx + len(enb)] = enb
        changed += 1
    if changed == 0:
        return 0
    if len(data) != size:
        raise SystemExit(f"{name}: size drift {len(data)} != {size}")
    # write back only the sectors that changed (byte-exact everywhere else)
    for s in range((size + iso.USER_DATA - 1) // iso.USER_DATA):
        a = s * iso.USER_DATA
        b = min(a + iso.USER_DATA, size)
        if orig[a:b] != data[a:b]:
            f.seek(iso.raw_offset(lba + s))
            f.write(bytes(data[a:b]))
    # re-verify from disk
    f.seek(0)
    check = iso.read_bytes(f, lba, size)
    for hexjp, enb in MAP.items():
        jpb = bytes.fromhex(hexjp)
        if check.count(jpb + b"\x00"):
            raise SystemExit(f"{name}: JP {_jdec(jpb)} still present after patch")
    return changed


def cmd_patch(intrack, outtrack):
    if os.path.abspath(intrack) != os.path.abspath(outtrack):
        shutil.copyfile(intrack, outtrack)
    return _do_fold(outtrack)


def cmd_fold(track):
    return _do_fold(track)


def _do_fold(track):
    total = 0
    with open(track, "r+b") as f:
        for name in TARGETS:
            n = _patch_file_in_track(f, name)
            print(f"{name:10s}: {n} labels -> English"
                  + ("" if n else " (already English / n/a — idempotent skip)"))
            total += n
    print(f"save_browser_en: {total} label replacements applied.")
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "verify":
        return cmd_verify(argv[2])
    if cmd == "dump":
        return cmd_dump(argv[2])
    if cmd == "patch":
        return cmd_patch(argv[2], argv[3])
    if cmd == "fold":
        return cmd_fold(argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
