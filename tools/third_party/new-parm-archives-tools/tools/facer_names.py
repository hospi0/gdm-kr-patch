#!/usr/bin/env python3
"""facer_names.py — translate the character-EXPRESSIONS viewer (キャラクター表情集, FACER.BIN).

The expressions viewer launched from the E810 Screening-Room terminal renders its
top-right NAMEPLATE ("<character> <expression>", e.g. ジャスティン 思考) from a
plain tbl-encoded string table inside its data file:

  /FIELD/FACE2.DAT  (653720 B) — header = BE-u32 slot-offset table (38 slots,
      terminated by an all-slots-consumed 0). The whole file is loaded RESIDENT to
      HWRAM 0x06050000 by the FACER.BIN overlay (file offset == HWRAM offset - 0x06050000).
      * slot 0  (0x98..0x49c)  = a 256-entry NAMEPLATE OFFSET TABLE:
            [BE u16 index N][BE u16 offset of record N, relative to slot-1 base],
            256 entries, terminated by 0xFFFFFFFF.
      * slot 1  (0x49c..0x1258) = the 256 nameplate records themselves.
      * slots 2..37             = the viewer's own glyph/UI tables + FACE portrait art.

  Nameplate record grammar (proven in-harness):
      0x20  <ctrl>  <name tbl>  0x20  <caption tbl>  0x07  [pad 0x00/0xf0..]
      - byte0 = 0x20 (mandatory leading space; the parser requires it)
      - <ctrl> = one of 0x04/0x06/0x08/0x0a/0x0c/0x0e (a legacy width tag; it does
        NOT affect on-screen x-position — text is left-aligned at ~x=180 — so we
        preserve the original byte verbatim)
      - name and caption are standard Grandia-16x16-tbl strings, separated by a
        single 0x20 space; single-label records (minor NPCs) have no caption/space
      - 0x07 terminates the string; trailing 0xf0('~')/0x00 are alignment padding
      - records with the caption 表示 preceded by name 未 ("未 表示" = unused slot)

  RENDERER FONT (proven in-harness on user-expressions-rc24):
      This viewer's nameplate renderer draws FULL-WIDTH tbl glyphs cleanly. English
      must therefore be FULL-WIDTH UPPERCASE Roman (A-Z/0-9/space) — same convention
      as the design-materials viewer (viewer_mtmes.py). The 0x03 half-width switch IS
      parsed but renders a broken white box (do NOT use it). The nameplate box is a
      fixed sprite ~163 px wide => a hard clip at ~11 full-width glyphs (safe budget
      MAXW below); name + 1 space + caption must fit or the tail clips.

Because slot 1 is walked ordinally BUT indexed by the slot-0 offset table (record N's
byte offset), we must rebuild BOTH slot 0 (the offsets) and the header (slots 2.. shift
if slot 1's size changes). To stay disc-in-place (no relocation, savestate-safe like
MTMES) we NUL-pad the rebuilt file back to the vanilla FACE2.DAT size; `patch` errors if
the English text does not fit the vanilla slot-1 + slot-0 span.

Subcommands:
  dump   FACE2.DAT                 -> JSON skeleton {records:[{i,ctrl,name_jp,cap_jp,name_en,cap_en}]}
  patch  FACE2.DAT EN.json OUTDIR  -> OUTDIR/FACE2.DAT (vanilla size, NUL-padded)
  inject TRACK.bin FACE2.DAT       -> write it in place at FACE2.DAT's LBA
  fold   TRACK.bin                 -> RC step: extract vanilla FACE2.DAT, patch, inject
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import dicdt  # Grandia16x16.tbl encode/decode

HDR_SLOTS = 38          # BE-u32 header offset table entries (offs[38] == 0 sentinel)
SLOT0_OFF = 0x98        # nameplate offset table base (== header offsets[0])
N_RECORDS = 256
MAXW = 11               # full-width glyph budget (nameplate box hard-clips ~11)


def _load(path):
    return bytearray(open(path, "rb").read())


def parse_header(d):
    offs = [struct.unpack(">I", d[i * 4:i * 4 + 4])[0] for i in range(HDR_SLOTS)]
    return offs


def parse_records(d):
    """Return (slot1_base, list of dicts) parsed via the slot-0 offset table."""
    offs = parse_header(d)
    s1 = offs[1]
    # slot-0 offset table: (idx u16, off u16) pairs, 0xffff terminated
    p = SLOT0_OFF
    table = []
    while True:
        idx, off = struct.unpack(">HH", d[p:p + 4]); p += 4
        if idx == 0xffff:
            break
        table.append((idx, off))
    recs = []
    for k, (idx, off) in enumerate(table):
        end = s1 + (table[k + 1][1] if k + 1 < len(table) else (offs[2] - s1))
        rec = bytes(d[s1 + off:end])
        ctrl = rec[1]
        t = rec.find(0x07)
        body = rec[2:t] if t >= 0 else rec[2:]
        sp = body.find(0x20)
        if sp >= 0:
            name, cap = body[:sp], body[sp + 1:]
        else:
            name, cap = body, b""
        recs.append({"i": idx, "ctrl": ctrl,
                     "name_jp": dicdt.decode(name), "cap_jp": dicdt.decode(cap),
                     "name_hex": name.hex(), "cap_hex": cap.hex()})
    return s1, recs


def cmd_dump(face2_path):
    d = _load(face2_path)
    _, recs = parse_records(d)
    out = {"records": [
        {"i": r["i"], "ctrl": r["ctrl"], "name_jp": r["name_jp"], "cap_jp": r["cap_jp"],
         "name_en": "", "cap_en": ""} for r in recs]}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print()


# full-width tbl codes for ASCII punctuation the base encoder lacks
_PUNCT = {"?": "？", "!": "！"}


def _enc_field(en, orig_hex):
    """Encode one English field full-width uppercase; empty -> keep original bytes."""
    if en == "":
        return bytes.fromhex(orig_hex)
    out = bytearray()
    for ch in en:
        if ch in _PUNCT:
            out += dicdt.REV[_PUNCT[ch]]
        else:
            out += dicdt.encode(ch, halfwidth=False)
    return bytes(out)


def build(face2_path, en_path):
    d = _load(face2_path)
    offs = parse_header(d)
    s1_base, recs = parse_records(d)
    en = json.load(open(en_path))["records"]
    if len(en) != len(recs):
        raise SystemExit(f"EN has {len(en)} records, file has {len(recs)}")

    # Rebuild slot 1 (records) + slot 0 (offset table). Preserve the ctrl byte.
    body = bytearray()
    new_offsets = []
    warnings = []
    for r, e in zip(recs, en):
        assert r["i"] == e["i"]
        new_offsets.append(len(body))
        ctrl = bytes([r["ctrl"]])
        name = _enc_field(e.get("name_en", ""), r["name_hex"])
        # cap_en: None = intentionally NO caption (name-only); "" = keep original JP;
        # non-empty = English caption.
        ce = e.get("cap_en", "")
        cap = b"" if ce is None else _enc_field(ce, r["cap_hex"])
        rec = b"\x20" + ctrl + name
        if cap:
            rec += b"\x20" + cap
        rec += b"\x07"
        while len(rec) % 2:
            rec += b"\x00"
        body += rec
        # width check on the ACTUAL English output (full-width glyph == 1 cell)
        ne = e.get("name_en", "")
        if ne:  # only English-translated records are subject to the box budget
            w = len(ne) + (1 + len(ce) if ce else 0)
            if w > MAXW:
                warnings.append(f"  rec {r['i']:3d}: {ne!r} {ce!r} = {w} glyphs > {MAXW}")

    # slot-0 offset table (idx, offset) + 0xffff terminator
    slot0 = bytearray()
    for k, o in enumerate(new_offsets):
        slot0 += struct.pack(">HH", k, o)
    slot0 += b"\xff\xff\xff\xff"

    # The vanilla layout: [header][slot0 @0x98][slot1 @ offs[1]] ... [slot2 @ offs[2]]
    # slot0 must fit its vanilla span (0x98..offs[1]); slot1 must fit (offs[1]..offs[2]).
    slot0_span = offs[1] - SLOT0_OFF
    slot1_span = offs[2] - offs[1]
    if len(slot0) > slot0_span:
        raise SystemExit(f"slot0 offset table {len(slot0)} > vanilla span {slot0_span}")
    if len(body) > slot1_span:
        raise SystemExit(
            f"slot1 records {len(body)} > vanilla span {slot1_span} "
            f"(would need relocation). Shorten captions.")

    out = bytearray(d)  # start from vanilla; overwrite slot0 + slot1 spans, NUL-pad
    out[SLOT0_OFF:offs[1]] = slot0 + b"\x00" * (slot0_span - len(slot0))
    out[offs[1]:offs[2]] = bytes(body) + b"\x00" * (slot1_span - len(body))
    assert len(out) == len(d), (len(out), len(d))
    return bytes(out), warnings


def cmd_patch(face2_path, en_path, outdir):
    new, warnings = build(face2_path, en_path)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    p = Path(outdir) / "FACE2.DAT"
    p.write_bytes(new)
    # sanity: re-parse
    _, recs = parse_records(bytearray(new))
    print(f"FACE2.DAT: {len(new)} B (vanilla size, in-place), {len(recs)} records")
    if warnings:
        print(f"WARNING: {len(warnings)} nameplate(s) exceed {MAXW} full-width glyphs (will clip):")
        for w in warnings:
            print(w)


def cmd_inject(track, face2_path):
    import iso
    new = open(face2_path, "rb").read()
    with open(track, "r+b") as f:
        rec = iso.find_record(f, "FACE2.DAT")
        if not rec:
            raise SystemExit("FACE2.DAT not found in track")
        if len(new) != rec["size"]:
            raise SystemExit(f"size mismatch {len(new)} != on-disc {rec['size']} (must be in-place)")
        n_sectors = (len(new) + iso.USER_DATA - 1) // iso.USER_DATA
        for i in range(n_sectors):
            chunk = new[i * iso.USER_DATA:(i + 1) * iso.USER_DATA]
            chunk = chunk + b"\x00" * (iso.USER_DATA - len(chunk))
            f.seek(iso.raw_offset(rec["lba"] + i))
            f.write(chunk)
    print(f"injected FACE2.DAT: {len(new)} B at LBA {rec['lba']} ({n_sectors} sectors)")


def cmd_fold(track):
    """RC step (idempotent): extract vanilla FACE2.DAT, patch with the checked-in EN
    JSON, inject in place. Already-English re-encodes to the same bytes => idempotent."""
    import tempfile
    import iso
    root = Path(__file__).resolve().parent.parent
    en_json = root / "docs/menus/expressions-en.json"
    with open(track, "rb") as f, tempfile.TemporaryDirectory() as td:
        rec = iso.find_record(f, "FACE2.DAT")
        out = bytearray()
        for s in range((rec["size"] + iso.USER_DATA - 1) // iso.USER_DATA):
            f.seek(iso.raw_offset(rec["lba"] + s))
            out += f.read(iso.USER_DATA)
        (Path(td) / "van_FACE2.DAT").write_bytes(bytes(out[:rec["size"]]))
        cmd_patch(f"{td}/van_FACE2.DAT", str(en_json), td)
        cmd_inject(track, f"{td}/FACE2.DAT")
    print(f"expressions viewer folded -> {track}")


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 1
    cmd = argv[1]
    if cmd == "dump":
        cmd_dump(argv[2])
    elif cmd == "patch":
        cmd_patch(argv[2], argv[3], argv[4])
    elif cmd == "inject":
        cmd_inject(argv[2], argv[3])
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
