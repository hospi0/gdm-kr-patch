#!/usr/bin/env python3
"""Build visual proof of an e2e harness run: an animated GIF + a contact-sheet grid.

Usage: make_proof.py <frames_dir> <out_prefix> [--cols N] [--tiles K] [--fps F] [--scale S]
Frames are the harness PNGs (frame_XXXXX.png). Output: <out_prefix>.gif and <out_prefix>_sheet.png
"""
import sys
import argparse
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("out_prefix")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--tiles", type=int, default=12)
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--gif-step", type=int, default=2, help="use every Nth frame in the GIF")
    a = ap.parse_args()

    files = sorted(Path(a.frames_dir).glob("frame_*.png"))
    files = [f for f in files if "final" not in f.name]
    if not files:
        print("no frames", file=sys.stderr); return 1

    # GIF (downscaled, every gif-step frame)
    gif_frames = []
    for f in files[:: a.gif_step]:
        im = Image.open(f).convert("RGB")
        if a.scale != 1.0:
            im = im.resize((int(im.width * a.scale), int(im.height * a.scale)))
        gif_frames.append(im)
    if gif_frames:
        gif_frames[0].save(f"{a.out_prefix}.gif", save_all=True, append_images=gif_frames[1:],
                           duration=int(1000 / a.fps), loop=0, optimize=True)
        print(f"wrote {a.out_prefix}.gif ({len(gif_frames)} frames)")

    # Contact sheet: evenly spaced tiles, labeled with frame number
    idxs = [round(i * (len(files) - 1) / (a.tiles - 1)) for i in range(a.tiles)]
    tiles = []
    for i in idxs:
        im = Image.open(files[i]).convert("RGB")
        tiles.append((files[i].stem.replace("frame_", "f"), im))
    tw = int(tiles[0][1].width * a.scale)
    th = int(tiles[0][1].height * a.scale)
    pad, lbl = 6, 16
    rows = (len(tiles) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (a.cols * (tw + pad) + pad, rows * (th + lbl + pad) + pad), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for k, (name, im) in enumerate(tiles):
        r, c = divmod(k, a.cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + lbl + pad)
        d.text((x, y), name, fill=(220, 220, 220))
        sheet.paste(im.resize((tw, th)), (x, y + lbl))
    sheet.save(f"{a.out_prefix}_sheet.png")
    print(f"wrote {a.out_prefix}_sheet.png ({len(tiles)} tiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
