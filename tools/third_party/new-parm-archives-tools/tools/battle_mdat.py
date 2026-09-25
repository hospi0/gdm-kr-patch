#!/usr/bin/env python3
"""battle_mdat.py — translate in-battle ENEMY NAMES stored in /BATLE/M_DAT.BIN.

LANE Q2 FINDING (see docs/lanes/laneQ2-battle-hud.md):
  The enemy name shown in the "<name> appeared" banner and in the target-selection banner is
  rendered LIVE from a per-monster record in M_DAT.BIN (26 MB container; the record block is
  copied verbatim into LWRAM at battle start). Each record stores the name in the standard
  Grandia 16x16 TBL encoding (`dicdt`), NUL-terminated with trailing NUL padding.
  The BANNER renderer honours control 0x03 (switch to 8x16 half-width ASCII) — PROVEN in a
  fresh battle: ドロンゾンビ -> "\x03Doron Zombie" rendered clean English in the appear banner.

  Some records ALSO carry a half-width-katakana copy of the name (the sec0/native encoding)
  which drives the bottom-left status PANEL. Where that copy sits IMMEDIATELY before the TBL
  name (verified layout for ドロンゾンビ), we patch it too, in place, with plain ASCII (the
  panel font renders ASCII directly, like the sec0 party names — no 0x03). It is not reliably
  locatable elsewhere (no leading NUL anchor), so panel names for other enemies may stay JP.

EDIT MODEL (size-preserving, in place — no relayout of the 26 MB file):
  TBL name: write 0x03 + ASCII + NUL, consuming only the original name bytes + their trailing
  NUL padding (never touches non-NUL data). Skipped if the padding can't fit the English.
  Adjacent hwkata copy: overwrite exactly its byte length with ASCII (space-padded), if the
  bytes there decode to the matching name.

Translation source = menus/battle_text.py MON (terms.json-consistent) + dictionary/exceptions
  DM-originals. Idempotent (skips already-0x03 TBL slots). md5-agnostic disc fold.

Usage:
    python3 tools/battle_mdat.py plan                 # dry-run: list every slot it would patch
    python3 tools/battle_mdat.py fold TRACK1.bin      # in-place patch M_DAT.BIN on a disc track
"""
from __future__ import annotations
import sys, unicodedata, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "menus"))
import iso        # noqa: E402
import dicdt      # noqa: E402
import battle_text  # noqa: E402

REV = dicdt.REV

# --- name table: G1-canon enemy names (localization truth) + DM-only fallbacks ----------------
# LANE BAT (rc_26): the enemy roster is shared with the original Grandia. Lane G1 aligned all 175
# JP<->EN enemy names from the G1 discs (docs/menus/g1-terms-aligned.json). Those localization names
# supersede menus/battle_text.py's MON dict, which held AI transliterations (101/175 conflicted, e.g.
# ヒバゴン Hibagon->Yeti, ドクレンジャー Venom Ranger->Gaia Drago). G1 canon wins; MON + exceptions
# only fill DM-only enemies G1 doesn't have.
def _load_names():
    """M_DAT text-slot translations: enemy NAMES (banner + panel) AND enemy ATTACK/action names.
    Both live in per-monster M_DAT records as a tbl slot (banner / ACTION field, honours 0x03) with
    an adjacent hwkata copy (status panel, plain ASCII) — the identical mechanism plan_patches uses.
    LANE BAT2 (rc_27): added the attack-name layer. The enemy record stores its name at record+0 and
    its action name at record+0x34 in the SAME layout; both are translated here off one map."""
    names = {}
    g1 = json.loads((ROOT / "docs/menus/g1-terms-aligned.json").read_text(encoding="utf-8"))
    for t in g1.get("terms", []):
        if t.get("category") == "enemy" and t.get("jp") and t.get("en"):
            names[t["jp"]] = t["en"]           # G1 localization canon (authoritative)
    # LANE BAT2: enemy ATTACK / action names, ripped from the G1 EN M_DAT at the JP-string offset
    # (docs/lanes/laneBAT2-battle.md). Same tbl+hwkata record layout as names → same fold.
    for t in g1.get("terms", []):
        if t.get("category") == "attack" and t.get("jp") and t.get("en"):
            names.setdefault(t["jp"], t["en"])
    for jp, en in battle_text.MON.items():
        names.setdefault(jp, en)               # DM-only enemies not in G1
    exc = json.loads((ROOT / "dictionary/exceptions.json").read_text(encoding="utf-8"))
    for e in exc.get("exceptions", []):
        jp, en = e.get("jp"), e.get("en")
        # DM-original battle enemies (heuristic: reason mentions enemy/battle); don't override G1
        if jp and en and "enem" in (e.get("reason", "").lower()):
            names.setdefault(jp, en)
    return names


def tbl_enc(s):
    out = bytearray()
    for ch in s:
        if ch not in REV:
            return None
        out += REV[ch]
    return bytes(out)


# half-width katakana encoder (native sec0/panel encoding: 0x90 = ー long vowel)
_KATA = "｡｢｣､･ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
_FW2HW = {unicodedata.normalize("NFKC", ch): bytes([0xA1 + i]) for i, ch in enumerate(_KATA)}


def hw_enc(s):
    out = bytearray()
    for ch in s:
        if ch == "ー":
            out += b"\x90"; continue
        d = unicodedata.normalize("NFD", ch)
        base = d[0]
        if base not in _FW2HW:
            return None
        out += _FW2HW[base]
        for m in d[1:]:
            if m == "゙":
                out += b"\xde"
            elif m == "゚":
                out += b"\xdf"
            else:
                return None
    return bytes(out)


MIN_TBL_LEN = 4   # skip 1-2 char names (目/手/花…) — too short to match safely


def plan_patches(b: bytes):
    """Return list of (offset, old_bytes, new_bytes, kind, jp, en). Size-preserving."""
    names = _load_names()
    n = len(b)
    patches = []
    for jp, en in names.items():
        t = tbl_enc(jp)
        if t is None or len(t) < MIN_TBL_LEN:
            continue
        L = len(t)
        ascii_en = en.encode("ascii", "replace")
        idx = 0
        while True:
            i = b.find(t, idx)
            if i < 0:
                break
            idx = i + 1
            # TBL name slot: NUL-bounded, enough trailing NUL padding for 0x03+ascii+NUL
            if not (i > 0 and b[i - 1] == 0 and i + L < n and b[i + L] == 0):
                continue
            k = i + L
            while k < n and b[k] == 0:
                k += 1
            avail = (k - i)                 # name bytes + trailing NUL run
            need = 1 + len(ascii_en) + 1
            if need > avail:
                continue
            # idempotent: already English?
            if b[i] == 0x03:
                continue
            new = b"\x03" + ascii_en + b"\x00" * (avail - need + 1)
            assert len(new) == avail
            patches.append((i, bytes(b[i:i + avail]), new, "tbl", jp, en))
            # adjacent hwkata copy (drives the status PANEL): sits at i-1-len(h), NUL at i-1
            h = hw_enc(jp)
            if h and i - 1 - len(h) >= 0 and b[i - 1 - len(h): i - 1] == h:
                ho = i - 1 - len(h)
                hen = ascii_en[:len(h)]
                new_h = hen + b" " * (len(h) - len(hen))
                if new_h != h:
                    patches.append((ho, bytes(h), new_h, "hwkata", jp, en))
    patches.sort()
    return patches


def _read_mdat(track):
    with open(track, "rb") as f:
        rec = iso.find_record(f, "M_DAT.BIN")
        b = iso.read_bytes(f, rec["lba"], rec["size"])
    return rec, b


def cmd_plan(track=None):
    van = track or str(ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin")
    _, b = _read_mdat(van)
    patches = plan_patches(b)
    tbl = sum(1 for p in patches if p[3] == "tbl")
    hw = sum(1 for p in patches if p[3] == "hwkata")
    print(f"M_DAT enemy-name plan: {tbl} banner(tbl) slots, {hw} panel(hwkata) slots")
    for off, old, new, kind, jp, en in patches:
        print(f"  0x{off:07x} [{kind:6s}] {jp!r} -> {en!r}")


def cmd_fold(track):
    rec, b = _read_mdat(track)
    patches = plan_patches(b)
    if not patches:
        print("battle_mdat fold: 0 slots (already English/unchanged)")
        return
    lba, U, RAW, SYNC = rec["lba"], iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    # apply into an in-memory copy, then write only the touched sectors
    b = bytearray(b)
    touched = set()
    for off, old, new, kind, jp, en in patches:
        assert b[off:off + len(new)] == old, f"anchor moved at 0x{off:x}"
        b[off:off + len(new)] = new
        for s in range(off // U, (off + len(new) - 1) // U + 1):
            touched.add(s)
    with open(track, "r+b") as f:
        for s in sorted(touched):
            chunk = bytes(b[s * U:(s + 1) * U])
            if len(chunk) < U:
                chunk = chunk + b"\x00" * (U - len(chunk))
            f.seek((lba + s) * RAW + SYNC)
            f.write(chunk)
    tbl = sum(1 for p in patches if p[3] == "tbl")
    hw = sum(1 for p in patches if p[3] == "hwkata")
    print(f"battle_mdat fold: patched {tbl} banner + {hw} panel enemy-name slots "
          f"({len(touched)} sectors)")


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    if argv[1] == "plan":
        cmd_plan(argv[2] if len(argv) > 2 else None)
    elif argv[1] == "fold":
        cmd_fold(argv[2])
    else:
        print(f"unknown command {argv[1]}"); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
