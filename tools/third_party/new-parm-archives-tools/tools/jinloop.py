#!/usr/bin/env python3
"""jinloop.py — one autonomous iteration of the Jin-conversation loop.

inject (build_mdt.py) -> run (headless YMIR harness from the savestate, drive C to
advance the convo) -> inspect (filmstrip PNGs + report.json). The agent reads the
PNGs to judge success; this script just wires the steps and records artifacts.

Usage:
  tools/jinloop.py --attempt 062 -- --paginate --align-scn --wrap 30 \
      --seg 500a:0,500a:2,500a:4,500a:5,500a:7,500a:8,500a:9 \
      --skip-pieces 0,3,4,5,6,9,a,e000 E80C

Everything after `--` is passed verbatim to src/build_mdt.py (minus --attempt,
which we inject). Use --no-build to re-run the harness on an existing output/<attempt>.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tools/ymir-harness/build/jinloop-harness"
WORK = ROOT / "work/jinloop"

# Set GDM_BIOS / GDM_STATE for your machine; the defaults below are placeholders.
BIOS = os.environ.get(
    "GDM_BIOS",
    "/path/to/Ymir/build/apps/ymir-sdl3/ymir-sdl3.app/"
    "Contents/MacOS/roms/ipl/Sega Saturn BIOS v1.01 (JAP).bin",
)
STATE = os.environ.get(
    "GDM_STATE",
    "/path/to/Ymir/savestates/<disc-hash>/0.savestate",
)


def make_convo_script(path: Path, cycles: int = 34, press: int = 6, gap: int = 40):
    """Idle, then press C `cycles` times to advance each dialogue box."""
    steps = [{"frames": 40, "buttons": ""}]
    for _ in range(cycles):
        steps.append({"frames": press, "buttons": "C"})
        steps.append({"frames": gap, "buttons": ""})
    path.write_text(json.dumps(steps))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt", required=True)
    ap.add_argument("--no-build", action="store_true", help="skip build_mdt; run harness only")
    ap.add_argument("--cycles", type=int, default=34)
    ap.add_argument("--png-every", type=int, default=23)
    ap.add_argument("build_args", nargs=argparse.REMAINDER,
                    help="args after `--` forwarded to src/build_mdt.py")
    a = ap.parse_args()

    attempt = a.attempt
    outdir = ROOT / f"output/{attempt}"
    cue = outdir / "Grandia-DM-patched.cue"
    wdir = WORK / attempt
    wdir.mkdir(parents=True, exist_ok=True)

    # 1) inject / build
    if not a.no_build:
        ba = a.build_args
        if ba and ba[0] == "--":
            ba = ba[1:]
        cmd = [sys.executable, str(ROOT / "src/build_mdt.py"), "--attempt", attempt] + ba
        print("BUILD:", " ".join(cmd))
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            print("BUILD FAILED", file=sys.stderr)
            return 1
    if not cue.exists():
        print(f"ERROR: {cue} not found", file=sys.stderr)
        return 1

    # 2) run + 3) inspect
    script = wdir / "convo_script.json"
    make_convo_script(script, cycles=a.cycles)
    pngdir = wdir / "frames"
    if pngdir.exists():
        for p in pngdir.glob("*.png"):
            p.unlink()
    pngdir.mkdir(exist_ok=True)
    report = wdir / "report.json"

    cmd = [
        str(HARNESS),
        "--bios", BIOS,
        "--disc", str(cue),
        "--state", STATE,
        "--out", str(report),
        "--script", str(script),
        "--png-dir", str(pngdir),
        "--png-every", str(a.png_every),
    ]
    print("RUN:", " ".join(cmd))
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL)
    if r.returncode != 0:
        print("HARNESS FAILED", file=sys.stderr)
        return 1

    nframes = len(list(pngdir.glob("*.png")))
    print(f"\nOK attempt {attempt}: {nframes} frames -> {pngdir}")
    print(f"report: {report}")
    print("Inspect: read the 'fully-printed' frame of each box (offset ~+40 in each 46-frame cycle).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
