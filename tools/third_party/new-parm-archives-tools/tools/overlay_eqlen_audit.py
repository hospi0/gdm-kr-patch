#!/usr/bin/env python3
"""Lane-H audit: verify the explicit-0x03 eqlen fix on a built track (and diff two builds).

The "9 Xそたで 9" menu-scroll garble (docs/lanes/laneH-overlay.md) was the eqlen encoder
eliding the leading 0x03 font switch on the FIRST line of each box: the menu cursor-move
redraw re-runs the box bytecode with stale 16x16 font state, so an 0x03-less ASCII line
renders as page-0 16x16 glyphs. src/subst.py _eqlen_line now always emits the 0x03.

  # 1) check a built track: every '* Back *'-style cursor-box first line must carry 05 03
  python3 tools/overlay_eqlen_audit.py check output/rc_NN/Track1.bin

  # 2) diff two builds and list any line whose text LOST a character (eqlen truncation)
  python3 tools/overlay_eqlen_audit.py diff output/old/Track1.bin output/new/Track1.bin
"""
import mmap
import re
import sys

SENTINELS = [b"* Back *", b"** Back **", b"** Save **", b"*** Storage ***"]


def _map(path):
    f = open(path, "rb")
    return f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)


def check(track: str) -> int:
    f, mm = _map(track)
    bad = ok = 0
    for pat in SENTINELS:
        for m in re.finditer(re.escape(pat), mm):
            s = m.start()
            # the line must be reachable from a control (<=0x0F) through an 0x03
            prev, prev2 = mm[s - 1], mm[s - 2]
            if prev == 0x03:
                ok += 1
            elif prev <= 0x0F or prev == 0x01:
                bad += 1
                print(f"MISSING 0x03: {pat.decode()} at {s:#x}  ctx={bytes(mm[s-8:s+12]).hex(' ')}")
            # mid-text matches of the shorter sentinel inside the longer one: skip silently
    print(f"{ok} lines carry the explicit 0x03; {bad} missing")
    return 1 if bad else 0


def diff(old: str, new: str) -> int:
    fa, ma = _map(old)
    fb, mb = _map(new)
    n = min(len(ma), len(mb))
    CH = 1 << 22
    diffs = []
    for off in range(0, n, CH):
        ca, cb = ma[off:off + CH], mb[off:off + CH]
        if ca != cb:
            diffs.extend(off + i for i in range(len(ca)) if ca[i] != cb[i])
    rngs = []
    for d in diffs:
        if rngs and d <= rngs[-1][1] + 4:
            rngs[-1][1] = d
        else:
            rngs.append([d, d])
    print(f"{len(rngs)} changed regions, {len(diffs)} bytes")

    def lines(buf, s, e):
        return re.findall(rb"[\x20-\x7e]{4,}", bytes(buf[s - 40:e + 40]))

    losses = set()
    for s, e in rngs:
        newl = set(lines(mb, s, e))
        for o in set(lines(ma, s, e)):
            ot = o.strip(b" ")
            if ot and not any(ot in nl for nl in newl):
                losses.add((s, ot))
    for s, t in sorted(losses):
        print(f"  {s:#x}  old text gone/shortened: {t!r}  (check: intentional retext, or a "
              f"sector-split false positive?)")
    if not losses:
        print("no line lost a character")
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        return check(sys.argv[2])
    if len(sys.argv) >= 4 and sys.argv[1] == "diff":
        return diff(sys.argv[2], sys.argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
