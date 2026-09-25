#!/usr/bin/env python3
"""facer_banner.py — English re-author of the EXPRESSIONS-viewer BAKED banner art.

The expressions viewer (FACER subsystem) top-left banner キャラクター表情集 is a
144x41 8bpp VDP1 sprite (drawn by VDP1 command 49, texture @ VDP1 VRAM 0x3ec00,
colour mode 4 / CRAM bank 2). It is NOT tbl text: it lives in **/FIELD/FACE0.DAT
slot 3** (slot table @0x0: [0x10 pal, 0x210 art->VDP2, 0x9c60 desc, 0xb1e8 slot3]):

  file 0xb21a (slot3+0x32) : the bank-2 UI palette (~178 entries), used by the banner
  file 0xb54c (slot3+0x364): ONE compressed **plate-codec** stream (engine func
       0x0601A716, decode table baked @0x0601A9E4 -- the SAME field-sprite codec
       family as Lane K's MTOUT DESIGN-MATERIALS banner and the theater plates,
       decoder oracle src/theater/gfx_plate.py). It decodes a 6672 B blob to VDP1
       VRAM 0x3e900: [+0x000 three 16x16 nameplate-box sprites][+0x300 banner 144x41].
       The stream is the LAST data in the file (runs to EOF 0xcaec), so the on-disc
       budget for a re-encode is 0xcaec-0xb54c = 5536 B.

`build` decodes that blob with the real engine routine (gfx_plate, byte-exact),
erases the JP glyphs to the plate's per-row gold gradient, draws "EXPRESSIONS"
(Arial-Narrow-Bold, blue body idx 93 / dark-blue outline idx 116 -- matches the
vanilla blue-on-gold look and E810's terminal term ※※View Expressions※※), re-encodes
the whole blob with the optimal length-limited canonical Huffman from
tools/viewer_mtout_gfx.encode_block, VERIFIES the re-encode round-trips byte-exact
through gfx_plate, and splices it back at 0xb54c zero-padded to the vanilla 51948 B
(same LBA 38150 / 26 sectors, savestate-safe). Needs RAM images with the viewer
resident (work/pN2 dump: wram-{hi,lo}.bin, cram-final.bin) for the decoder/palette
oracles and PIL for the font.

`fold TRACK` is the RC build step: md5-gated, needs no oracle. It extracts the
on-disc FACE0.DAT, and if it is vanilla applies patches/viewer/FACE0.DAT.xdelta3 and
injects the English file IN PLACE (same size/sectors); already-English -> skip;
anything else -> hard error. Idempotent.

CLI:
  build  FACE0.DAT OUTDIR   [--hwram H --lwram L --cram C --banner TEXT]
  fold   TRACK1.bin
"""
import hashlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "theater"))

# ---- geometry / codec constants (all reverse-engineered, see module docstring) ----
BANNER_STREAM_OFF = 0xB54C      # file offset of the compressed plate stream
STREAM_COMP_LEN = 0x16AC        # generous len passed to the decoder (self-terminates)
BLOB_VRAM_BASE = 0x3E900        # VDP1 VRAM base the blob decodes to
BANNER_VRAM = 0x3EC00           # VDP1 VRAM addr of the banner sub-sprite
BANNER_IN_BLOB = BANNER_VRAM - BLOB_VRAM_BASE   # 0x300
BLOB_LEN = BANNER_IN_BLOB + 144 * 41            # 6672
FACE0_LWRAM = 0x2A0000          # where FACE0.DAT is resident (LWRAM)
W, H = 144, 41
FONT = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
BANNER_TEXT = "EXPRESSIONS"

VANILLA_MD5 = "d1614604eb4b82c2c0e6d371f4ef4f38"
ENGLISH_MD5 = "cbfd312840e412ec756bd4415fdd404e"
XDELTA = ROOT / "patches/viewer/FACE0.DAT.xdelta3"

HWRAM_DEF = ROOT / "work/pN2/dump/wram-hi.bin"
LWRAM_DEF = ROOT / "work/pN2/dump/wram-lo.bin"
CRAM_DEF = ROOT / "work/pN2/dump/cram-final.bin"


def _load_encode_block():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "vm", str(ROOT / "tools/viewer_mtout_gfx.py"))
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    return vm.encode_block


def _bank2_rgb(cram: bytes):
    def rgb(i):
        wv = struct.unpack_from(">H", cram, (512 + i) * 2)[0]
        return ((wv & 31) << 3, ((wv >> 5) & 31) << 3, ((wv >> 10) & 31) << 3)
    return [rgb(i) for i in range(256)]


def _decode_blob(face0: bytes, hwram: bytes, lwram: bytes) -> bytes:
    """Decode the plate stream to the 6672 B blob via the real engine routine."""
    import gfx_plate
    lw = bytearray(lwram)
    base = FACE0_LWRAM - 0x200000
    lw[base:base + len(face0)] = face0            # make FACE0 resident (== on disc)
    dec = gfx_plate.decode_plate(
        hwram, bytes(lw), FACE0_LWRAM + BANNER_STREAM_OFF, STREAM_COMP_LEN,
        BLOB_LEN, 1, dst_vram_off=BLOB_VRAM_BASE)
    return bytes(dec[:BLOB_LEN])


def _author_english_banner(blob: bytes, cram: bytes, text: str) -> bytes:
    """Return a new 144x41 banner (JP erased, `text` drawn) for the blob's +0x300 slot."""
    from collections import Counter
    from PIL import Image, ImageDraw, ImageFont
    RGB = _bank2_rgb(cram)
    ban = bytearray(blob[BANNER_IN_BLOB:BANNER_IN_BLOB + W * H])

    def isgold(i):
        r, g, b = RGB[i]
        return i != 0 and r >= b and r > 120

    # per-row plate fill sampled from the clean rounded-end columns
    rowfill = [0] * H
    for y in range(H):
        samp = [ban[y * W + x] for x in list(range(3, 10)) + list(range(134, 141))
                if isgold(ban[y * W + x])]
        if not samp:
            samp = [ban[y * W + x] for x in range(W) if isgold(ban[y * W + x])]
        rowfill[y] = Counter(samp).most_common(1)[0][0] if samp else 0
    # rebuild the interior band -> clean plate (erases blue strokes + pale AA halo)
    out = bytearray(ban)
    for y in range(3, 38):
        f = rowfill[y]
        if not f:
            continue
        for x in range(6, 138):
            if ban[y * W + x] != 0:                # keep the magenta rounded corners
                out[y * W + x] = f

    BODY = 93                                      # bright blue (96,96,232)
    OUT = min(range(256), key=lambda i: sum(
        (a - b) ** 2 for a, b in zip(RGB[i], (16, 0, 80))))   # dark-blue outline
    # fit the font to the plate window (<=126 px wide, <=23 px cap height)
    fit = None
    for size in range(40, 10, -1):
        fnt = ImageFont.truetype(FONT, size)
        bb = ImageDraw.Draw(Image.new("L", (320, 80))).textbbox((0, 0), text, font=fnt)
        if bb[2] - bb[0] <= 126 and bb[3] - bb[1] <= 23:
            fit = (fnt, bb); break
    fnt, bb = fit
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).text(((W - tw) // 2 - bb[0], (H - th) // 2 - bb[1] - 1),
                             text, fill=255, font=fnt)
    px = img.load()
    m = [[px[x, y] >= 128 for x in range(W)] for y in range(H)]
    for y in range(H):                             # 1px dark outline
        for x in range(W):
            if m[y][x]:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < W and not m[yy][xx]:
                            out[yy * W + xx] = OUT
    for y in range(H):                             # blue body
        for x in range(W):
            if m[y][x]:
                out[y * W + x] = BODY
    return bytes(out)


def cmd_build(face0_path, outdir, hwram=None, lwram=None, cram=None, banner=None):
    import gfx_plate
    encode_block = _load_encode_block()
    face0 = bytearray(Path(face0_path).read_bytes())
    if hashlib.md5(bytes(face0)).hexdigest() != VANILLA_MD5:
        print("WARNING: input FACE0.DAT is not the known vanilla md5")
    hw = Path(hwram or HWRAM_DEF).read_bytes()
    lw = Path(lwram or LWRAM_DEF).read_bytes()
    cr = Path(cram or CRAM_DEF).read_bytes()
    banner = banner or BANNER_TEXT

    blob = _decode_blob(bytes(face0), hw, lw)
    eng_banner = _author_english_banner(blob, cr, banner)
    new_blob = bytearray(blob)
    new_blob[BANNER_IN_BLOB:BANNER_IN_BLOB + W * H] = eng_banner

    stream = encode_block(bytes(new_blob))
    budget = len(face0) - BANNER_STREAM_OFF
    if len(stream) > budget:
        raise SystemExit(f"re-encoded stream {len(stream)} B > on-disc budget {budget} B")

    # splice in place + zero-pad to vanilla size
    face0[BANNER_STREAM_OFF:BANNER_STREAM_OFF + len(stream)] = stream
    for i in range(BANNER_STREAM_OFF + len(stream), len(face0)):
        face0[i] = 0

    # round-trip verify through the REAL engine decoder
    rt = _decode_blob(bytes(face0), hw, lw)
    if rt != new_blob:
        bad = next(i for i in range(len(rt)) if rt[i] != new_blob[i])
        raise SystemExit(f"round-trip mismatch at blob +{bad:#x}")

    Path(outdir).mkdir(parents=True, exist_ok=True)
    out = Path(outdir) / "FACE0.DAT"
    out.write_bytes(bytes(face0))
    print(f"OK: banner '{banner}' stream {len(stream)} B (fits {budget}), "
          f"round-trip byte-exact, md5 {hashlib.md5(bytes(face0)).hexdigest()} -> {out}")


def _read_file(f, rec):
    import iso
    out = bytearray()
    for s in range((rec["size"] + iso.USER_DATA - 1) // iso.USER_DATA):
        f.seek(iso.raw_offset(rec["lba"] + s))
        out += f.read(iso.USER_DATA)
    return bytes(out[:rec["size"]])


def _inject(track, rec, data):
    import iso
    if len(data) != rec["size"]:
        raise SystemExit(f"size {len(data)} != on-disc {rec['size']} (must be in-place)")
    with open(track, "r+b") as f:
        for i in range((len(data) + iso.USER_DATA - 1) // iso.USER_DATA):
            chunk = data[i * iso.USER_DATA:(i + 1) * iso.USER_DATA]
            chunk = chunk + b"\x00" * (iso.USER_DATA - len(chunk))
            f.seek(iso.raw_offset(rec["lba"] + i))
            f.write(chunk)


def cmd_fold(track):
    """RC step (idempotent, md5-gated, no oracle): apply the English FACE0.DAT banner."""
    import iso
    with open(track, "rb") as f:
        rec = iso.find_record(f, "FACE0.DAT")
        if not rec:
            raise SystemExit("FACE0.DAT not found in track")
        cur = _read_file(f, rec)
    md5 = hashlib.md5(cur).hexdigest()
    if md5 == ENGLISH_MD5:
        print(f"FACE0.DAT already English ({md5}); skip"); return
    if md5 != VANILLA_MD5:
        raise SystemExit(f"FACE0.DAT md5 {md5} is neither vanilla nor English -- refusing")
    with tempfile.TemporaryDirectory() as td:
        van = Path(td) / "van.DAT"
        eng = Path(td) / "eng.DAT"
        van.write_bytes(cur)
        subprocess.run(["xdelta3", "-d", "-f", "-s", str(van), str(XDELTA), str(eng)],
                       check=True)
        out = eng.read_bytes()
        if hashlib.md5(out).hexdigest() != ENGLISH_MD5:
            raise SystemExit("xdelta produced unexpected FACE0.DAT md5")
        _inject(track, rec, out)
    print(f"expressions banner folded -> EXPRESSIONS ({track})")


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 1
    cmd = argv[1]
    if cmd == "build":
        kw = {}
        rest = argv[4:]
        it = iter(rest)
        for a in it:
            if a == "--hwram": kw["hwram"] = next(it)
            elif a == "--lwram": kw["lwram"] = next(it)
            elif a == "--cram": kw["cram"] = next(it)
            elif a == "--banner": kw["banner"] = next(it)
        cmd_build(argv[2], argv[3], **kw)
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
