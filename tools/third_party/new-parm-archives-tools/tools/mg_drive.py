#!/usr/bin/env python3
"""mg_drive.py — thin harness driver for the minigame in-game sweep.

Boots a registered savestate against a (optionally patched) disc, runs an
explicit per-frame button plan, dumps PNGs, and (optionally) breakpoints/
watchpoints + dump-on-bp. Keeps all the path boilerplate in one place.

Plan syntax: a compact CSV of `frames:buttons` steps, e.g.
  "30:,8:C,90:,8:Down,8:C,260:"
(empty buttons = idle). Buttons are YMIR names: C, Up, Down, Left, Right, A, B, Start.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tools/ymir-harness/build/jinloop-harness"
BIOS = os.environ.get("GDM_BIOS",  # set GDM_BIOS for your machine; placeholder default
    "/path/to/Ymir/build/apps/ymir-sdl3/ymir-sdl3.app/"
    "Contents/MacOS/roms/ipl/Sega Saturn BIOS v1.01 (JAP).bin")
DEF_CUE = str(ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M).cue")


def save_path(slug):
    return subprocess.check_output(
        [sys.executable, str(ROOT / "tools/save_register.py"), "path", slug]).decode().strip()


def build_plan(spec):
    # Steps separated by ';'. Each step "frames:buttons"; buttons may be a
    # '+'-joined combo (e.g. "Up+Left") -> emitted as YMIR CSV "Up,Left".
    plan = []
    for step in spec.split(";"):
        step = step.strip()
        if not step:
            continue
        n, _, b = step.partition(":")
        b = b.replace("+", ",")
        plan.append({"frames": int(n), "buttons": b})
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True, help="save slug")
    ap.add_argument("--disc", default=DEF_CUE)
    ap.add_argument("--plan", required=True, help="CSV frames:buttons steps")
    ap.add_argument("--dir", required=True, help="output dir")
    ap.add_argument("--png-every", type=int, default=15)
    ap.add_argument("--bp", action="append", default=[])
    ap.add_argument("--watchr", action="append", default=[])
    ap.add_argument("--watch", action="append", default=[])
    ap.add_argument("--dump-on-bp", default="")
    ap.add_argument("--dump-bp-hit", type=int, default=1)
    ap.add_argument("--dump-wram", default="")
    ap.add_argument("--inject", default="")      # file
    ap.add_argument("--inject-addr", default="")
    ap.add_argument("--debug-slave", action="store_true",
                    help="also arm bp/watchpoints on the slave SH-2")
    ap.add_argument("--save-state-out", default="")
    args = ap.parse_args()

    outdir = Path(args.dir)
    outdir.mkdir(parents=True, exist_ok=True)
    plan_path = outdir / "plan.json"
    plan_path.write_text(json.dumps(build_plan(args.plan)))

    S = save_path(args.state)
    cmd = [str(HARNESS), "--bios", BIOS, "--disc", args.disc, "--state", S,
           "--out", str(outdir / "report.json"),
           "--script", str(plan_path),
           "--png-dir", str(outdir), "--png-every", str(args.png_every)]
    for b in args.bp: cmd += ["--bp", b]
    for w in args.watchr: cmd += ["--watchr", w]
    for w in args.watch: cmd += ["--watch", w]
    if args.dump_on_bp:
        cmd += ["--dump-on-bp", args.dump_on_bp, "--dump-bp-hit", str(args.dump_bp_hit)]
    if args.dump_wram:
        cmd += ["--dump-wram", args.dump_wram]
    if args.inject and args.inject_addr:
        cmd += ["--inject-scn", args.inject, "--inject-addr", args.inject_addr]
    if args.debug_slave:
        cmd += ["--debug-slave"]
    if args.save_state_out:
        cmd += ["--save-state-out", args.save_state_out]
    r = subprocess.run(cmd, stderr=subprocess.PIPE)
    err = r.stderr.decode()
    for line in err.splitlines():
        if "CDBlock" in line or "Filter 14" in line:
            continue
        print(line, file=sys.stderr)
    print("RC", r.returncode)


if __name__ == "__main__":
    main()
