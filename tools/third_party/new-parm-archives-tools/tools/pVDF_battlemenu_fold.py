#!/usr/bin/env python3
"""pVDF_battlemenu_fold.py — English re-author of the in-battle SUBMENU labels that render
through the VDP2 TILE-FONT (NOT the VDP1 chrome sprite atlas of lane pO4/pO4b).

LANE pVDF (VDP2 battle-menu labels). Prefix pVDF_. Owner: EXECUTOR sub-agent.

SUBSYSTEM (confirmed this lane, oracle + trace)
-----------------------------------------------
Each in-battle submenu, on OPEN, fires the SAME resident decompressor at HWRAM 0x0601A716
(the pO4 chrome codec) but writes to **VDP2 VRAM 0x25E03400** (a per-submenu work region),
NOT the VDP1 sprite atlas 0x25C4xxxx. So these submenu labels are VDP2 NBG 8x8 tiles placed
by a pattern-name table, and their glyph atlas is a compressed disc blob decoded via
tools/pO4_chrome_codec.py (dst-base 0x3400). Confirmed per label:

  * SKILL submenu header  しゅうとくスキル (Acquired Skill)  -> blob disc 0xEB0674
      trace: --bp 0x0601A716 from state user-battle-ring-magic-rc33 + C -> r4=0x25E03400,
      r5(src)=0x060CC6A4; the HWRAM source bytes are VERBATIM on disc at raw 0xEB0674.
      decode(0xEB0674, dst 0x3400) writes VDP2 [0x3400,0x3780) (28 tiles); the label is 8
      dedicated 8x8 cells char# 0x1b1..0x1b8 (VRAM 0x3620..0x3720), EXCLUSIVE to this label
      (marker-inject regression test: only the header changed, description/list intact).
      All 8 cells decode BIT-EXACT vs live VDP2 dump (state user-battle-skillmenu-jp-rc25).

The DECODE region 0x3400 is shared/transient across submenus (Strategy 0xEBB644, Item
0xEB8DA4, Defend 0xEBD830 all decode their own blob there — see pO4b), so each blob is
patched independently and only the label cells inside it are touched.

WHAT THIS TOOL DOES (size-preserving, md5/byte-gated, idempotent — models pO4b_chrome_labels_fold)
  - decode the on-disc blob via pO4_chrome_codec,
  - author English into the label's dedicated 8x8 cells (chunky 5x7 font, matching ink),
  - re-encode the decoded window via pO4_chrome_encode.encode (verified inverse),
  - write_logical() the stream back at the blob's disc offset (padded to the on-disc budget),
  - round-trip self-check (ROM-decode the written stream == the authored window).

Subcommands:
  atlas  OUT.bin [--text T]   -> full 0x80000 VDP2 image w/ English cells (for --inject-vram2 @0x0)
  fold   TRACK1.bin           -> patch the disc blob in place (build step)
  preview OUT.png             -> QA sheet of the authored cells
  md5                          -> md5 of the authored cells (determinism gate)
"""
from __future__ import annotations
import argparse, os, sys, hashlib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import pO4_chrome_codec as codec
import pO4_chrome_encode as enc
# reuse the shipped chunky 5x7 font + cell packer from the ENDW tile-font lane
import battle_skillgain_gfx as tf  # _fit, _pack_cell, _cells_1row

CELL = 0x20

# ---- per-label descriptor -------------------------------------------------------------------
# each: disc blob offset, VDP2 dst-base, decode window [lo,hi), cell char# list, English, ink,
#       and the on-disc stream footprint budget (bytes; next-blob gap).
# NOTE two authoring modes:
#   * "text"   -> tf._cells_1row proportionally renders ONE screen line across the (contiguous)
#                 cells. Correct only when the cells form a single left-to-right run on screen
#                 (skill_header: しゅうとくスキル == one 8-cell line).
#   * "glyphs" -> per-cell {char#: single-char} authoring. Required when the label's cells are
#                 SPLIT across the tilemap (multiple screen rows and/or SHARED cells), so a
#                 proportional whole-string render would not line up. strategy_rows uses this:
#                 the two red row labels 個人作戦 / 全体作戦 share the 作戦 glyph tiles (a dedup
#                 pool referenced by the VDP2 pattern-name table at VRAM ~0xe462, palette bank 5
#                 = red), so 個人/全体 get their own cells and 作戦 is authored ONCE for both rows.
LABELS = {
    "skill_header": dict(
        src_off=0xEB0674, dst_base=0x3400, win_lo=0x3400, win_hi=0x3780,
        cells=[0x1b2, 0x1b3, 0x1b4, 0x1b5, 0x1b6, 0x1b7, 0x1b8, 0x1b9],
        text="Acquired", ink=15, budget=0x900,
        jp="しゅうとくスキル", note="Acquired Skill (習得スキル) header over the skill-mastery box",
    ),
    # Strategy submenu RED row labels (blob disc 0xEBB644 -> VDP2 0x3400). The tilemap
    # (VDP2 VRAM ~0xe462, pal-bank 5) lays each label as [distinguishing 2 kanji | 作戦 | :]
    # over 2 cell-rows.  CANONICAL Grandia English (reference: the live G1 battle STRATEGY
    # screen, which DM's engine reuses): 個人作戦 -> "Single", 全体作戦 -> "Party" -- the 作戦
    # ("Tactics") word is DROPPED on the row labels, matching G1.  Each word is rendered
    # proportionally (5x7 font) across its OWN 4 scope cells -- "Single" (~35px) squishes ~9%
    # into the 32px slot, "Party" fits natively -- so NO tilemap repoint / un-share is needed.
    # The SHARED 作戦 cells (0x1a7-0x1aa top, 0x1af-0x1b2 bot) and both bottom cell-rows are
    # BLANKED so no JP kanji tail remains.  Colon cells 0x1a1/0x1a2 left as JP.
    # (The three TOP buttons 作戦設定/個人作戦実行/全体作戦実行 = "Tactics"/"Single Tactics"/
    # "Party Tactics" are a SEPARATE VDP1-sprite source, NOT this blob -> deferred, see doc.)
    "strategy_rows": dict(
        src_off=0xEBB644, dst_base=0x3400, win_lo=0x3400, win_hi=0x3980,
        ink=15, budget=0x2000,
        cells=[0x1a3, 0x1a4, 0x1a5, 0x1a6, 0x1b3, 0x1b4, 0x1b5, 0x1b6,
               0x1a7, 0x1a8, 0x1a9, 0x1aa, 0x1ab, 0x1ac, 0x1ad, 0x1ae,
               0x1af, 0x1b0, 0x1b1, 0x1b2, 0x1b7, 0x1b8, 0x1b9, 0x1ba],
        runs=[("Single", [0x1a3, 0x1a4, 0x1a5, 0x1a6]),   # 個人作戦 -> Single (own 4 cells)
              ("Party",  [0x1b3, 0x1b4, 0x1b5, 0x1b6])],  # 全体作戦 -> Party  (own 4 cells)
        blank=[0x1a7, 0x1a8, 0x1a9, 0x1aa,   # shared 作戦 top -> blank
               0x1ab, 0x1ac, 0x1ad, 0x1ae,   # 個人 bottom cell-row
               0x1af, 0x1b0, 0x1b1, 0x1b2,   # shared 作戦 bottom
               0x1b7, 0x1b8, 0x1b9, 0x1ba],  # 全体 bottom cell-row
        text="Single / Party",
        jp="個人作戦 / 全体作戦", note="strategy submenu red row labels -> Single / Party (G1 canon)",
    ),
}
DEFAULT = "skill_header"


def author_cells(name=DEFAULT, text=None):
    """Return {char#: 32B cell} authoring English into the label's dedicated 8x8 cells.
    Three modes (see LABELS note): a 'runs' list of (text, cells) proportional renders +
    a 'blank' cell list; a per-cell 'glyphs' map; or a single proportional 'text' line."""
    d = LABELS[name]
    if "runs" in d and text is None:
        out = {}
        for run_text, run_cells in d["runs"]:
            out.update(tf._cells_1row(run_text, run_cells, d["ink"]))
        for ch in d.get("blank", []):
            out[ch] = tf._cells_1row(' ', [ch], d["ink"])[ch]
        return out
    if "glyphs" in d and text is None:
        out = {}
        for ch, g in d["glyphs"].items():
            out[ch] = tf._cells_1row(g, [ch], d["ink"])[ch]
        return out
    txt = text if text is not None else d["text"]
    return tf._cells_1row(txt, d["cells"], d["ink"])


def patched_window(disc: bytes, name=DEFAULT, text=None) -> bytearray:
    """Decode the blob, overwrite the label cells with English, return the VRAM image."""
    d = LABELS[name]
    vram = bytearray(codec.run_decode(disc, d["src_off"], d["dst_base"], 0x1000))
    for ch, cell in author_cells(name, text).items():
        vram[ch * CELL: ch * CELL + CELL] = cell
    return vram


# ---------------------------------------------------------------------------------------------
# Custom Huffman codelen9. The on-disc blob's tree is a COMPLETE (Kraft=1) but SPARSE canonical
# code built only from the ORIGINAL glyphs' delta-symbol set. Authoring English introduces
# literal delta-symbols the original tree lacks (KeyError). Because the ROM decompressor reads
# the 9-byte code-length table FROM THE STREAM (encode() embeds it), we can widen the tree: emit
# a fresh optimal length-limited Huffman codelen over exactly the symbols our authored window
# needs. encode() calls build_tree() (the ROM LUT-builder) on whatever codelen we pass, so the
# emitted codes and the on-hardware decode stay consistent by construction.
# ---------------------------------------------------------------------------------------------
def _literal_symbol_freq(pixels, zthresh=6):
    """Mirror encode()'s tokenizer to count literal Huffman symbols (0..15) + escape (16)."""
    nib = []
    for byte in pixels:
        nib.append((byte >> 4) & 0xF); nib.append(byte & 0xF)
    N = len(nib); i = 0; prev_px = 0
    freq = [0] * 17
    while i < N:
        z = 0
        while i < N and nib[i] == 0:
            z += 1; i += 1
        if z and z < zthresh and i < N:
            i -= z; z = 0
        lit_nibs = []
        while i < N:
            if nib[i] == 0:
                k = i
                while k < N and nib[k] == 0:
                    k += 1
                if (k - i) >= zthresh:
                    break
            lit_nibs.append(nib[i]); i += 1
        for P in lit_nibs:
            freq[(prev_px - P) & 0xF] += 1
            prev_px = P
        freq[16] += 1  # escape terminates every literal run
    return freq


def _huffman_lengths(freq, maxlen=8):
    """LENGTH-LIMITED optimal code lengths (package-merge, Larmore-Hirschberg) capped at
    `maxlen` bits — the ROM decode LUT is an 8-bit prefix table, so no code may exceed 8 bits.
    Returns list[18] of nibble lengths (idx 0..15 symbols, 16 escape, 17 pad=0)."""
    used = [(f, s) for s, f in enumerate(freq) if f > 0]
    if not used:
        return [0] * 18
    if len(used) == 1:
        lengths = [0] * 18; lengths[used[0][1]] = 1; return lengths
    n = len(used)
    if (1 << maxlen) < n:
        raise SystemExit(f"{n} symbols cannot fit in {maxlen}-bit codes")
    orig = sorted((f, [s]) for f, s in used)     # coin = (weight, [symbols])
    packages = []
    for _ in range(maxlen - 1):                   # L-1 package rounds -> max code length L
        pool = sorted(orig + packages)
        packages = []
        for i in range(0, len(pool) - 1, 2):
            packages.append((pool[i][0] + pool[i + 1][0], pool[i][1] + pool[i + 1][1]))
    final = sorted(orig + packages)[: 2 * n - 2]
    lengths = [0] * 18
    for _w, syms in final:
        for s in syms:
            lengths[s] += 1
    return lengths


def _codelen9_for_window(pixels, zthresh=6):
    freq = _literal_symbol_freq(pixels, zthresh)
    lengths = _huffman_lengths(freq)
    b = bytearray(9)
    for i in range(18):
        if i % 2 == 0:
            b[i // 2] = (lengths[i] << 4) | (b[i // 2] & 0x0F)
        else:
            b[i // 2] = (b[i // 2] & 0xF0) | (lengths[i] & 0xF)
    return bytes(b)


def build_stream(disc: bytes, name=DEFAULT, text=None):
    d = LABELS[name]
    vram = patched_window(disc, name, text)
    pixels = bytes(vram[d["win_lo"]:d["win_hi"]])
    # try the on-disc tree first (smallest stream); widen to a custom tree if it lacks a symbol.
    orig_cl, _ = enc._codelen9_from_disc_bytes(disc, d["src_off"])
    for codelen9 in (orig_cl, _codelen9_for_window(pixels)):
        try:
            stream = enc.encode(pixels, codelen9, zthresh=6)
            return stream, vram
        except KeyError:
            continue
    raise SystemExit(f"{name}: could not encode window with any tree")


# de-sectored write (identical to pO4b_chrome_labels_fold.write_logical)
RAW_SECTOR, SYNC_HEADER, USER_DATA = 2352, 16, 2048
def write_logical(disc, raw_off, data):
    o, p = raw_off, 0
    while p < len(data):
        sec = o // RAW_SECTOR
        ino = max(o % RAW_SECTOR, SYNC_HEADER)
        data_end = sec * RAW_SECTOR + SYNC_HEADER + USER_DATA
        n = min(data_end - (sec * RAW_SECTOR + ino), len(data) - p)
        disc[sec * RAW_SECTOR + ino: sec * RAW_SECTOR + ino + n] = data[p:p + n]
        p += n
        o = (sec + 1) * RAW_SECTOR + SYNC_HEADER


def cmd_atlas(a):
    """Emit ONLY the label's authored cells (contiguous) for a TARGETED --inject-vram2 at the
    first cell's VRAM address — this validates the label without zeroing surrounding VRAM."""
    d = LABELS[a.name]
    cells = author_cells(a.name, a.text)
    addr = d["cells"][0] * CELL
    blob = b"".join(cells[c] for c in d["cells"])
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "wb").write(blob)
    print(f"authored {len(d['cells'])} cells ({a.name}: '{a.text or d['text']}') -> {a.out} "
          f"({len(blob)} B). Validate: --inject-vram2 {a.out} --inject-vram2-addr {addr:#x}")


def cmd_fold(a):
    track = a.track
    disc = bytearray(open(track, "rb").read())
    changed = False
    for name in (LABELS if a.name == "all" else [a.name]):
        d = LABELS[name]
        cur = bytearray(codec.run_decode(bytes(disc), d["src_off"], d["dst_base"], 0x1000))
        tgt = bytearray(cur)
        for ch, cell in author_cells(name).items():
            tgt[ch * CELL: ch * CELL + CELL] = cell
        if bytes(cur[d["win_lo"]:d["win_hi"]]) == bytes(tgt[d["win_lo"]:d["win_hi"]]):
            print(f"{name}: already English -> skip"); continue
        stream, vram = build_stream(bytes(disc), name)
        # The ROM decoder stops at this stream's own END control token, so a SHORTER English
        # stream is written UNPADDED — we overwrite only its bytes and never clobber the data
        # that follows the original (longer) stream in the file. `budget` is a sanity ceiling
        # (must stay below the next co-located structure at logical ~0xa40).
        if len(stream) > d["budget"]:
            raise SystemExit(f"{name}: stream {len(stream)} B > budget {d['budget']} B")
        write_logical(disc, d["src_off"], stream)
        chk = codec.run_decode(bytes(disc), d["src_off"], d["dst_base"], 0x1000)
        ok = bytes(chk[d["win_lo"]:d["win_hi"]]) == bytes(vram[d["win_lo"]:d["win_hi"]])
        print(f"{name}: {d['jp']} -> '{d['text']}'  round-trip={'OK' if ok else 'MISMATCH'} "
              f"(stream {len(stream)} B unpadded, ceiling {d['budget']})")
        if not ok:
            raise SystemExit("round-trip mismatch — refusing to write a bad blob")
        changed = True
    if changed:
        open(track, "wb").write(bytes(disc))
        print(f"wrote -> {track}")


def cmd_md5(a):
    cells = author_cells(a.name)
    h = hashlib.md5(b"".join(cells[c] for c in sorted(cells))).hexdigest()
    print(h)


def cmd_preview(a):
    from PIL import Image
    cells = author_cells(a.name, a.text)
    scale = 12
    ids = sorted(cells)
    img = Image.new("RGB", (len(ids) * 8 * scale, 8 * scale), (20, 20, 50))
    pal = {1: (210, 210, 230)}
    for i, ch in enumerate(ids):
        cell = cells[ch]
        for y in range(8):
            for x in range(0, 8, 2):
                b = cell[y * 4 + x // 2]
                for j, pv in enumerate((b >> 4, b & 0xf)):
                    col = (10, 10, 40) if pv == 0 else pal.get(pv, (255, 0, 255))
                    for sy in range(scale):
                        for sx in range(scale):
                            img.putpixel((i * 8 * scale + (x + j) * scale + sx, y * scale + sy), col)
    img.save(a.out); print("saved", a.out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("atlas"); pa.add_argument("out"); pa.add_argument("--track", default="output/rc_38/Track1.bin"); pa.add_argument("--name", default=DEFAULT); pa.add_argument("--text", default=None); pa.set_defaults(fn=cmd_atlas)
    pf = sub.add_parser("fold"); pf.add_argument("track"); pf.add_argument("--name", default="all"); pf.set_defaults(fn=cmd_fold)
    pm = sub.add_parser("md5"); pm.add_argument("--name", default=DEFAULT); pm.set_defaults(fn=cmd_md5)
    pp = sub.add_parser("preview"); pp.add_argument("out"); pp.add_argument("--name", default=DEFAULT); pp.add_argument("--text", default=None); pp.set_defaults(fn=cmd_preview)
    a = ap.parse_args(); a.fn(a)
