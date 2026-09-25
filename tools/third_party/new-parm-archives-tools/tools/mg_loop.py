#!/usr/bin/env python3
"""mg_loop.py — one autonomous iteration of the minigame-UI translation loop.

Separate from tools/jinloop.py (which is wired to build_mdt + the Jin savestate).
This drives the minigame-engine RE/translation loop: build an English menu/logo
bitmap -> load it -> screenshot -> the agent reads the PNG to judge success.

Two modes:

  --mode vram   (default, WORKS today): patch the 8bpp sprite bitmap directly into
                VDP1 VRAM in savestate 4 (assets resident) via the harness
                --inject-vram1 flag, boot, and screenshot the menu. Proves the
                English ART renders (palette/place/transparency). NOT a disc proof.

  --mode disc   (STUB — needs the codec): patch the on-disc compressed asset,
                inject into a fresh disc copy with src/inject.py, boot savestate 5,
                script terminal->Start-Game->menu, screenshot. Blocked until the
                minigame graphics compression codec is reversed (see
                docs/mgame-format.md). Left here so the pipeline is ready.

Savestates live under the disc-hash dir <minigame-disc-hash> (NOT the
jinloop default A2883C55…). 4 = inside the deck-swab menu; 5 = at the terminal.

Examples:
  tools/mg_loop.py --attempt 01 --text START,RANK,QUIT
  tools/mg_loop.py --attempt 02 --block work/mgame/poc/menu_block.bin --addr 0x27400
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tools/ymir-harness/build/jinloop-harness"
MG_TEXT = ROOT / "tools/mg_text.py"
WORK = ROOT / "work/mgame/loop"

# Set GDM_BIOS / GDM_MG_STATEDIR for your machine; the defaults below are placeholders.
BIOS = os.environ.get(
    "GDM_BIOS",
    "/path/to/Ymir/build/apps/ymir-sdl3/ymir-sdl3.app/"
    "Contents/MacOS/roms/ipl/Sega Saturn BIOS v1.01 (JAP).bin",
)
SS_DIR = os.environ.get(
    "GDM_MG_STATEDIR",
    "/path/to/Ymir/savestates/<minigame-disc-hash>",
)
CUE = os.environ.get(
    "GDM_MG_DISC",
    str(ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M).cue"),
)
# VDP1 VRAM addresses of the three shared menu items (deck-swab, save 4).
MENU_ADDRS = [0x27400, 0x28400, 0x29400]


def build_block(texts, out: Path):
    """Render N labels into one contiguous 8bpp 128x32 block (4096 B each)."""
    parts = []
    for i, t in enumerate(texts):
        p = out.parent / f"item_{i}.bin"
        subprocess.run([sys.executable, str(MG_TEXT), t, str(p),
                        "--val", "6", "--hi", "16", "--scale", "3",
                        "--x", "8", "--y", "5"], check=True)
        parts.append(p.read_bytes())
    out.write_bytes(b"".join(parts))
    return out


def run_vram(attempt, block: Path, addr: int):
    wdir = WORK / attempt
    wdir.mkdir(parents=True, exist_ok=True)
    script = wdir / "idle.json"
    script.write_text(json.dumps([{"frames": 120, "buttons": ""}]))
    cmd = [
        str(HARNESS),
        "--bios", BIOS,
        "--disc", CUE,
        "--state", f"{SS_DIR}/4.savestate",
        "--out", str(wdir / "report.json"),
        "--script", str(script),
        "--inject-vram1", str(block),
        "--inject-vram1-addr", hex(addr),
        "--png-dir", str(wdir),
        "--png-every", "60",
    ]
    print("RUN:", " ".join(cmd))
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL)
    if r.returncode != 0:
        print("HARNESS FAILED", file=sys.stderr)
        return 1
    print(f"\nOK attempt {attempt}: read {wdir}/frame_final.png and confirm English renders.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt", required=True)
    ap.add_argument("--mode", choices=["vram", "disc"], default="vram")
    ap.add_argument("--text", help="comma list of labels, e.g. START,RANK,QUIT")
    ap.add_argument("--block", help="prebuilt 8bpp bitmap block to inject")
    ap.add_argument("--addr", default=hex(MENU_ADDRS[0]),
                    help="VDP1 VRAM addr for --block (default first menu item)")
    a = ap.parse_args()

    if a.mode == "disc":
        print("mode=disc is a STUB: blocked on the minigame graphics compression codec.\n"
              "See docs/mgame-format.md (Open blocker). Use --mode vram for the render proof.",
              file=sys.stderr)
        return 2

    wdir = WORK / a.attempt
    wdir.mkdir(parents=True, exist_ok=True)
    if a.block:
        block = Path(a.block)
    elif a.text:
        block = build_block(a.text.split(","), wdir / "menu_block.bin")
    else:
        print("need --text or --block", file=sys.stderr)
        return 2
    return run_vram(a.attempt, block, int(a.addr, 0))


if __name__ == "__main__":
    raise SystemExit(main())
