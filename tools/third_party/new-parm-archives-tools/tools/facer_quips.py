#!/usr/bin/env python3
"""facer_quips.py — translate the 256 voice-clip COMMENT QUIPS of the character-
EXPRESSIONS viewer (キャラクター表情集), shown when you press C on a portrait.

Same data file as the nameplates (see facer_names.py) — /FIELD/FACE2.DAT, resident
at HWRAM 0x06050000 — but a DIFFERENT slot pair:

  * slot 2  (offs[2]..offs[3]) = the 256-entry QUIP OFFSET TABLE
        [BE u16 index N][BE u16 offset of record N, relative to slot-3 base],
        256 entries, 0xFFFFFFFF-terminated.  (exact analogue of slot 0 for slot 1)
  * slot 3  (offs[3]..offs[4]) = the 256 QUIP RECORDS themselves.

  Quip record grammar (proven in-harness):
        0x20  <ctrl>  <line0> [0x01 <line1> [0x01 <line2>]]  0x07  [pad 0x00/0xf0]
      - byte0 = 0x20 (mandatory leading space)
      - <ctrl> = a single per-record width/style tag byte (even, 0x06..0x48). It is
        NOT rendered (verified: the user's on-screen quip shows no leading glyph) and
        does NOT move on-screen x. Preserved verbatim, like the nameplate ctrl.
      - lines are standard Grandia-16x16-tbl strings; 0x01 (<NL/01>) is the line break
      - 0x07 (<ED>) terminates; trailing 0x00/0xf0 are alignment padding
      - 21 records read 未表示 ("not shown") = unused slots; kept verbatim JP.

  RENDERER FONT (proven in-harness on user-expression-quip-jp-rc25 — see
  docs/lanes/laneQUIP-quips.md): unlike the nameplate, the quip box HONOURS control
  0x03 = switch to the 8x16 HALF-WIDTH ASCII font (mixed-case lowercase, ~2x the
  text density). Half-width mode persists across 0x01 line breaks within a record, so
  a single leading 0x03 covers the whole multi-line quip. English quips are therefore
  authored as 0x03 + ASCII with 0x01 line breaks. Box budget: <= LINE_CHARS half-width
  chars/line, <= MAX_LINES lines (see below); the encoder warns on overflow.

This tool rebuilds slot 2 (the offset table) + slot 3 (the records). It COMPOSES with
facer_names.py's nameplate fold (slots 0/1) and Lane O's slot-5 exit dialog by reading
the CURRENT on-disc FACE2 (with those English edits already applied) and preserving
slots 0/1/2/4..37 verbatim — so it must run AFTER those folds.

English quips are far longer than the compact JP kanji, so slot 3 CANNOT fit its
vanilla 10336-byte span. The file is grown: slots 0/1/2 stay in place (preserving
facer_names' English nameplates), slot 3 is replaced with the grown English block,
slots 4..37 shift down by the growth delta (bytes verbatim, incl. Lane O's slot-5
exit dialog), header entries >=4 are bumped, and the grown file is relocated with
src/relayout.py (append at track end + repoint the ISO dir record — proven DICDT/
TEXT2 pattern; the game rebuilds its file-index from the ISO dir at cold boot).

Subcommands:
  dump   FACE2.DAT                  -> JSON skeleton {records:[{i,ctrl,jp,lines,en_lines}]}
  patch  FACE2.DAT EN.json OUTDIR   -> OUTDIR/FACE2.DAT (grown English build)
  emit   TRACK.bin OUT.DAT          -> grown English FACE2.DAT from the track (RAM-inject)
  fold   TRACK.bin                  -> RC step (idempotent): grow slot 3 + relocate in place
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import dicdt  # Grandia16x16.tbl encode/decode

HDR_SLOTS = 38
QUIP_OFFTAB_SLOT = 2     # offs[2]..offs[3] = quip offset table
QUIP_REC_SLOT = 3        # offs[3]..offs[4] = quip records
N_RECORDS = 256
LINE_CHARS = 36          # half-width chars per line budget (measured: hard clip ~38)
MAX_LINES = 3            # box shows up to 3 lines


def _load(path):
    return bytearray(open(path, "rb").read())


def parse_header(d):
    return [struct.unpack(">I", d[i * 4:i * 4 + 4])[0] for i in range(HDR_SLOTS)]


def parse_records(d):
    """Return (slot3_base, offs, list of record dicts) via the slot-2 offset table."""
    offs = parse_header(d)
    s2, s3, s4 = offs[QUIP_OFFTAB_SLOT], offs[QUIP_REC_SLOT], offs[QUIP_REC_SLOT + 1]
    p = s2
    table = []
    while True:
        idx, off = struct.unpack(">HH", d[p:p + 4]); p += 4
        if idx == 0xffff:
            break
        table.append((idx, off))
    recs = []
    for k, (idx, off) in enumerate(table):
        end = (table[k + 1][1] if k + 1 < len(table) else (s4 - s3))
        rec = bytes(d[s3 + off:s3 + end])
        ctrl = rec[1]
        t = rec.find(0x07)
        body = rec[2:t] if t >= 0 else rec[2:]
        dec = dicdt.decode(body)
        lines = dec.split("<NL/01>")
        recs.append({"i": idx, "ctrl": ctrl, "body_hex": body.hex(),
                     "jp": dec, "lines": lines})
    return s3, offs, recs


def cmd_dump(face2_path):
    d = _load(face2_path)
    _, _, recs = parse_records(d)
    out = {"records": [
        {"i": r["i"], "ctrl": r["ctrl"], "jp": r["jp"], "lines": r["lines"],
         "en_lines": []} for r in recs]}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print()


def _enc_body(en_lines, orig_body_hex):
    """Encode an English quip body: 0x03 half-width ASCII, 0x01 line breaks.
    en_lines == [] (or None) -> keep the original JP body verbatim."""
    if not en_lines:
        return bytes.fromhex(orig_body_hex)
    parts = []
    for ln in en_lines:
        parts.append(b"\x03" + ln.encode("ascii"))
    return b"\x01".join(parts)


def build(face2_path, en_path):
    """Rebuild FACE2.DAT with an English slot 3. English quips are far longer than
    the compact JP kanji, so slot 3 cannot fit its vanilla 10336-byte span; the file
    is GROWN. FACE2.DAT is a header-indexed slot container (the 38 BE-u32 header
    entries ARE the slot table; each slot N spans offs[N]..offs[N+1]), with no known
    absolute cross-references between slots — the same invariant facer_names relies on
    and dicdt.py relies on for its section relocate. So we keep slots 0/1/2 in place
    (preserving facer_names' English nameplates), replace slot 3 with the grown
    English block, shift slots 4..37 down by the growth delta (their bytes copied
    verbatim, incl. Lane O's slot-5 exit dialog), and bump header entries >=4 by delta.
    offs[4] therefore still equals slot3_start + new_slot3_len, so the overlay bounds
    every slot correctly. The grown file is placed by src/relayout.py (append at track
    end + repoint the ISO dir record — the proven DICDT/TEXT2 pattern)."""
    d = _load(face2_path)
    s3_base, offs, recs = parse_records(d)
    en = json.load(open(en_path))["records"]
    if len(en) != len(recs):
        raise SystemExit(f"EN has {len(en)} records, file has {len(recs)}")

    body_all = bytearray()
    new_offsets = []
    warnings = []
    for r, e in zip(recs, en):
        assert r["i"] == e["i"], (r["i"], e["i"])
        new_offsets.append(len(body_all))
        ctrl = bytes([r["ctrl"]])
        el = e.get("en_lines") or []
        rec = b"\x20" + ctrl + _enc_body(el, r["body_hex"]) + b"\x07"
        while len(rec) % 2:
            rec += b"\x00"
        body_all += rec
        if el:
            if len(el) > MAX_LINES:
                warnings.append(f"  rec {r['i']:3d}: {len(el)} lines > {MAX_LINES}")
            for ln in el:
                if len(ln) > LINE_CHARS:
                    warnings.append(f"  rec {r['i']:3d}: line {len(ln)}>{LINE_CHARS}: {ln!r}")

    slot2 = bytearray()
    for k, o in enumerate(new_offsets):
        slot2 += struct.pack(">HH", k, o)
    slot2 += b"\xff\xff\xff\xff"
    s2_base = offs[QUIP_OFFTAB_SLOT]
    slot2_span = offs[QUIP_REC_SLOT] - s2_base
    if len(slot2) > slot2_span:
        raise SystemExit(f"slot2 offset table {len(slot2)} > vanilla span {slot2_span}")

    old_s3_span = offs[QUIP_REC_SLOT + 1] - offs[QUIP_REC_SLOT]
    # keep slot3 record block even-aligned so slot4 stays 2-aligned
    new_s3 = bytes(body_all)
    if len(new_s3) % 2:
        new_s3 += b"\x00"
    delta = len(new_s3) - old_s3_span

    # new header: offs[0..3] unchanged, offs[4..37] += delta
    new_offs = list(offs)
    for k in range(QUIP_REC_SLOT + 1, HDR_SLOTS):
        new_offs[k] += delta
    header = b"".join(struct.pack(">I", o) for o in new_offs)

    out = bytearray()
    out += header                                # 0x00..0x98 header (offs>=4 bumped)
    out += d[len(header):s2_base]                # slots 0 + 1 verbatim (nameplates)
    out += slot2 + b"\x00" * (slot2_span - len(slot2))   # slot 2 (rebuilt, same span)
    out += new_s3                                # slot 3 (grown English quips)
    out += d[offs[QUIP_REC_SLOT + 1]:]           # slots 4..37 verbatim (incl. slot-5 dlg)
    assert len(out) == len(d) + delta, (len(out), len(d), delta)
    assert new_offs[QUIP_REC_SLOT] == offs[QUIP_REC_SLOT]
    assert new_offs[QUIP_REC_SLOT + 1] == offs[QUIP_REC_SLOT] + len(new_s3)
    return bytes(out), warnings, len(body_all), delta


def cmd_patch(face2_path, en_path, outdir):
    new, warnings, used, delta = build(face2_path, en_path)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    p = Path(outdir) / "FACE2.DAT"
    p.write_bytes(new)
    parse_records(bytearray(new))  # sanity re-parse (offsets consistent)
    print(f"FACE2.DAT: {len(new)} B (grown +{delta} B); slot3 {used} B English")
    if warnings:
        print(f"WARNING: {len(warnings)} quip line/count overflow(s):")
        for w in warnings:
            print(w)


def _extract_face2(track):
    import iso
    with open(track, "rb") as f:
        rec = iso.find_record(f, "FACE2.DAT")
        out = bytearray()
        for s in range((rec["size"] + iso.USER_DATA - 1) // iso.USER_DATA):
            f.seek(iso.raw_offset(rec["lba"] + s))
            out += f.read(iso.USER_DATA)
    return bytes(out[:rec["size"]]), rec


def cmd_emit(track, out_path):
    """Extract the track's current FACE2.DAT, build the grown English version, write it
    to out_path (for harness RAM injection at HWRAM 0x06050000)."""
    root = Path(__file__).resolve().parent.parent
    en_json = root / "docs/menus/expression-quips-en.json"
    cur, _ = _extract_face2(track)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "cur.DAT").write_bytes(cur)
        cmd_patch(f"{td}/cur.DAT", str(en_json), str(Path(out_path).parent))
    # cmd_patch wrote <parent>/FACE2.DAT; move to requested name if different
    p = Path(out_path).parent / "FACE2.DAT"
    if str(p) != str(out_path):
        Path(out_path).write_bytes(p.read_bytes())
    print(f"emitted grown English FACE2.DAT -> {out_path}")


def cmd_fold(track):
    """RC step: extract the track's CURRENT FACE2.DAT (composes with facer_names slots
    0/1 + Lane O slot-5 dialog already applied), grow slot 3 with the checked-in EN
    JSON, and relocate the grown file with src/relayout.py (append at track end +
    repoint the ISO dir record — the proven DICDT/TEXT2 pattern). Idempotent: if the
    current FACE2 already equals the English rebuild, it is a no-op (English re-encodes
    to identical bytes, delta 0)."""
    import tempfile
    import subprocess
    root = Path(__file__).resolve().parent.parent
    en_json = root / "docs/menus/expression-quips-en.json"
    cur, rec = _extract_face2(track)
    grown, warnings, used, delta = build_from_bytes(cur, en_json)
    if grown == cur:
        print(f"expression quips: already English ({len(cur)} B) -> no-op")
        return
    with tempfile.TemporaryDirectory() as td:
        gp = Path(td) / "FACE2.DAT"
        gp.write_bytes(grown)
        outp = Path(td) / "out.bin"
        subprocess.run([sys.executable, str(root / "src/relayout.py"),
                        "--bin", track, "--name", "FACE2.DAT",
                        "--mdt", str(gp), "--out", str(outp)], check=True)
        Path(track).write_bytes(outp.read_bytes())
    print(f"expression quips folded (slot3 {used} B English, +{delta} B, relocated) "
          f"-> {track}")
    if warnings:
        print(f"WARNING: {len(warnings)} quip overflow(s):")
        for w in warnings:
            print(w)


def build_from_bytes(face2_bytes, en_path):
    """build() variant taking FACE2 bytes directly (avoids a temp file)."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".DAT", delete=True) as tf:
        tf.write(face2_bytes)
        tf.flush()
        return build(tf.name, en_path)


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 1
    cmd = argv[1]
    if cmd == "dump":
        cmd_dump(argv[2])
    elif cmd == "patch":
        cmd_patch(argv[2], argv[3], argv[4])
    elif cmd == "emit":
        cmd_emit(argv[2], argv[3])
    elif cmd == "fold":
        cmd_fold(argv[2])
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
