#!/usr/bin/env python3
"""Drive build_mdt.py across every dialogue-bearing MDT with the proven Step-3 recipe.

For each MDT whose script/<MDT>_en.py has SEG_TEXTS, derive:
  --seg          = every SEG_TEXTS piece:idx  (the dialogue)
  --skip-pieces  = the RUN_TEXTS piece-code prefixes (names/menus — built separately, output/044)
and run:  build_mdt.py --attempt dlg_<MDT> --paginate --align-scn --wrap 30 --seg ... --skip-pieces ...

The pagination path auto-applies the even-pad + 0x3NNN box fix (subst.substitute_piece_boxes_paginate)
and the sector-aligned SCN growth (--align-scn). Captures pass/fail + deltas per MDT.

Usage: python3 tools/build_all_dialogue.py [MDT ...]   (default: all dialogue MDTs)
"""
import importlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "script"))


# E800_intro_en.py is the alternate flat-schema intro translation (idx->text), applied to E800's
# intro piece, not a standalone MDT (the disc has no E800_intro.MDT). 34 scripts - this = 33 MDTs.
NOT_AN_MDT = {"E800_intro"}

# 2000's SCN is 60544B; script-piece pointers are 16-bit (ScriptPointerTable.java:123, max 65535B),
# so full-English pagination (which would grow it to ~87KB) overflows the pointer space and corrupts
# the script. 2000 must use the EQUAL-LENGTH path (length-preserving, injected in place). It's the
# only MDT large enough to hit this limit. See memory step3-2000-pointer-limit.
EQUAL_LENGTH_ONLY = {"2000"}


def mdt_args(base):
    if base in NOT_AN_MDT:
        return ("skip", "alt-schema / not a standalone MDT")
    m = importlib.import_module(base + "_en")
    seg = getattr(m, "SEG_TEXTS", {})
    run = getattr(m, "RUN_TEXTS", {})
    if not seg:
        return None
    # Every real MDT maps piece_code -> {seg_idx: text}. Anything else is a non-standard file.
    if any(not isinstance(sm, dict) for sm in seg.values()):
        return ("skip", "non-standard SEG_TEXTS schema")
    seg_tokens = []
    for code, sm in seg.items():
        for idx in sorted(int(k) for k in sm):
            seg_tokens.append(f"{code}:{idx}")
    skip = ",".join(sorted(run.keys()))
    return ",".join(seg_tokens), skip


def main():
    import glob
    all_bases = [os.path.basename(f)[:-6] for f in sorted(glob.glob(os.path.join(ROOT, "script/*_en.py")))]
    targets = sys.argv[1:] or all_bases
    results = []
    for base in targets:
        args = mdt_args(base)
        if args is None:
            results.append((base, "SKIP", "no dialogue (names-only)"))
            continue
        if args[0] == "skip":
            results.append((base, "SKIP", args[1]))
            continue
        seg, skip = args
        cmd = [sys.executable, os.path.join(ROOT, "src/build_mdt.py"),
               "--attempt", f"dlg_{base}", "--seg", seg]
        if base not in EQUAL_LENGTH_ONLY:
            # full-English growth path; 2000 stays equal-length (16-bit pointer limit, see above)
            cmd += ["--paginate", "--align-scn", "--wrap", "30"]
        if skip:
            cmd += ["--skip-pieces", skip]
        cmd.append(base)
        print(f"\n========== {base} ==========", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()
        for ln in tail[-12:]:
            print("  " + ln)
        status = "OK" if r.returncode == 0 else "FAIL"
        summary = tail[-1] if tail else ""
        results.append((base, status, summary))

    print("\n\n===== SUMMARY =====")
    for base, status, summary in results:
        print(f"{status:5} {base:14} {summary}")
    fails = [b for b, s, _ in results if s == "FAIL"]
    print(f"\n{sum(1 for _,s,_ in results if s=='OK')} OK, {len(fails)} FAIL, "
          f"{sum(1 for _,s,_ in results if s=='SKIP')} skipped")
    if fails:
        print("FAILED:", ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
