#!/usr/bin/env python3
"""viewer_mtmes.py — translate the DESIGN-MATERIALS viewer (設定資料集, MATER.BIN).

The viewer launched from the E808 archives terminal renders its text from TWO
plain tbl-encoded sources (standard Grandia 16x16 table, same as DICDT.DAT —
NO codec involved; the ST1 blob in the overlay is only UI art):

  /FIELD/MTMES.DAT  (1004 B)  — header = 6 BE-u32 slot offsets (0x18, ...);
      each slot = 17 NUL-separated strings: [0] category title, [1..16] the 16
      page captions (matching art banks MT{cat}00..MT{cat}0F.BIN + MT{cat}FF
      thumbnail sheet). NUL-padded to 4-byte alignment. Categories:
      美術設定1/2, モンスター設定, キャラクター設定1/2/3.
  /FIELD/MTOUT.DAT  (110644 B) — header = 4 BE-u32 slot offsets;
      slot 0 = 512-B palette, slots 1-2 = UI art, slot 3 (LAST, 68 B) = the
      viewer's 6 category MENU labels, NUL-separated (same tbl encoding).

English encodes as FULL-WIDTH UPPERCASE tbl Roman (A-Z 0x2B.., digits, space).
NOTE: the 0x03 half-width-ASCII convention that works in the monster
encyclopedia does NOT work here — this viewer's renderer ignores 0x03 and
draws the raw bytes through the 16x16 table (proven in-harness: "Art Design 1"
renders as 今のば Ｚちはづっな). Both files are consumed ordinally (NUL walk, no pointer
table), so entries may change length freely; we only rewrite slot offsets in
the header. Both files fit their original sector allocation when translated,
so they are patched IN PLACE on the track (same LBA; only the ISO dir record's
data-length changes). Savestates bake the old file-index table (HWRAM
0x06029b08 entries = [8-char name][FAD u32][size u32]) — for harness runs
against an old state, poke the new size into the "MTMESDAT"/"MTOUTDAT" entries.

Subcommands:
  dump   MTMES.DAT MTOUT.DAT           -> JSON skeleton on stdout (jp + en:"")
  patch  MTMES.DAT MTOUT.DAT EN.json OUTDIR   -> OUTDIR/MTMES.DAT, OUTDIR/MTOUT.DAT
  inject TRACK.bin NAME NEWFILE        -> write NEWFILE in place at NAME's LBA
         (fails if it needs more sectors than the gap to the next file)

EN.json: {"menu": ["...", x6], "slots": [["title", "cap1", ... "cap16"], x6]}
Empty string = keep original Japanese.
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import dicdt  # tbl encode/decode (Grandia16x16.tbl)

N_SLOTS = 6
N_STRINGS = 17  # title + 16 page captions


def parse_packed(data: bytes, table_len: int):
    """Return (offsets, list-of-slot-string-lists) for a BE-u32 offset-table file."""
    offs = [struct.unpack(">I", data[i * 4:i * 4 + 4])[0] for i in range(table_len)]
    slots = []
    for i, o in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else len(data)
        parts = data[o:end].split(b"\x00")
        while parts and not parts[-1]:
            parts.pop()  # strip alignment padding
        slots.append(parts)
    return offs, slots


def cmd_dump(mtmes_path: str, mtout_path: str) -> None:
    mtmes = open(mtmes_path, "rb").read()
    mtout = open(mtout_path, "rb").read()
    _, slots = parse_packed(mtmes, N_SLOTS)
    _, oslots = parse_packed(mtout, 4)
    out = {
        "menu": [{"jp": dicdt.decode(p), "en": ""} for p in oslots[3]],
        "slots": [[{"jp": dicdt.decode(p), "en": ""} for p in s] for s in slots],
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print()


def _encode(en: str, jp_bytes: bytes) -> bytes:
    if not en:
        return jp_bytes
    # PROVEN IN-HARNESS: the design viewer's 16x16 renderer does NOT honor the
    # 0x03 half-width-ASCII switch (unlike the monster encyclopedia's) — ASCII
    # renders as page-0 garble ("Art Design 1" -> 今のば Ｚちはづっな). So English
    # must use the tbl's FULL-WIDTH UPPERCASE Roman (A-Z/0-9/space only).
    return dicdt.encode(en, halfwidth=False)


def _build_packed(orig: bytes, table_len: int, texts, only_slot=None) -> bytes:
    """Rebuild the packed file; texts = list per slot of EN strings ('' = keep)."""
    offs, slots = parse_packed(orig, table_len)
    out = bytearray()
    new_offs = []
    body = bytearray()
    base = table_len * 4
    for i, parts in enumerate(slots):
        new_offs.append(base + len(body))
        if only_slot is not None and i != only_slot:
            # keep the slot's original raw bytes verbatim (incl. padding)
            end = offs[i + 1] if i + 1 < len(offs) else len(orig)
            body += orig[offs[i]:end]
            continue
        en_list = texts[i] if only_slot is None else texts
        if len(en_list) != len(parts):
            raise SystemExit(f"slot {i}: {len(en_list)} strings != original {len(parts)}")
        for en, jp in zip(en_list, parts):
            body += _encode(en, jp) + b"\x00"
        while len(body) % 4:
            body += b"\x00"
    for o in new_offs:
        out += struct.pack(">I", o)
    out += body
    return bytes(out)


def cmd_patch(mtmes_path: str, mtout_path: str, en_path: str, outdir: str) -> None:
    en = json.load(open(en_path))
    menu = [e["en"] for e in en["menu"]]
    slots = [[e["en"] for e in s] for s in en["slots"]]
    mtmes = open(mtmes_path, "rb").read()
    mtout = open(mtout_path, "rb").read()
    new_mtmes = _build_packed(mtmes, N_SLOTS, slots)
    new_mtout = _build_packed(mtout, 4, menu, only_slot=3)
    # CRITICAL (Lane K RE): the category-page label parser ends on a DOUBLE NUL.
    # Slot 3 is the last slot, so the label block must leave >=1 spare NUL after
    # the final terminator INSIDE the file, or the parser runs off the end of the
    # load buffer, parses a garbage 7th label, overflows the sprite staging array
    # and trashes its own label structs (= the historic "pixel noise" screen).
    # Enforce it by keeping MTOUT at its vanilla size, NUL-padded (also keeps the
    # ISO dir size and stale-savestate file-index sizes exactly unchanged).
    if len(new_mtout) >= len(mtout):
        raise SystemExit(
            f"MTOUT menu labels too long: {len(new_mtout)} >= vanilla {len(mtout)} "
            f"(need >=1 spare NUL after the last label for the double-NUL end marker)")
    new_mtout = new_mtout + b"\x00" * (len(mtout) - len(new_mtout))
    # Pad MTMES to its vanilla size too: keeps the ISO dir record data-length AND
    # the file-index sizes baked into existing savestates exactly unchanged (the
    # trailing NULs are stripped by the ordinal NUL-walk parse, so it's free).
    if len(new_mtmes) > len(mtmes):
        raise SystemExit(f"MTMES text too long: {len(new_mtmes)} > vanilla {len(mtmes)}")
    new_mtmes = new_mtmes + b"\x00" * (len(mtmes) - len(new_mtmes))
    Path(outdir).mkdir(parents=True, exist_ok=True)
    for name, old, new in (("MTMES.DAT", mtmes, new_mtmes), ("MTOUT.DAT", mtout, new_mtout)):
        p = Path(outdir) / name
        p.write_bytes(new)
        o_sec = (len(old) + 2047) // 2048
        n_sec = (len(new) + 2047) // 2048
        print(f"{name}: {len(old)} -> {len(new)} B ({o_sec} -> {n_sec} sectors)")
        # sanity round-trip
        _, rslots = parse_packed(new, N_SLOTS if name == "MTMES.DAT" else 4)


def cmd_inject(track: str, name: str, newfile: str) -> None:
    import iso
    new = open(newfile, "rb").read()
    n_sectors = (len(new) + iso.USER_DATA - 1) // iso.USER_DATA
    with open(track, "r+b") as f:
        rec = iso.find_record(f, name)
        if not rec:
            raise SystemExit(f"not found: {name}")
        old_sectors = (rec["size"] + iso.USER_DATA - 1) // iso.USER_DATA
        # find next file's LBA to know the real gap
        next_lba = None
        for _, lba, size, _raw in iso.walk_records(f):
            if lba > rec["lba"] and (next_lba is None or lba < next_lba):
                next_lba = lba
        gap = (next_lba - rec["lba"]) if next_lba else old_sectors
        if n_sectors > gap:
            raise SystemExit(f"{name}: needs {n_sectors} sectors > gap {gap} — relocate instead")
        for i in range(n_sectors):
            chunk = new[i * iso.USER_DATA:(i + 1) * iso.USER_DATA]
            chunk = chunk + b"\x00" * (iso.USER_DATA - len(chunk))
            # raw_offset() already points past the 16-byte sync+MSF+mode header
            f.seek(iso.raw_offset(rec["lba"] + i))
            f.write(chunk)
        # patch dir record data-length (both-endian u32 at rec_raw+10)
        f.seek(rec["rec_raw"] + 10)
        f.write(struct.pack("<I", len(new)))
        f.seek(rec["rec_raw"] + 14)
        f.write(struct.pack(">I", len(new)))
    print(f"injected {name}: {len(new)} B at LBA {rec['lba']} ({n_sectors}/{gap} sectors), dir size updated")


def cmd_fold(track: str) -> None:
    """One-shot RC step (Lane K): make the design-materials viewer fully English.

    MTMES.DAT (tab titles + plate captions): extract from the track, re-patch with the
    checked-in EN json, inject (vanilla-size NUL-padded; idempotent — already-English
    text re-encodes to the same bytes).
    MTOUT.DAT (6 category menu labels + the baked DESIGN MATERIALS banner + the 6
    selected-label bar strips): the authored file ships as patches/viewer/MTOUT.DAT.xdelta3
    against the VANILLA bytes (the art re-author needs RAM oracles not present at RC-build
    time). md5-gated like tools/mg_fold_rc.py: vanilla -> apply delta; already-English ->
    skip; anything else -> hard error. Falls back to the text-labels-only cmd_patch output
    if the delta is missing."""
    import hashlib
    import json as _json
    import subprocess
    import tempfile
    import iso
    root = Path(__file__).resolve().parent.parent
    en_json = root / "docs/menus/design-materials-en.json"
    patch_dir = root / "patches/viewer"
    with open(track, "rb") as f, tempfile.TemporaryDirectory() as td:
        for name in ("MTMES.DAT", "MTOUT.DAT"):
            rec = iso.find_record(f, name)
            out = bytearray()
            for s in range((rec["size"] + iso.USER_DATA - 1) // iso.USER_DATA):
                f.seek(iso.raw_offset(rec["lba"] + s))
                out += f.read(iso.USER_DATA)
            (Path(td) / f"van_{name}").write_bytes(bytes(out[:rec["size"]]))
        cmd_patch(f"{td}/van_MTMES.DAT", f"{td}/van_MTOUT.DAT", str(en_json), td)
        cmd_inject(track, "MTMES.DAT", f"{td}/MTMES.DAT")
        delta = patch_dir / "MTOUT.DAT.xdelta3"
        if delta.exists():
            m = _json.loads((patch_dir / "manifest.json").read_text())["MTOUT.DAT"]
            cur = (Path(td) / "van_MTOUT.DAT").read_bytes()
            cur_md5 = hashlib.md5(cur).hexdigest()
            if cur_md5 == m["english_md5"]:
                print("MTOUT.DAT: already English on this track — skipping")
                return print(f"design-materials viewer folded -> {track}")
            if cur_md5 != m["vanilla_md5"]:
                raise SystemExit(
                    f"MTOUT.DAT: track bytes are neither vanilla nor English (md5 {cur_md5}) — "
                    f"refusing to fold (re-author with tools/viewer_mtout_gfx.py?)")
            subprocess.run(["xdelta3", "-f", "-d", "-s", f"{td}/van_MTOUT.DAT",
                            str(delta), f"{td}/en_MTOUT.DAT"], check=True)
            new = (Path(td) / "en_MTOUT.DAT").read_bytes()
            if len(new) != m["size"] or hashlib.md5(new).hexdigest() != m["english_md5"]:
                raise SystemExit("MTOUT.DAT: delta output failed size/md5 verification")
            cmd_inject(track, "MTOUT.DAT", f"{td}/en_MTOUT.DAT")
        else:
            print("WARNING: patches/viewer/MTOUT.DAT.xdelta3 missing — folding text-only "
                  "MTOUT (menu labels English, banner/bar art stays vanilla)")
            cmd_inject(track, "MTOUT.DAT", f"{td}/MTOUT.DAT")
    print(f"design-materials viewer folded -> {track}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "dump":
        cmd_dump(argv[2], argv[3])
    elif cmd == "patch":
        cmd_patch(argv[2], argv[3], argv[4], argv[5])
    elif cmd == "inject":
        cmd_inject(argv[2], argv[3], argv[4])
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
