#!/usr/bin/env python3
"""Step-3 per-MDT build driver: apply script/<MDT>_en.py into the JP track & build a test image.

Generalizes build_attempt.py / build_expand.py to consume the Step-2 translation files
(SEG_TEXTS = portrait dialogue, RUN_TEXTS = location/door/save names) for ANY MDT, in the
NON-TRUNCATING (grow) mode the user asked for: the full accuracy English is injected and the
file grown as needed, with the sector-count header fields fixed and the file injected in place
when it still fits its original sector span, otherwise relocated to the end of the track
(relayout.py, the attempt-016 recipe). Multiple MDTs are applied CUMULATIVELY onto one track.

  build_mdt.py --attempt 033 EA04                # one MDT onto a fresh JP track
  build_mdt.py --attempt 040 EA04 EC0C EB00 ...  # several, cumulative, into one build

Each MDT's source bytes are always read from the original JP track; the patched MDT is written
into the working (accumulating) track. Output: output/<attempt>/ (Track1.bin, Track2.bin, cue).
"""
from __future__ import annotations

import argparse
import glob
import importlib
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CP = ROOT / "tools/vendor/GrandiaTranslation/GrandiaTranslationTools/target/classes"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "script"))
import iso  # noqa: E402
import relayout  # noqa: E402
import subst  # noqa: E402

RECON_PARTS = ["HEADER", "PRESCRIPT", "GRAPHICS", "FOOTER"]


def sh(*a):
    r = subprocess.run([str(x) for x in a], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("cmd failed: " + " ".join(map(str, a)))
    return r.stdout


def java(*a):
    return sh("java", "-cp", str(CP), "com.grandia.cli.MDTParserCLI", *a)


def find_bin(n):
    return glob.glob(str(ROOT / f"input/**/*Track {n}*.bin"), recursive=True)[0]


def fix_sectors(mdt: bytearray) -> tuple[int, int, int]:
    """Correct the MDT header CD-sector-count fields for a grown file (see build_expand.py):
    0x180 = (A, B), 0x1F4.w0 = A, where A = ceil(end_of_graphics/2048), B = footer sectors,
    A + B = total file sectors. The reconstructor updates 0x1FC (end_of_graphics) but not these,
    so a grown file would read one sector short -> crash without this."""
    total = (len(mdt) + 2047) // 2048
    end_graphics = struct.unpack(">I", mdt[0x1FC:0x200])[0]
    A = (end_graphics + 2047) // 2048
    B = total - A
    struct.pack_into(">I", mdt, 0x180, A)
    struct.pack_into(">I", mdt, 0x184, B)
    struct.pack_into(">I", mdt, 0x1F4, A)
    return A, B, total


def apply_en(base: str, pieces_dir: Path, names_only: bool = False,
             skip_prefixes: tuple[str, ...] = (), grow_prefixes: tuple[str, ...] = (),
             seg_filter: dict[str, set[int]] | None = None, wrap: int = 22,
             paginate: bool = False, grow_filter: dict[str, set[int]] | None = None,
             merge_boxes: tuple[str, ...] = ()) -> dict:
    """Apply script/<base>_en.py (SEG_TEXTS + RUN_TEXTS) to the parsed piece files in place.
    Returns per-piece size deltas for reporting. With names_only=True, skip SEG_TEXTS dialogue
    (which still needs pagination) and translate only RUN_TEXTS (location/door/save/menu names).

    RUN_TEXTS handling: EQUAL-LENGTH glyph-capped fit by default (safe — preserves every box's
    size calc; the proven 010 recipe). Piece codes starting with a grow_prefix instead use the
    non-truncating GROW path — only safe for name-overlay pieces (c000 banner), NOT sized
    boxes/menus (grown menus overflow their box -> freeze, seen in output/035).
    skip_prefixes: piece codes starting with any of these are left untranslated.

    seg_filter: if given, translate ONLY these dialogue segments {piece_code: {seg_idx,...}} via the
    GROW path (8x16 mixed-case, the proven E800 dialogue font), ignoring skip_prefixes for SEG; the
    bigger file is relocated by build_one. Caller must ensure each grown segment stays <=3 lines
    (pagination not yet wired) or it will vertically overflow. RUN names still apply normally."""
    en = importlib.import_module(f"{base}_en")
    # Optional box-fit overlay: script/<base>_fit.py SEG_TEXTS holds terse, equal-length-targeted
    # rephrasings that fit each segment's JP byte budget (the clean dialogue path — no expansion,
    # which corrupts graphics). Where present it overrides the accuracy-first _en.py text.
    try:
        fit_seg = getattr(importlib.import_module(f"{base}_fit"), "SEG_TEXTS", {})
    except ModuleNotFoundError:
        fit_seg = {}
    deltas: dict[str, tuple[int, int]] = {}

    def has(code, prefixes):
        return any(code.startswith(p) for p in prefixes)

    seg_texts = {} if names_only else getattr(en, "SEG_TEXTS", {})
    for code, seg_map in seg_texts.items():
        if seg_filter is not None and code not in seg_filter:
            continue
        if seg_filter is None and has(code, skip_prefixes):
            continue
        # Paginate uses the FULL accuracy English (it can fit it across screens); equal-length uses
        # the box-fit overlay where present (it must be terse).
        src = dict(seg_map) if paginate else {**seg_map, **fit_seg.get(code, {})}
        rmap = {int(k): v for k, v in src.items()}
        if seg_filter is not None:
            rmap = {k: v for k, v in rmap.items() if k in seg_filter[code]}
            if not rmap:
                continue
        pf = pieces_dir / code
        data = pf.read_bytes()
        if paginate:
            # 016 path: full English split into <=3-line screens (0x02 + own portrait break). Grows
            # the piece; injected in place while it still fits the sector span. If the piece is an
            # interpreter command stream with box-render commands (0x2NNN, e.g. E80C 500a), use the
            # box-aware paginate so each grown box's NNN length word is rewritten — otherwise the
            # engine advances by the stale length and the next box starts mid-text (the Jin loop;
            # see work/scnrl/vm_notes.md).
            grow_set = grow_filter.get(code) if grow_filter else None
            if grow_set is not None:
                # MIXED mode (validated via the YMIR harness, output/068): pieces with a mid-convo
                # EVENT OP (50 01 00 19f0…, has_inter_segment_bytecode) loop/garbage when segments
                # BEFORE the op grow (the op's absolute target goes stale). So grow ONLY segs after
                # the op (grow_set) with full English; substitute every other seg EQUAL-LENGTH (terse
                # fit text) so nothing before the op shifts. Equal-length pass is length-preserving,
                # so the box-aware grow pass then operates on a structurally identical piece.
                eq_src = {int(k): v for k, v in {**seg_map, **fit_seg.get(code, {})}.items()
                          if int(k) in rmap and int(k) not in grow_set}
                gr_src = {int(k): v for k, v in seg_map.items()
                          if int(k) in rmap and int(k) in grow_set}
                data = subst.substitute_piece_perseg(data, eq_src, min_glyphs=4)
                out = subst.substitute_piece_boxes_paginate(data, gr_src, wrap=wrap)
            elif subst.has_box_commands(data):
                if any(code.startswith(p) for p in merge_boxes):
                    # Pieces with a mid-convo event op (500a): merge boxes so the op can't corrupt
                    # the box->box handoff (full English + no junk). See subst.substitute_piece_boxes_merge.
                    out = subst.substitute_piece_boxes_merge(data, rmap, wrap=wrap)
                else:
                    out = subst.substitute_piece_boxes_paginate(data, rmap, wrap=wrap)
            else:
                out = subst.substitute_piece_perseg_paginate(data, rmap, wrap=wrap)
        else:
            # EQUAL-LENGTH (clean 047 path): 8x16 mixed-case, padded to original byte length -> no
            # graphics shift. Text must be box-fit terse to the JP byte budget.
            out = subst.substitute_piece_perseg(data, rmap, min_glyphs=4)
            assert len(out) == len(data), f"{code}: seg substitution changed length"
        pf.write_bytes(out)
        deltas[code] = (len(data), len(out))
    # GROW_RUN_PIECES: RUN_TEXTS pieces that are TEXT-RUN box-command streams (E814 piece 0 prize
    # messages, 6001-6008 minigame titles/help) whose flat runs glue the 0x2NNN box command onto the
    # first line. Under the 8x16-default disc these route through substitute_piece_boxruns (per-box,
    # ASCII) instead of the page-0 substitute_piece_runs (which clobbers the box command -> garble).
    # The value is the per-box GROW gate: None = grow all boxes; a set of run keys = only boxes whose
    # mapped runs are all in the set may grow, the rest stay EQUAL-LENGTH (title boxes 6001-7 must not
    # grow — it desyncs the following 0x50 op). Accepts a bare set/None or a {code: grow_keys} dict.
    grow_run = getattr(en, "GROW_RUN_PIECES", {})
    if not isinstance(grow_run, dict):
        grow_run = {c: None for c in grow_run}
    # TIGHT_RUN_PIECES (lane W1): {piece: {run keys}} — eqlen runs allowed the 1-byte 0x04 commit
    # (no trailing pad space) when the text is exactly one byte over; buys one character on
    # byte-starved title lines (E814 6003 "Feena's Panties"). See subst._eqlen_line(tight=...).
    tight_run = getattr(en, "TIGHT_RUN_PIECES", {})
    for code, run_map in getattr(en, "RUN_TEXTS", {}).items():
        if has(code, skip_prefixes):
            continue
        pf = pieces_dir / code
        data = pf.read_bytes()
        rmap = {int(k): v for k, v in run_map.items()}
        # Banner = location/door name overlays (c000, d0xx, e001) rendered by the box-cmd prefix path.
        # NOT e000: that is the save-point camp MENU (Save/Recover/Quit [+Exhibit Count]) which must
        # auto-route through the box-aware path, not the banner path (else its menu items garble).
        is_banner = code.startswith(("c000", "d0")) or (code.startswith("e0") and code != "e000")
        if os.environ.get("GDM_8X16") and code in grow_run:
            out = subst.substitute_piece_boxruns(data, rmap, grow_keys=grow_run[code],
                                                 tight_keys=tight_run.get(code, frozenset()))
        elif (os.environ.get("GDM_8X16") and not is_banner
              and subst.is_text_box_stream(data)):
            # Museum/casino terminal & info SCREENS (non-banner text-run box-command pieces) garble
            # under the 8x16-default font via substitute_piece_runs' page-0 path (and it clobbers the
            # box command on each first line). Route through the box-aware path with "auto" grow:
            # description/inscription boxes GROW to full English; interactive menus + boxes followed by
            # a 0x50 event op stay EQUAL-LENGTH (no freeze/desync). Pieces needing a specific grow plan
            # opt in via the MDT's GROW_RUN_PIECES (handled above). Banners stay on the prefix path.
            out = subst.substitute_piece_boxruns(data, rmap, grow_keys="auto")
        elif os.environ.get("GDM_8X16") and code.startswith(("c000", "e001")):
            # ROOM-ENTRY banners only (#11): GROW-to-CENTRE the half-width 8x16 name in its fixed
            # box. Door-preview (d0xx) banners must NOT grow (their trailing `0a 00 d0 7c 07` arrow
            # element breaks — rc_18 lesson); they stay on the equal-length path below, ~5 cells
            # left of true centre.
            centered = subst.substitute_piece_banner_center(data, rmap)
            out = centered if centered is not None else subst.substitute_piece_runs(data, rmap)
        elif has(code, grow_prefixes):
            out = subst.substitute_piece_runs_grow(data, rmap)
        else:
            out = subst.substitute_piece_runs(data, rmap)
        pf.write_bytes(out)
        deltas[code] = (len(data), len(out))
    return deltas


def build_one(base: str, bin1: str, work_track: Path, w: Path, names_only: bool = False,
              skip_prefixes: tuple[str, ...] = (), grow_prefixes: tuple[str, ...] = (),
              seg_filter: dict[str, set[int]] | None = None, paginate: bool = False,
              force_relocate: bool = False, pad_scn: int = 0, align_scn: bool = False,
              wrap: int = 22, grow_filter: dict[str, set[int]] | None = None,
              merge_boxes: tuple[str, ...] = ()) -> None:
    """Patch one MDT (source from JP bin1) into work_track (in place or relocate)."""
    name = base + ".MDT"
    wd = w / base
    for d in ["", "parts", "pieces", "recon", "mdtout"]:
        (wd / d).mkdir(parents=True, exist_ok=True)

    sh(sys.executable, str(ROOT / "src/iso.py"), "extract", bin1, name, str(wd / name))
    orig_size = (wd / name).stat().st_size
    java("parse-mdt", str(wd), str(wd / "parts"), ".MDT", "big")
    if not (wd / "parts" / f"{base}.SCN").exists():
        raise SystemExit(f"{base}: no script section")
    java("parse-script", str(wd / f"parts/{base}.SCN"), str(wd / f"parts/{base}.OFS"),
         str(wd / "pieces"))

    deltas = apply_en(base, wd / "pieces", names_only, skip_prefixes, grow_prefixes, seg_filter,
                      wrap=wrap, paginate=paginate, grow_filter=grow_filter, merge_boxes=merge_boxes)
    for code, (o, n) in sorted(deltas.items()):
        print(f"  {base} piece {code}: {o}B -> {n}B ({n-o:+d})")

    java("reconstruct-script", str(wd / "pieces"), str(wd / f"parts/{base}.OFS"), str(wd / "recon"))
    for ext in RECON_PARTS:
        shutil.copy(wd / f"parts/{base}.{ext}", wd / "recon")
    scn = wd / "recon" / f"{base}.SCN"
    if align_scn:
        # Pad the SCN so its TOTAL size change is an exact multiple of 2048. The graphics sit right
        # after the script, and the room's graphics DMA reads whole CD sectors, so the graphics must
        # keep their position WITHIN their sectors. Shifting them by a whole number of sectors (a
        # 2048-multiple) preserves that; a sub-sector shift misaligns the DMA -> yellow. (049 grew
        # E800 by exactly +2048 = one sector and rendered clean; my +155 did not.)
        orig_scn = (wd / "parts" / f"{base}.SCN").stat().st_size
        pad = (orig_scn - scn.stat().st_size) % 2048
        scn.write_bytes(scn.read_bytes() + b"\x00" * pad)
        print(f"  {base}: aligned SCN growth to a sector multiple (+{pad}B pad)")
    elif pad_scn:
        scn.write_bytes(scn.read_bytes() + b"\x00" * pad_scn)
        print(f"  {base}: padded SCN +{pad_scn}B")
    java("reconstruct-mdt", str(wd / "recon"), str(wd / "mdtout"))

    # Use the Java reconstruct-mdt output VERBATIM — it already recalculates the sector-count fields
    # (0x180/0x1F4), the special-data sector offsets, and pads the footer to a sector boundary, which
    # is what resolves expansion graphics errors (per the GrandiaTranslation wiki). No fix_sectors.
    fixed = wd / "mdtout" / name
    mdt = fixed.read_bytes()
    total = (len(mdt) + 2047) // 2048
    orig_sectors = orig_size // 2048
    grew = any(n > o for o, n in deltas.values())
    print(f"  {base}: rebuilt {len(mdt)}B ({total} sectors); original {orig_size}B "
          f"({orig_sectors} sectors); grew={grew}")

    if len(mdt) <= orig_size and not force_relocate:
        # Still fits its original sector span -> inject IN PLACE (even if content grew; the Java
        # header makes the engine read the right sectors and find the shifted graphics correctly).
        with open(work_track, "rb") as f:
            rec = iso.find_record(f, name)
        sh(sys.executable, str(ROOT / "src/inject.py"), "--bin", str(work_track), "--mdt",
           str(fixed), "--lba", str(rec["lba"]), "--out", str(work_track) + ".tmp",
           "--max-bytes", str(orig_size))
        shutil.move(str(work_track) + ".tmp", work_track)
        print(f"  {base}: injected IN PLACE at LBA {rec['lba']}")
    else:
        out_tmp = str(work_track) + ".tmp"
        relayout.relocate_and_grow(str(work_track), name, str(fixed), out_tmp)
        shutil.move(out_tmp, work_track)
        print(f"  {base}: RELOCATED (needs {total - orig_sectors} more sectors)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--attempt", required=True)
    ap.add_argument("--names-only", action="store_true",
                    help="translate only RUN_TEXTS names/menus; skip SEG_TEXTS dialogue (no pagination yet)")
    ap.add_argument("--skip-pieces", default="",
                    help="comma-separated piece-code prefixes to leave untranslated, e.g. 'd' for door names")
    ap.add_argument("--grow-pieces", default="",
                    help="comma-separated RUN piece-code prefixes to GROW (non-truncating) instead of "
                         "equal-length fit; only safe for name-overlay pieces, e.g. 'c000'")
    ap.add_argument("--seg", default="",
                    help="translate ONLY these dialogue segments, e.g. '5005:0' or '500a:0,500a:8'.")
    ap.add_argument("--paginate", action="store_true",
                    help="dialogue (--seg) uses the 016 pagination path (full English split into "
                         "<=3-line screens) instead of equal-length box-fit. Grows the piece.")
    ap.add_argument("--merge-boxes", default="",
                    help="with --paginate: comma-separated piece-code prefixes whose multiple dialogue "
                         "boxes are MERGED into one box, moving the mid-convo event op after it. Use for "
                         "pieces with inter-segment event bytecode (e.g. 500a) so full-English growth "
                         "renders with no garbage box (validated via the YMIR harness).")
    ap.add_argument("--grow-segs", default="",
                    help="with --paginate: GROW only these segments (full English), e.g. "
                         "'500a:8,500a:9'; every other --seg segment is forced EQUAL-LENGTH. Use for "
                         "pieces with a mid-convo event op (500a) so segments BEFORE the op don't "
                         "shift (validated via the YMIR harness; see memory jin-loop-harness).")
    ap.add_argument("--wrap", type=int, default=22,
                    help="dialogue line-wrap width in 8x16 chars (default 22; the box holds ~30+).")
    ap.add_argument("--relocate", action="store_true",
                    help="force RELOCATION (append at track end + repoint dir record) even if the "
                         "grown MDT still fits its hole — the 049 method (single-file relocate).")
    ap.add_argument("--pad-scn", type=int, default=0,
                    help="append N zero bytes after the script (raw).")
    ap.add_argument("--align-scn", action="store_true",
                    help="pad the SCN so its size change is an exact 2048 multiple -> graphics shift "
                         "by whole sectors, preserving intra-sector DMA alignment (the 049 trick).")
    ap.add_argument("mdts", nargs="+", help="MDT base names, e.g. EA04 EC0C")
    a = ap.parse_args()
    skip_prefixes = tuple(p for p in a.skip_pieces.split(",") if p)
    grow_prefixes = tuple(p for p in a.grow_pieces.split(",") if p)
    seg_filter: dict[str, set[int]] | None = None
    if a.seg:
        seg_filter = {}
        for tok in a.seg.split(","):
            pc, idx = tok.split(":")
            seg_filter.setdefault(pc, set()).add(int(idx))
    merge_boxes = tuple(p for p in a.merge_boxes.split(",") if p)
    grow_filter: dict[str, set[int]] | None = None
    if a.grow_segs:
        grow_filter = {}
        for tok in a.grow_segs.split(","):
            pc, idx = tok.split(":")
            grow_filter.setdefault(pc, set()).add(int(idx))

    out = ROOT / f"output/{a.attempt}"
    w = out / "work"
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True, exist_ok=True)
    bin1, bin2 = find_bin(1), find_bin(2)

    work_track = out / "Track1.bin"
    shutil.copyfile(bin1, work_track)
    for base in a.mdts:
        base = base.removesuffix(".MDT")
        print(f"== {base} ==")
        build_one(base, bin1, work_track, w, a.names_only, skip_prefixes, grow_prefixes, seg_filter,
                  a.paginate, a.relocate, a.pad_scn, a.align_scn, a.wrap, grow_filter, merge_boxes)

    shutil.copy(bin2, out / "Track2.bin")
    (out / "Grandia-DM-patched.cue").write_text(
        'FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
        'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')
    print(f"\nbuilt output/{a.attempt}/  ({len(a.mdts)} MDT(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
