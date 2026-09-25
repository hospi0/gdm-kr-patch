#!/usr/bin/env python3
"""build_dicdt.py — build the English Monster-Encyclopedia DICDT.DAT and relocate it
into a disc track.

Single integration point for the encyclopedia translation: reads the committed,
human-reviewable translation JSONs under docs/menus/ (the source of truth), derives
the per-section idx->EN patch maps, applies them to a freshly-extracted vanilla
DICDT.DAT via tools/dicdt.py, then relocates the grown file into the track with
src/relayout.py (the game rebuilds its file-index table from the ISO dir at cold
boot, so the relocated copy is what loads — see docs/museum-viewers-format.md).

Sources (docs/menus/):
  monster-uilabels-en.json     -> section 4 (title / 'Monster Book 1-8' / Name:/Habitat:)
  monster-names-en.json        -> section 5 (169 names)
  monster-locales-en.json      -> section 6 (51 unique habitats, mapped per-entry)
  monster-descriptions-en.json -> section 7 (162 groups / 493 lines)
  monster-descriptions-jp.json -> section-7 entry indices per group

Usage:
  build_dicdt.py --bin TRACK1.bin --out TRACK1_out.bin     # relocate English DICDT in
  build_dicdt.py --emit-dat OUT.DAT                         # just build the .DAT (no track)
"""
import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MENUS = ROOT / "docs/menus"
VANILLA = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
sys.path.insert(0, str(ROOT / "tools"))
import dicdt  # noqa: E402


def load(name):
    return json.loads((MENUS / name).read_text())


def sec_maps(vanilla_dat: Path):
    """Derive {section: {entry_idx: EN}} from the committed JSONs + vanilla DICDT order."""
    d = vanilla_dat.read_bytes()
    hdr = struct.unpack_from(">8I", d, 0)

    def entries(s):
        blk = d[hdr[s]:hdr[s + 1] if s + 1 < 8 else len(d)]
        out, i = [], 0
        while i < len(blk):
            e = blk.find(b"\x00", i)
            if e < 0:
                break
            out.append((i, dicdt.decode(blk[i:e]).rstrip() if e > i else ""))
            i = e + 1
        return out  # list of (rel_off, jp) in order; index in list = ordinal entry idx

    maps = {4: {}, 5: {}, 6: {}, 7: {}}
    # sec4 labels + sec5 names: direct idx->en
    for s, fn in [(4, "monster-uilabels-en.json"), (5, "monster-names-en.json")]:
        for r in load(fn):
            maps[s][str(r["idx"])] = r["en"]
    # sec6 locales: unique jp->en, mapped onto each ordinal entry by its decoded JP
    uni = {r["jp"]: r["en"] for r in load("monster-locales-en.json")}
    for idx, (_, jp) in enumerate(entries(6)):
        if jp in uni:
            maps[6][str(idx)] = uni[jp]
    # sec7 descriptions: group->en[] applied to that group's entry indices (from jp json)
    jpg = load("monster-descriptions-jp.json")
    eng = {g["group"]: g["en"] for g in load("monster-descriptions-en.json")}
    for g in jpg:
        for e_ix, line in zip(g["entries"], eng[g["group"]]):
            maps[7][str(e_ix)] = line
    return maps


def build_dat(out_dat: Path, work: Path):
    work.mkdir(parents=True, exist_ok=True)
    vanilla = work / "DICDT_vanilla.DAT"
    subprocess.run([sys.executable, str(ROOT / "src/iso.py"), "extract",
                    str(VANILLA), "DICDT.DAT", str(vanilla)], check=True)
    maps = sec_maps(vanilla)
    cur = vanilla
    for s in (5, 4, 6, 7):  # any order; each patch reads the current header
        mp = work / f"sec{s}.json"
        mp.write_text(json.dumps(maps[s], ensure_ascii=False))
        nxt = work / f"after{s}.DAT"
        subprocess.run([sys.executable, str(ROOT / "tools/dicdt.py"), "patch",
                        str(cur), str(mp), str(nxt), "--section", str(s)], check=True)
        cur = nxt
    out_dat.write_bytes(cur.read_bytes())
    # sanity: every line <= 38 half-width chars (detail box width)
    over = _check_widths(out_dat)
    if over:
        print(f"WARNING: {len(over)} line(s) >38 chars (will clip): {over[:5]}")
    print(f"built {out_dat} ({out_dat.stat().st_size} bytes)")
    return out_dat


def _check_widths(dat: Path):
    d = dat.read_bytes()
    hdr = struct.unpack_from(">8I", d, 0)
    over = []
    for s in (5, 6, 7):
        blk = d[hdr[s]:hdr[s + 1] if s + 1 < 8 else len(d)]
        i = 0
        while i < len(blk):
            e = blk.find(b"\x00", i)
            if e < 0:
                break
            t = dicdt.decode(blk[i:e])
            if len(t) > 38:
                over.append((s, len(t), t))
            i = e + 1
    return over


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bin", help="input track1.bin to relocate the English DICDT into")
    ap.add_argument("--out", help="output track1.bin")
    ap.add_argument("--emit-dat", help="just write the English DICDT.DAT here and stop")
    ap.add_argument("--work", default=str(ROOT / "work/museum/dicdt_build"))
    a = ap.parse_args()
    work = Path(a.work)
    dat = build_dat(Path(a.emit_dat) if a.emit_dat else work / "DICDT_en.DAT", work)
    if a.emit_dat:
        return
    if not (a.bin and a.out):
        sys.exit("need --bin and --out (or --emit-dat)")
    subprocess.run([sys.executable, str(ROOT / "src/relayout.py"), "--bin", a.bin,
                    "--name", "DICDT.DAT", "--mdt", str(dat), "--out", a.out], check=True)
    print(f"relocated English DICDT into {a.out}")
    # MANDATORY companion fix: the viewer overlay (MONST.BIN) loads FIELD/TEXT2.BIN
    # into a 0x7000-byte LWRAM window directly below the DICDT buffer (0x240000);
    # the menus build grows TEXT2 past 0x7000, so its load tail clobbers DICDT's
    # section-offset header -> black screen on book-open (rc_23 user issue #5).
    # Retarget the viewer's TEXT2 buffer to free LWRAM 0x2E0000 (in-place, 11
    # literals; see tools/monst_text2_fix.py + docs/lanes/laneJ-monsterguide.md).
    subprocess.run([sys.executable, str(ROOT / "tools/monst_text2_fix.py"),
                    "patch-track", a.out], check=True)


if __name__ == "__main__":
    main()
