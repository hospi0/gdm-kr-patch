#!/usr/bin/env python3
"""battle_sec0.py — translate the VISIBLE battle HUD text embedded in every /BATLE/*.BBG.

LANE Q2 FINDING (supersedes Lane Q's sec2 assumption — see docs/lanes/laneQ2-battle-hud.md):
  The live battle HUD (party name plates ジャスティン/スー/フィーナ, the bottom command line
  コマンド にゅうりょく, the command verbs 攻撃/防御/道具/…, and the クリティカル/コンボ
  popups) all rasterise from **sec0** of the BBG's embedded 9-section text file — NOT sec2.
  Lane Q translated sec2 (a 16x16-tbl duplicate) and correctly observed the HUD did not change.
  sec0 uses a DIFFERENT, game-native encoding: half-width katakana in the standard JIS X0201
  range 0xA1-0xDF, plus a custom HIRAGANA block (0x80-0x9F / 0xE0-0xFF), 0x90 = ー (long vowel),
  0xDE/0xDF = ゛/゜ combining dakuten/handakuten. Crucially the sec0 font ALSO contains plain
  ASCII 0x20-0x7E (proven: the "?????????" placeholder entry is stored as nine 0x3F '?' bytes),
  so English renders by writing ASCII bytes directly — no 0x03 font-switch needed.

CONTAINER (identical to battle_bbg.py; sec0 is byte-identical across all 34 gameplay BBGs, 140 B,
with a 5.8-8.3 KB runtime-placeholder sec7 donor):
  root archive -> child[last] (text sub-resource) -> item[1] = 9x uint32 BE section header + data.
  Header entries are offsets RELATIVE TO THE ITEM. sec0 = [hdr[0]=0x24, hdr[1]).

EDIT MODEL (size-preserving, no disc relayout — same as battle_bbg.py):
  English sec0 is byte-longer than the dense JP, so we GROW sec0 and SHRINK the trailing
  runtime-placeholder sec7 by the same delta, keeping item and file size identical. Only the
  9-uint item header + sec0 + sec7 bytes change.

Usage:
    python3 tools/battle_sec0.py plan                  # show sec0 decode + translation + delta
    python3 tools/battle_sec0.py patch-bytes IN OUT [--test]   # translate one raw .BBG file
    python3 tools/battle_sec0.py fold TRACK1.bin [--test]      # md5-agnostic in-place disc patch
"""
from __future__ import annotations
import struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
import iso  # noqa: E402

# ---- sec0 custom encoding: decoder (for verification / dump) --------------------------------
_KATA = "｡｢｣､･ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝﾞﾟ"
_HIRA = {0x8d: 'ゅ', 0x8e: 'ょ', 0x8f: 'っ', 0x92: 'い', 0x93: 'う', 0x96: 'か', 0x97: 'き',
         0x98: 'く', 0x99: 'け', 0x9a: 'こ', 0x9b: 'さ', 0x9e: 'せ', 0x9f: 'そ', 0xe0: 'た',
         0xe2: 'つ', 0xe4: 'と', 0xe6: 'に', 0xe9: 'の', 0xeb: 'ひ', 0xec: 'ふ', 0xee: 'ほ',
         0xef: 'ま', 0xf8: 'り', 0xfc: 'わ', 0xfa: '?', }


def decode(b: bytes) -> str:
    out = ""
    i = 0
    while i < len(b):
        x = b[i]
        nxt = b[i + 1] if i + 1 < len(b) else None
        if 0xa1 <= x <= 0xdf:
            ch = _KATA[x - 0xa1]
        elif x == 0x90:
            ch = 'ー'
        elif x in _HIRA:
            ch = _HIRA[x]
        elif 0x20 <= x < 0x7f:
            ch = chr(x)
        else:
            ch = f'[{x:02x}]'
        if nxt == 0xde:
            out += ch + '゙'; i += 2; continue
        if nxt == 0xdf:
            out += ch + '゚'; i += 2; continue
        out += ch; i += 1
    return out


# ---- translation: keyed on the verbatim JP sec0 bytes (robust + idempotent) ------------------
# English values are dictionary-consistent (terms.json / menus/battle_text.py CMD).
SEC0_TRANS = {
    "cadf90c3a890": "Party",
    "bcdeacbdc3a8dd": "Justin",
    "cca890c5": "Feena",
    "bd90": "Sue",
    "b6dec4deb2dd": "Gadwin",
    "d7afccdf": "Rapp",
    "d0d9c0de": "Milda",
    "b7dec4de": "Guido",
    "d8b490c3": "Liete",
    "e09297": "Wait",              # 待機
    "baddcede": "Combo",           # コンボ
    "b8d8c3a8b6d9": "Critical",    # クリティカル
    "eede9397de8e": "Defend",      # 防御 (ぼうぎょ)
    "efee93": "Magic",             # 魔法 (まほう)
    "eb8f9be2fc9bde": "Special",   # 必殺技 (ひっさつわざ)
    "9692eb": "Evade",             # 回避 (かいひ)
    "e4de9398de": "Item",          # 道具 (どうぐ)
    "9a9399de97": "Attack",        # 攻撃 (こうげき)
    "9efde493ece993": "K.O.",      # 戦闘不能 (せんとうふのう)
    "bacfddc4dee68d93f88e98": "Command input",  # コマンド にゅうりょく
    # entry 20 = nine 0x3F literal '?' placeholder — keep verbatim (already ASCII).
    # entries 21/22 = escape-message fragments (かく? / とうそう), keep verbatim for now.
}


def _split(b: bytes):
    """Split packed NUL-separated block -> list of (entry_bytes)."""
    out = []
    i = 0
    while i < len(b):
        e = b.find(b"\x00", i)
        if e < 0:
            out.append(b[i:]); break
        out.append(b[i:e]); i = e + 1
    return out


def translate_sec0(sec0: bytes):
    """JP sec0 -> EN sec0. Preserves NUL structure exactly (idempotent).
    Returns (new_bytes, notes)."""
    out = bytearray()
    notes = []
    i = 0
    n = len(sec0)
    while i < n:
        if sec0[i] == 0:
            out += b"\x00"; i += 1; continue
        j = sec0.index(0, i) if 0 in sec0[i:] else n
        s = sec0[i:j]
        h = s.hex()
        if h in SEC0_TRANS:
            out += SEC0_TRANS[h].encode("ascii")
            notes.append(("EN", decode(s), SEC0_TRANS[h]))
        else:
            out += s
            notes.append(("KEEP", decode(s)))
        i = j
    return bytes(out), notes


# ---- generic recursive archive parse (from battle_bbg.py) -----------------------------------
LEADER_SIG = bytes.fromhex("0397c298a582d004")  # sec2 leader slot — survives translation, unique


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
    _, _, item_off, item_len = chain[-2]
    return item_off, item_len


def patch_bbg(b: bytes, test: bool = False) -> bytes:
    b = bytearray(b)
    item_off, item_len = _locate(b)
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    if hdr[0] != 0x24:
        raise ValueError(f"unexpected item header[0]={hdr[0]:#x}")
    sec0 = bytes(b[item_off + hdr[0]: item_off + hdr[1]])
    if test:
        new_sec0, _ = _translate_test(sec0)
    else:
        new_sec0, _ = translate_sec0(sec0)
    delta = len(new_sec0) - len(sec0)
    if delta == 0 and new_sec0 == sec0:
        return bytes(b)  # nothing changed (already English)
    sec7 = bytes(b[item_off + hdr[7]: item_off + hdr[8]])
    if delta > len(sec7) - 4:
        raise ValueError(f"delta {delta} too large for sec7 donor ({len(sec7)} B)")
    new_sec7 = sec7[: len(sec7) - delta] if delta > 0 else sec7 + b"\x00" * (-delta)
    # header: sec1..sec7 offsets += delta, sec8 unchanged
    new_hdr = [hdr[0]] + [hdr[i] + delta for i in range(1, 8)] + [hdr[8]]
    parts = bytearray()
    for v in new_hdr:
        parts += struct.pack(">I", v)
    parts = parts[: hdr[0]]
    body = bytearray(b[item_off + hdr[0]: item_off + item_len])
    H = hdr[0]

    def splice(dst, lo, hi, new):
        return dst[:lo] + new + dst[hi:]
    # sec7 first (higher offset), then sec0
    body = splice(body, hdr[7] - H, hdr[8] - H, new_sec7)
    body = splice(body, hdr[0] - H, hdr[1] - H, new_sec0)
    new_item = bytes(parts) + bytes(body)
    if len(new_item) != item_len:
        raise ValueError(f"item size changed {item_len}->{len(new_item)} (delta {delta})")
    b[item_off: item_off + item_len] = new_item
    return bytes(b)


# minimal font-routing test: only translate Justin + the command line, rest verbatim
def _translate_test(sec0: bytes):
    keep = {"bcdeacbdc3a8dd": "Justin", "bacfddc4dee68d93f88e98": "Command"}
    out = bytearray(); notes = []
    i = 0; n = len(sec0)
    while i < n:
        if sec0[i] == 0:
            out += b"\x00"; i += 1; continue
        j = sec0.index(0, i) if 0 in sec0[i:] else n
        s = sec0[i:j]; h = s.hex()
        if h in keep:
            out += keep[h].encode("ascii"); notes.append(("EN", decode(s), keep[h]))
        else:
            out += s; notes.append(("KEEP", decode(s)))
        i = j
    return bytes(out), notes


BBG_NAMES = [f"B{n:03d}.BBG" for n in range(1, 33)] + ["B255.BBG", "BTEST.BBG"]


def cmd_plan(test=False):
    van = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
    with open(van, "rb") as f:
        rec = iso.find_record(f, "B001.BBG")
        b = iso.read_bytes(f, rec["lba"], rec["size"])
    item_off, item_len = _locate(bytearray(b))
    hdr = [struct.unpack_from(">I", b, item_off + i * 4)[0] for i in range(9)]
    sec0 = b[item_off + hdr[0]: item_off + hdr[1]]
    new_sec0, notes = (_translate_test if test else translate_sec0)(bytes(sec0))
    print(f"sec0 {len(sec0)} -> {len(new_sec0)} B (delta {len(new_sec0)-len(sec0):+d}); "
          f"sec7 donor {hdr[8]-hdr[7]} B")
    for nt in notes:
        if nt[0] == "EN":
            print(f"   {nt[1]!r} -> {nt[2]!r}")
        else:
            print(f"   KEEP {nt[1]!r}")


def cmd_fold(track, test=False):
    U, RAW, SYNC = iso.USER_DATA, iso.RAW_SECTOR, iso.SYNC_HEADER
    done = skipped = 0
    for name in BBG_NAMES:
        with open(track, "rb") as f:
            rec = iso.find_record(f, name)
            if not rec:
                continue
            data = iso.read_bytes(f, rec["lba"], rec["size"])
        new = patch_bbg(data, test=test)
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
    print(f"battle_sec0 fold: patched {done} BBG(s), skipped {skipped}")


def main(argv):
    test = "--test" in argv
    argv = [a for a in argv if a != "--test"]
    if len(argv) < 2:
        print(__doc__); return 2
    cmd = argv[1]
    if cmd == "plan":
        cmd_plan(test)
    elif cmd == "patch-bytes":
        Path(argv[3]).write_bytes(patch_bbg(Path(argv[2]).read_bytes(), test=test))
        print(f"patched {argv[2]} -> {argv[3]}")
    elif cmd == "fold":
        cmd_fold(argv[2], test)
    else:
        print(f"unknown command {cmd}"); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
