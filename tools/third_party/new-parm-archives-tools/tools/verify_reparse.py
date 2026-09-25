#!/usr/bin/env python3
"""Automated integrity check for the dialogue builds (no emulator/savestate needed).

For each output/dlg_<MDT>/ build: re-extract <MDT>.MDT from the *patched* Track1.bin (post relocate +
injection), then re-run the Java parse-mdt + parse-script on it. A clean round-trip proves the relocate
repointed the directory record correctly and the grown SCN/OFS are structurally valid. Additionally,
for every piece that is a box-command stream (subst.has_box_commands), confirm parse_box_commands
consumes the whole piece (pos == len) — the structural criterion the growth fix targets (no box whose
0x3NNN/0x2NNN length now runs off the end -> the Jin-loop garbage).

Usage: python3 tools/verify_reparse.py [MDT ...]
"""
import glob
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import subst  # noqa: E402

CP = os.path.join(ROOT, "tools/vendor/GrandiaTranslation/GrandiaTranslationTools/target/classes")


def run(*a):
    return subprocess.run([str(x) for x in a], capture_output=True, text=True)


def java(*a):
    return run("java", "-cp", CP, "com.grandia.cli.MDTParserCLI", *a)


def check(base):
    track = os.path.join(ROOT, f"output/dlg_{base}/Track1.bin")
    if not os.path.exists(track):
        return base, "MISSING", "no build"
    with tempfile.TemporaryDirectory() as td:
        mdt = os.path.join(td, f"{base}.MDT")
        r = run(sys.executable, os.path.join(ROOT, "src/iso.py"), "extract", track, f"{base}.MDT", mdt)
        if r.returncode:
            return base, "FAIL", "extract failed"
        parts, pieces = os.path.join(td, "parts"), os.path.join(td, "pieces")
        os.makedirs(parts); os.makedirs(pieces)
        r = java("parse-mdt", td, parts, ".MDT", "big")
        if r.returncode:
            return base, "FAIL", "parse-mdt failed: " + r.stderr.strip().splitlines()[-1:][0] if r.stderr else "parse-mdt failed"
        scn, ofs = os.path.join(parts, f"{base}.SCN"), os.path.join(parts, f"{base}.OFS")
        if not os.path.exists(scn):
            return base, "FAIL", "no SCN after re-parse"
        r = java("parse-script", scn, ofs, pieces)
        if r.returncode:
            return base, "FAIL", "parse-script failed"
        # Box-stream consumption check on every re-parsed piece.
        bad = []
        nbox = 0
        for pf in sorted(glob.glob(os.path.join(pieces, "*"))):
            data = open(pf, "rb").read()
            if subst.has_box_commands(data):
                nbox += 1
                pos = 0
                while pos + 1 < len(data):
                    w = (data[pos] << 8) | data[pos + 1]
                    pos += (2 + (w & 0x0FFF)) if (w >> 12) == 2 else 2
                if pos != len(data):
                    bad.append(os.path.basename(pf))
        if bad:
            return base, "FAIL", f"box stream overran in pieces: {','.join(bad)}"
        return base, "OK", f"re-parse clean ({nbox} box-stream piece(s))"


def main():
    targets = sys.argv[1:]
    if not targets:
        targets = sorted(os.path.basename(os.path.dirname(p))[4:]
                         for p in glob.glob(os.path.join(ROOT, "output/dlg_*/Track1.bin")))
    rows = [check(b) for b in targets]
    print("===== RE-PARSE INTEGRITY =====")
    for base, status, msg in rows:
        print(f"{status:5} {base:8} {msg}")
    fails = [b for b, s, _ in rows if s not in ("OK",)]
    print(f"\n{sum(1 for _,s,_ in rows if s=='OK')}/{len(rows)} clean")
    if fails:
        print("PROBLEMS:", ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
