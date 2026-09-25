#!/usr/bin/env python3
"""Lane O — common viewer PAUSE/EXIT dialog ("終了しますか? / はい / いいえ") -> English.

The Start-button pause dialog that appears in the museum VIEWERS is stored, in the
theater-screening menu (/FIELD/DORAM.BIN) and the expression-collection viewer
(/FIELD/FACE2.DAT), as a standard **SCN box-run** using the Grandia 16x16 tbl:

    201e | <main string> | 01 | 200a00<c1> | opt1 | 0a00f0 | 200a00<c2> | opt2 | 0a00f0 | 07f000

where <c1>/<c2> in {fa = highlighted, f0 = normal} give two pre-rendered cursor
states (one block with 'はい' highlighted, one with 'いいえ' highlighted). Each file
contains BOTH state blocks. The blocks are byte-identical across DORAM and FACE2.

Grandia 16x16 tbl has UPPERCASE Latin only (A=0x2B..Z=0x44, ?=0xEC, space=0x20), so
the English is UPPERCASE ("QUIT? / YES / NO") to match the other viewer UI (laneK's
"DESIGN MATERIALS"). The replacement is **size-preserving** (34 -> 34 bytes):

    終了しますか？(9B) + はい(2B) + いいえ(3B)  =  QUIT? padded(9B) + YES(3B) + NO(2B) = 14 text B

so it can be applied to the raw disc image in place (no ISO/pointer changes).

NOTE (monster book /FIELD/MONST.BIN + design-materials /FIELD/MATER.BIN): those two
viewers render the SAME-looking dialog but NOT from a tbl box-run — the string is not
present as text anywhere on the disc or in RAM (searched all encodings). It is baked
into their compressed 2-colour UI/font art (the ST1 viewer-art subsystem). This tool
does NOT touch MONST/MATER (Lanes M/N own those overlays); see docs/lanes/laneO-*.md.

Usage:
    viewer_pausedlg.py patch  <track1.bin>          # in-place, idempotent
    viewer_pausedlg.py verify <track1.bin>          # report JP/EN/absent per block
    viewer_pausedlg.py fold   <track1.bin>          # alias of patch (build-chain hook)
"""
from __future__ import annotations
import sys

# --- tbl helpers (Grandia 16x16) -------------------------------------------------
# space=0x20, digits 0-9 = 0x21-0x2A, A-Z = 0x2B-0x44, ?=0xEC
def _u(ch: str) -> int:
    if ch == ' ':
        return 0x20
    if ch == '?':
        return 0xEC
    if 'A' <= ch <= 'Z':
        return 0x2B + (ord(ch) - ord('A'))
    raise ValueError(f"no 16x16 tbl glyph for {ch!r}")

def _txt(s: str) -> bytes:
    return bytes(_u(c) for c in s)

# --- the two JP state blocks and their English size-preserving replacements ------
# main JP: 終了しますか？ = 115d 115e 5b 82 5d 4f ec  (9 bytes, 7 glyphs)
_JP_MAIN  = bytes.fromhex("115d115e5b825d4fec")   # 9 B
_JP_HAI   = bytes.fromhex("7348")                 # はい  2 B
_JP_IIE   = bytes.fromhex("48484c")               # いいえ 3 B

_EN_MAIN  = _txt("  QUIT?  ")                      # 9 B (2 lead + QUIT? + 2 trail)
_EN_YES   = _txt("YES")                            # 3 B
_EN_NO    = _txt("NO")                             # 2 B
assert len(_EN_MAIN) == len(_JP_MAIN)
assert len(_EN_YES) + len(_EN_NO) == len(_JP_HAI) + len(_JP_IIE)

def _block(main, opt1, c1, opt2, c2):
    # 201e main 01 200a00 c1 opt1 0a00f0 200a00 c2 opt2 0a00f0 07f000
    return (b"\x20\x1e" + main + b"\x01"
            + b"\x20\x0a\x00" + bytes([c1]) + opt1 + b"\x0a\x00\xf0"
            + b"\x20\x0a\x00" + bytes([c2]) + opt2 + b"\x0a\x00\xf0"
            + b"\x07\xf0\x00")

# state A: first option highlighted (fa), second normal (f0)
JP_A = _block(_JP_MAIN, _JP_HAI, 0xfa, _JP_IIE, 0xf0)
JP_B = _block(_JP_MAIN, _JP_HAI, 0xf0, _JP_IIE, 0xfa)
EN_A = _block(_EN_MAIN, _EN_YES, 0xfa, _EN_NO, 0xf0)
EN_B = _block(_EN_MAIN, _EN_YES, 0xf0, _EN_NO, 0xfa)
for a, b in ((JP_A, EN_A), (JP_B, EN_B)):
    assert len(a) == len(b) == 34, (len(a), len(b))

PAIRS = [(JP_A, EN_A), (JP_B, EN_B)]

def _count(data: bytes, needle: bytes):
    idx, out = 0, []
    while True:
        i = data.find(needle, idx)
        if i < 0:
            break
        out.append(i)
        idx = i + 1
    return out

def verify(path: str) -> dict:
    data = open(path, "rb").read()
    jp = sum(len(_count(data, jp)) for jp, _ in PAIRS)
    en = sum(len(_count(data, en)) for _, en in PAIRS)
    return {"jp_blocks": jp, "en_blocks": en}

def patch(path: str) -> int:
    data = bytearray(open(path, "rb").read())
    replaced = 0
    for jp, en in PAIRS:
        for i in _count(bytes(data), jp):
            data[i:i + len(jp)] = en
            replaced += 1
    already = sum(len(_count(bytes(data), en)) for _, en in PAIRS)
    if replaced:
        open(path, "wb").write(data)
    else:
        # idempotent: nothing to do because already English?
        if already < 2:  # expect >=2 EN blocks (DORAM + FACE2 each 2, but any track subset)
            print(f"WARNING: no JP dialog blocks found and only {already} EN block(s) present "
                  f"in {path}; expected either JP (to convert) or EN (already done).",
                  file=sys.stderr)
    print(f"{path}: replaced {replaced} JP block(s); EN blocks now present = {already}")
    return replaced

def main(argv):
    if len(argv) < 3 or argv[1] not in ("patch", "fold", "verify"):
        print(__doc__)
        return 2
    cmd, path = argv[1], argv[2]
    if cmd == "verify":
        print(verify(path))
        return 0
    patch(path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
