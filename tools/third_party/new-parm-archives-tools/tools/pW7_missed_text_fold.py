#!/usr/bin/env python3
"""Lane W7 fold: translate MDT text runs the *_en.py pass missed (pre-portrait boxes).

The Step-2 translation pipeline keyed dialogue off portrait-started segments, so a
handful of PORTRAIT-LESS opening boxes / item-get popups / door-sign boxes shipped
untranslated (found by the rc_46 full-disc JP sweep, docs/lanes/laneJP-sweep.md):

  2000/5044  townsman greeting (3 lines)         EB00/5000  old soldier barks (3 lines)
  D804/0     Got 'Game Coin 7'!                  EB04/0     Got a Pink Card!
  EB04|0C|10|14 /6000  'Door Locked' / Insert cards....  (mirrors shipped EB08 wording)

Mechanism: equal-length in-place replacement of the exact vanilla tbl-encoded JP byte
string inside the named MDT's extent on the track — 0x03 + ASCII + 0x04 + 0x20 padding,
the same byte shape the pipeline's _eqlen path emits (verified against EB08's shipped
'Door Locked' bytes). Never changes any file's length. Idempotent: JP bytes found ->
patch; English already present -> skip; neither -> ERROR (never fake a pass).

Usage: pW7_missed_text_fold.py <Track1.bin> [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import iso  # noqa: E402

# (mdt, label, jp_hex, english)  — len(0x03+en+0x04) <= len(jp_hex)/2, padded with 0x20
PATCHES = [
    ("2000.MDT", "5044 townsman L1 なんだ ジャスティン",
     "6e956420add8aebb98e6", "Justin!?"),
    ("2000.MDT", "5044 townsman L2 また博物館に遊びにきたのか？",
     "826320145b108810526f2014c0776f5163724fec", "Playing again, eh?"),
    ("2000.MDT", "5044 townsman L3 あまり館長さんにメイワクかけんなよ",
     "46828e201052104859956f20d699e4a44f55956e8c", "Easy on the Curator"),
    ("EB00.MDT", "5000 soldier L1 この奥が試験場になっておる！",
     "5772129c5020136e114610566f6e676a4e8fed", "Test range ahead!"),
    ("EB00.MDT", "5000 soldier L2 入隊希望者は覚悟して進むがよい",
     "102313fd12d1149f112073201012132b5b6a13bf84508c48", "Recruits, be prepared!"),
    ("EB00.MDT", "5000 soldier L3 りっぱな兵隊になるんじゃぞ！！",
     "8e67756e2010ca13fd6f6e8f955c8762f6", "Make us proud!!"),
    ("D804.MDT", "0 item-get ゲームのコイン７",
     "20123ba7efd572a899e628123c9410206f10239063ed", "Got 'Game Coin 7'!"),
    ("EB04.MDT", "0 item-get ピンクカード",
     "2020123bc9e6a4a0efbe123c9410206f10239063ed", "Got a Pink Card!"),
    ("EB04.MDT", "6000 door sign ドアロック中",
     "20262020202020123bbe97e2b8a41226123c", "'Door Locked'"),
    ("EB04.MDT", "6000 door sign カードを入れて下さい",
     "202020a0efbe94201023906a102c5948f1f1f1", "Insert cards...."),
    ("EB0C.MDT", "6000 door sign ドアロック中",
     "20262020202020123bbe97e2b8a41226123c", "'Door Locked'"),
    ("EB0C.MDT", "6000 door sign カードを入れて下さい",
     "202020a0efbe94201023906a102c5948f1f1f1", "Insert cards...."),
    ("EB10.MDT", "6000 door sign ドアロック中",
     "20262020202020123bbe97e2b8a41226123c", "'Door Locked'"),
    ("EB10.MDT", "6000 door sign カードを入れて下さい",
     "202020a0efbe94201023906a102c5948f1f1f1", "Insert cards...."),
    ("EB14.MDT", "6000 door sign ドアロック中",
     "20262020202020123bbe97e2b8a41226123c", "'Door Locked'"),
    ("EB14.MDT", "6000 door sign カードを入れて下さい",
     "202020a0efbe94201023906a102c5948f1f1f1", "Insert cards...."),
    ("E814.MDT", "500d NPC いろんなゲームができるんだって",
     "4891956e20a7efd550206b518f9564676a", "Lots of games!"),
    ("EB00.MDT", "5000 soldier L4 なんというヘタクソな運転じゃ！",
     "6e956c484a20cdb4a4b26e128e10725c87ed", "Awful driving!!"),
    ("EB00.MDT", "5000 soldier L5 見ちゃあおれんわ！！",
     "1045658746204e909593f6", "Yeesh!!"),
    ("EB00.MDT", "5000 soldier L6 ワシが入隊した頃は",
     "e4ac5020102313fd5b63134073", "In my day,"),
    ("EB00.MDT", "5000 soldier L7 乗りたくても戦車など無かったが‥‥",
     "12068e63536a862010b213806e6d10344f676350f1f1", "we had no tanks...."),
    ("EB00.MDT", "5000 soldier L8 ボウズは立派な兵隊になるんじゃぞ！",
     "d19baf732010d114536e10ca13fd6f6e8f955c8762ed", "Make a fine soldier!"),
]

RAW_SECTOR, SYNC, USER = 2352, 16, 2048


def file_extent(f, name):
    for path, lba, size in iso.walk(f):
        if path.rsplit("/", 1)[-1] == name:
            return lba, size
    raise SystemExit(f"{name}: not on disc")


def read_span(f, lba, size):
    out = bytearray()
    nsec = (size + USER - 1) // USER
    for i in range(nsec):
        f.seek((lba + i) * RAW_SECTOR + SYNC)
        out += f.read(USER)
    return bytes(out[:size])


def write_span(f, lba, data):
    nsec = (len(data) + USER - 1) // USER
    for i in range(nsec):
        chunk = data[i * USER:(i + 1) * USER]
        f.seek((lba + i) * RAW_SECTOR + SYNC)
        f.write(chunk)


def build_en(en: str, jp_len: int) -> bytes:
    body = b"\x03" + en.encode("ascii") + b"\x04"
    assert len(body) <= jp_len, f"{en!r} too long for {jp_len}B slot"
    return body + b"\x20" * (jp_len - len(body))


def main() -> int:
    track = Path(sys.argv[1])
    check = "--check" in sys.argv
    patched = skipped = 0
    with open(track, "r+b" if not check else "rb") as f:
        extents = {}
        for mdt, label, jp_hex, en in PATCHES:
            if mdt not in extents:
                extents[mdt] = file_extent(f, mdt)
            lba, size = extents[mdt]
            data = bytearray(read_span(f, lba, size))
            jp = bytes.fromhex(jp_hex)
            enb = build_en(en, len(jp))
            n = data.count(jp)
            if n == 0:
                if data.count(enb.rstrip(b"\x20")[:len(enb) - 2]) or enb in data or bytes(enb).rstrip(b" ") in data:
                    print(f"  SKIP (already English): {mdt} {label}")
                    skipped += 1
                    continue
                raise SystemExit(f"ERROR: {mdt} {label}: JP bytes not found and English absent")
            pos = 0
            while True:
                i = data.find(jp, pos)
                if i < 0:
                    break
                data[i:i + len(jp)] = enb
                pos = i + len(enb)
            if not check:
                write_span(f, lba, bytes(data))
            print(f"  PATCH x{n}: {mdt} {label} -> {en!r}")
            patched += n
    print(f"{'CHECK' if check else 'FOLD'} done: {patched} patched, {skipped} already-English")
    return 0


if __name__ == "__main__":
    sys.exit(main())
