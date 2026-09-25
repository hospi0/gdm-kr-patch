#!/usr/bin/env python3
"""Cumulative FINAL build: all MDTs (names + dialogue) into one patched track.

Default mode mirrors build_mdt.main()'s loop but applies per-MDT flags into one accumulating
Track1.bin (2000 equal-length; the rest paginated full-English; RUN_TEXTS names equal-length fit).

--widen mode applies the SCNRL offset-widening patch (tools/widen_offsets.py) so 2000 can be
full-English too (the 64KB 16-bit OFS cap is lifted to 128KB):
  * GDM_HALVE_OFS=1 -> reconstruct-script emits off//2 for EVERY MDT (the patched resolver does <<1).
  * 2000 builds paginated full-English (no longer equal-length).
  * The 3 untranslated /FIELD MDTs (0000, 0004, E8FF) get an OFS-only rewrite (halved) so they still
    resolve under the patched resolver.
  * SCNRL.BIN in the track is patched (resolver -> base + (off<<1)).
Because the resolver is shared, --widen is all-or-nothing: every script the engine loads must have a
halved OFS. See docs/step3-dialogue-RE-log.md.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "script"))
sys.path.insert(0, str(ROOT / "tools"))
import build_mdt  # noqa: E402
import iso  # noqa: E402
import widen_offsets  # noqa: E402

EQUAL_LENGTH_ONLY = {"2000"}                 # only when NOT --widen
UNTRANSLATED = ["0000", "0004", "E8FF"]      # /FIELD MDTs with no _en.py (OFS-rewrite only under --widen)


def real_mdts():
    return [os.path.basename(f)[:-6] for f in sorted(glob.glob(str(ROOT / "script/*_en.py")))
            if os.path.basename(f)[:-6] != "E800_intro"]


def passthrough_mdt(base, bin1, work_track, w):
    """Re-emit an UNTRANSLATED MDT through the pipeline (no text change) so its OFS is halved by the
    GDM_HALVE_OFS-patched reconstruct-script. SCN size unchanged -> inject in place."""
    name = base + ".MDT"
    wd = w / base
    for d in ["", "parts", "pieces", "recon", "mdtout"]:
        (wd / d).mkdir(parents=True, exist_ok=True)
    build_mdt.sh(sys.executable, str(ROOT / "src/iso.py"), "extract", str(bin1), name, str(wd / name))
    orig_size = (wd / name).stat().st_size
    build_mdt.java("parse-mdt", str(wd), str(wd / "parts"), ".MDT", "big")
    if not (wd / "parts" / f"{base}.SCN").exists():
        print(f"  {base}: no script section, skipped"); return
    build_mdt.java("parse-script", str(wd / f"parts/{base}.SCN"), str(wd / f"parts/{base}.OFS"),
                   str(wd / "pieces"))
    build_mdt.java("reconstruct-script", str(wd / "pieces"), str(wd / f"parts/{base}.OFS"),
                   str(wd / "recon"))
    for ext in build_mdt.RECON_PARTS:
        shutil.copy(wd / f"parts/{base}.{ext}", wd / "recon")
    build_mdt.java("reconstruct-mdt", str(wd / "recon"), str(wd / "mdtout"))
    fixed = wd / "mdtout" / name
    if fixed.stat().st_size > orig_size:
        raise SystemExit(f"{base}: passthrough grew ({fixed.stat().st_size} > {orig_size})?!")
    with open(work_track, "rb") as f:
        rec = iso.find_record(f, name)
    build_mdt.sh(sys.executable, str(ROOT / "src/inject.py"), "--bin", str(work_track), "--mdt",
                 str(fixed), "--lba", str(rec["lba"]), "--out", str(work_track) + ".tmp",
                 "--max-bytes", str(orig_size))
    shutil.move(str(work_track) + ".tmp", work_track)
    print(f"  {base}: OFS-rewrite (halved), injected IN PLACE at LBA {rec['lba']}")


def patch_scnrl_in_track(work_track):
    """Extract SCNRL.BIN from the track, apply the resolver word-scale patch, inject in place."""
    with open(work_track, "rb") as f:
        rec = iso.find_record(f, "SCNRL.BIN")
    tmp = work_track.parent / "SCNRL.BIN"
    build_mdt.sh(sys.executable, str(ROOT / "src/iso.py"), "extract", str(work_track), "SCNRL.BIN", str(tmp))
    raw = tmp.read_bytes()
    patched = widen_offsets.patch_scnrl(raw)
    tmp.write_bytes(patched)
    build_mdt.sh(sys.executable, str(ROOT / "src/inject.py"), "--bin", str(work_track), "--mdt",
                 str(tmp), "--lba", str(rec["lba"]), "--out", str(work_track) + ".tmp",
                 "--max-bytes", str(len(raw)))
    shutil.move(str(work_track) + ".tmp", work_track)
    print(f"  SCNRL.BIN: resolver word-scale patch injected IN PLACE at LBA {rec['lba']} "
          f"(changed {sum(1 for a,b in zip(raw,patched) if a!=b)} bytes)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt", default="final")
    ap.add_argument("--wrap", type=int, default=30)
    ap.add_argument("--widen", action="store_true",
                    help="apply the SCNRL offset-widening patch so 2000 can be full-English too")
    ap.add_argument("--8x16", dest="force_8x16", action="store_true",
                    help="force the 8x16 text paths (GDM_8X16=1) even without --widen (for piece-level "
                         "A/B tests; the disc itself only gets the SCNRL font patch under --widen)")
    ap.add_argument("--no-8x16", action="store_true",
                    help="legacy page-0 disc (vanilla 16x16-default font) even under --widen")
    ap.add_argument("mdts", nargs="*")
    a = ap.parse_args()
    mdts = a.mdts or real_mdts()
    if a.widen:
        os.environ["GDM_HALVE_OFS"] = "1"
    # The shipping RC disc is the 8x16 --widen build. GDM_8X16 used to come only from the caller's
    # environment; forgetting it (rc_20) silently built the museum terminal/banner RUN_TEXTS via the
    # page-0 path, whose leading 0x03 makes 0x03-honoring renderers read page-0 codes as ASCII ->
    # garbled terminal menus (E80C 600c: "BACK" -> ",+-5") + freeze on select. Default it ON whenever
    # --widen is set (patch_scnrl then applies the matching default-8x16 font patch to the disc), so
    # the mode can no longer be lost between sessions. Non-widen builds keep the legacy page-0
    # default (their SCNRL is never font-patched, so page-0 is the self-consistent encoding there);
    # --8x16 forces the ASCII paths on, --no-8x16 forces them off.
    want_8x16 = (a.widen or a.force_8x16 or bool(os.environ.get("GDM_8X16"))) and not a.no_8x16
    if want_8x16:
        os.environ["GDM_8X16"] = "1"
    else:
        os.environ.pop("GDM_8X16", None)
    print(f"font mode: {'8x16-default (GDM_8X16=1)' if want_8x16 else 'page-0 legacy (vanilla font)'}")

    out = ROOT / f"output/{a.attempt}"
    w = out / "work"
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True, exist_ok=True)
    bin1, bin2 = build_mdt.find_bin(1), build_mdt.find_bin(2)
    work_track = out / "Track1.bin"
    shutil.copyfile(bin1, work_track)

    for base in mdts:
        base = base.removesuffix(".MDT")
        eq = (base in EQUAL_LENGTH_ONLY) and not a.widen
        print(f"== {base} ==  ({'equal-length' if eq else 'paginate'})")
        build_mdt.build_one(base, bin1, work_track, w, names_only=False, skip_prefixes=(),
                            grow_prefixes=(), seg_filter=None, paginate=not eq,
                            align_scn=not eq, wrap=a.wrap)

    if a.widen:
        print("== untranslated MDTs (OFS-rewrite only) ==")
        for base in UNTRANSLATED:
            passthrough_mdt(base, bin1, work_track, w)
        print("== SCNRL resolver patch ==")
        patch_scnrl_in_track(work_track)

    shutil.copy(bin2, out / "Track2.bin")
    (out / "Grandia-DM-patched.cue").write_text(
        'FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
        'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')
    print(f"\nbuilt output/{a.attempt}/  ({len(mdts)} MDTs{' + widen' if a.widen else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
