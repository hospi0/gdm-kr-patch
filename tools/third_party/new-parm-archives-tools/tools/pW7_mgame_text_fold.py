#!/usr/bin/env python3
"""Lane W7 fold: minigame INTERNALS text — MGSUE.BIN (game 2 cheer-battle dialogue,
Grandia-16x16-tbl encoded) + BARLG.BIN (game 7 tank-battle intro, JIS X0201 hwkata
C-strings).

Found by the rc_46 full-game JP image sweep (docs/lanes/laneJP-sweep.md):
  - Game 2 (Sue vs Gantz cheer battle) renders ~20 JP dialogue lines from a
    NUL/ctrl-delimited tbl string block at MGSUE.BIN ~0x34728-0x348ea. The renderer
    is the 16x16 tbl font, so English is authored as the tbl's full-width UPPERCASE
    Roman (DICDT convention), equal-length, 0x20-padded.
  - Game 7 (Garlyle tank battle) renders a hwkata intro from zero-padded slots at
    BARLG.BIN ~0xa740-0xa83c + a C-string at 0xa258. JIS X0201 renders raw ASCII
    (proven by the sibling strings "play Test!"/"RUN" and the O7 save-browser RE),
    so English is plain ASCII, NUL-padded inside each slot.

Each entry = (file, label, context-pattern hex, span_off, span_len, english).
The context pattern is matched in the file's extent on the track; only the
[span_off, span_off+span_len) bytes inside each match are rewritten, equal-length.
Idempotent: pattern found -> patch; English already present -> skip; neither -> ERROR.

Usage: pW7_mgame_text_fold.py <Track1.bin> [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import iso  # noqa: E402

# tbl full-width Roman (Grandia16x16.tbl): '0'-'9'=0x21-0x2A, A-Z=0x2B-0x44,
# space=0x20, '!'=0xED, '?'=0xEC, '~'(wave)=0xF0
def tbl_enc(s: str) -> bytes:
    out = bytearray()
    for ch in s:
        if ch == " ":
            out.append(0x20)
        elif "0" <= ch <= "9":
            out.append(0x21 + ord(ch) - 0x30)
        elif "A" <= ch <= "Z":
            out.append(0x2B + ord(ch) - 0x41)
        elif ch == "!":
            out.append(0xED)
        elif ch == "?":
            out.append(0xEC)
        elif ch == "~":
            out.append(0xF0)
        else:
            raise SystemExit(f"tbl_enc: unsupported char {ch!r} in {s!r}")
    return bytes(out)


def ascii_enc(s: str) -> bytes:
    return s.encode("ascii")


M = "MGSUE.BIN"
B = "BARLG.BIN"
# (file, label, pattern_hex, span_off, span_len, english, encoder, pad_byte)
ENTRIES = [
    # --- MGSUE game-2 cheer-battle dialogue (tbl, pad 0x20) ---
    (M, "がんばラーー！！",       "2014a8deefefeded01",                   1, 7,  "GO GO!!",           tbl_enc, 0x20),
    (M, "かかってこーーーーい！！", "014f4f676a57efefefef48eded07",         1, 12, "COME ON!!!!!",      tbl_enc, 0x20),
    (M, "うわ～～～",            "20124a93f0f0f001",                     1, 6,  "WHOA~~",            tbl_enc, 0x20),
    (M, "すっごいキハク‥‥‥",     "015d675848a2c4a4f1f1f107",             1, 10, "SUCH VIGOR",        tbl_enc, 0x20),
    (M, "よぉ～～～し！",         "201a8c4ef0f0f05bed01",                 1, 8,  "ALRIGHT!",          tbl_enc, 0x20),
    (M, "負けないから！！",       "011481556e484f8deded01",               1, 9,  "CANT LOSE",         tbl_enc, 0x20),
    (M, "ね！ プーイ！？",        "0171ed20ccef99f707",                   1, 7,  "PUFFY?!",           tbl_enc, 0x20),
    (M, "ぷぷっ！",              "20067b7b67ed07",                       2, 4,  "PUU!",              tbl_enc, 0x20),
    (M, "よっしゃあ！",           "20148c675b8746ed01",                   1, 7,  "YEAH!!!",           tbl_enc, 0x20),
    (M, "いっちょいったるか！！",   "014867658b4867638f4feded07",           1, 11, "HERE I GO!!",       tbl_enc, 0x20),
    (M, "やれだなあ",            "2014d9646e4601",                       1, 5,  "OH MY",             tbl_enc, 0x20),
    (M, "あんなにはりきっちゃって‥‥","0146956e6f738e51676587676af1f107",     1, 14, "SO FIRED UP",       tbl_enc, 0x20),
    (M, "かえろっか プーイ",       "200a4f4c91674f20ccef9907",             2, 9,  "HEAD HOME",         tbl_enc, 0x20),
    (M, "ぷぷう",                "20047b7b4a07",                         2, 3,  "PUU",               tbl_enc, 0x20),
    (M, "な～～にをごちゃごちゃ言ってる！","20186ef0f06f945865875865871322676a8fed01", 2, 17, "QUIT YER MUMBLING", tbl_enc, 0x20),
    (M, "いくぞ！！",             "01485362eded07",                       1, 5,  "GO!!!",             tbl_enc, 0x20),
    (M, "う‥‥‥ ダメみた～い",     "20164af1f1f120b5d68363f04801",         2, 11, "NO GOOD HUH",       tbl_enc, 0x20),
    (M, "しょうがないなあ",        "015b8b4a506e486e4607",                 1, 8,  "OH WELL!",          tbl_enc, 0x20),
    (M, "もう‥‥",               "201c6b86f1f101",                       2, 4,  "UGH!",              tbl_enc, 0x20),
    (M, "なんでこんなコトに",      "016e956b57956ea8bd6f01",               1, 9,  "HOW DID I",         tbl_enc, 0x20),
    (M, "なっちゃったのかしら‥‥",  "016e6765876763724f5b8df1f107",         1, 12, "END UP HERE",       tbl_enc, 0x20),
    (M, "ぷうぷう",              "20067b4a7b4a07",                       2, 4,  "PUPU",              tbl_enc, 0x20),
    (M, "ふん！",                "2014797995ed01",                       1, 5,  "HMPH!",             tbl_enc, 0x20),
    (M, "いくぜ！かくごしろよ！！", "01485360ed204f53585b918ceded07",       1, 13, "READY OR NOT!",     tbl_enc, 0x20),
    (M, "ガドインにでも",         "201aa1be99e66f6b8601",                 2, 7,  " GADWIN",           tbl_enc, 0x20),
    (M, "お仕置きしてもらおうかしら‥‥","014e13601074515b6a868d4e4a4f5b8df1f107", 1, 17, "SHOULD PUNISH YOU", tbl_enc, 0x20),
    (M, "ふん！今日から このガンツさまの","201e7995ed20134111ce4f8d205772a1e6b959827201", 2, 19, "FROM TODAY YOURE", tbl_enc, 0x20),
    (M, "ヨメにしてやる！",        "01ddd66f5b6a888fed07",                 1, 8,  "MY BRIDE",          tbl_enc, 0x20),
    (M, "へへ～～～んだ！",        "20267c7cf0f0f09564ed01",               2, 8,  "HA HA!!!",          tbl_enc, 0x20),
    (M, "こっちだって負けないんだから！！","0157676564676a1481556e4895644f8deded01", 1, 17, "IM NOT LOSING!!!",  tbl_enc, 0x20),
    (M, "この勝負‥‥‥",           "01577213a01481f1f1f107",               1, 9,  "THE MATCH",         tbl_enc, 0x20),
    (M, "おれさまの勝ちだ！！！！",  "200e4e9059827213a06564edededed07",     2, 13, "IS MINE!!!!!!",     tbl_enc, 0x20),
    (M, "ちょっと！",             "201c658b676ced01",                     2, 5,  "HEY!!",             tbl_enc, 0x20),
    (M, "ヒトの話は最後まで聞きなさい！！","01c7bd7210077310cd115f826b1488516e5948eded07", 1, 20, "LET PEOPLE FINISH!!!", tbl_enc, 0x20),
    # --- BARLG game-7 tank-battle intro (JIS X0201 / ASCII, pad 0x00) ---
    (B, "Bﾎﾞﾀﾝｦ ｵｼﾃｸﾀﾞｻｲ",  "ff42cedec0dda620b5bcc3b8c0debbb200",   1, 15, "Press B Button",       ascii_enc, 0x00),
    (B, "ﾊﾞｯ (laugh unit)",   "ffffffcadeaf00",                       3, 3,  "HA!",                  ascii_enc, 0x00),
    (B, "ﾊﾞｰﾙﾀﾞ,",           "cadeb0d9c0de2c0000000000000000",       0, 16, "GENERAL BAAL!",        ascii_enc, 0x00),
    (B, " ﾋｷｮｳﾓﾉﾒ",          "20cbb7aeb3d3c9d2000000000000",         0, 14, " YOU COWARD!",         ascii_enc, 0x00),
    (B, " ｺﾛｼﾃﾔﾙ",           "20badbbcc3d4d90000000000000000000000", 0, 18, " ILL DESTROY YOU!",    ascii_enc, 0x00),
    (B, " ｼｺﾝﾃﾞﾔﾙ",          "20bcbaddc3ded4d90000000000000000000000000000", 0, 22, " ILL TRAIN YOU HARD!", ascii_enc, 0x00),
    (B, " ﾀｽｶｯﾀ",            "20c0bdb6afc00000000000000000",         0, 14, " PHEW, SAVED!",        ascii_enc, 0x00),
    (B, "ﾜﾚﾊ ｶﾞｰﾗｲﾙｸﾞﾝﾉ ｼｮｳｸﾞﾝ", "dcdaca20b6deb0d7b2d9b8deddc920bcaeb3b8dedd20", 0, 22, "I AM THE GARLYLE ARMY", ascii_enc, 0x00),
]

RAW_SECTOR, SYNC, USER = 2352, 16, 2048


def file_extent(f, name):
    for path, lba, size in iso.walk(f):
        if path.rsplit("/", 1)[-1] == name:
            return lba, size
    raise SystemExit(f"{name}: not on disc")


def read_span(f, lba, size):
    out = bytearray()
    for i in range((size + USER - 1) // USER):
        f.seek((lba + i) * RAW_SECTOR + SYNC)
        out += f.read(USER)
    return bytes(out[:size])


def write_span(f, lba, data):
    for i in range((len(data) + USER - 1) // USER):
        f.seek((lba + i) * RAW_SECTOR + SYNC)
        f.write(data[i * USER:(i + 1) * USER])


def main() -> int:
    track = Path(sys.argv[1])
    check = "--check" in sys.argv
    patched = skipped = 0
    with open(track, "rb" if check else "r+b") as f:
        cache = {}
        for fname, label, pat_hex, off, ln, en, enc, pad in ENTRIES:
            if fname not in cache:
                lba, size = file_extent(f, fname)
                cache[fname] = [lba, bytearray(read_span(f, lba, size)), False]
            lba, data, _ = cache[fname]
            pat = bytes.fromhex(pat_hex)
            body = enc(en)
            assert len(body) <= ln, f"{label}: {en!r} too long ({len(body)}>{ln})"
            repl = body + bytes([pad]) * (ln - len(body))
            n = data.count(pat)
            if n == 0:
                # already-English probe: pattern with the span replaced
                probe = pat[:off] + repl + pat[off + ln:]
                if probe in data:
                    print(f"  SKIP (already English): {fname} {label}")
                    skipped += 1
                    continue
                raise SystemExit(f"ERROR: {fname} {label}: JP pattern not found, English absent")
            pos = 0
            while True:
                i = data.find(pat, pos)
                if i < 0:
                    break
                data[i + off:i + off + ln] = repl
                pos = i + len(pat)
            cache[fname][2] = True
            print(f"  PATCH x{n}: {fname} {label} -> {en!r}")
            patched += n
        if not check:
            for fname, (lba, data, dirty) in cache.items():
                if dirty:
                    write_span(f, lba, bytes(data))
    print(f"{'CHECK' if check else 'FOLD'} done: {patched} patched, {skipped} already-English")
    return 0


if __name__ == "__main__":
    sys.exit(main())
