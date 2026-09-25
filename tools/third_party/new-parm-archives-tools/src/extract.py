#!/usr/bin/env python3
"""Extract MDT script text VERBATIM into script/<MDT>/ (Step 2a).

Drives the Java MDTFileParser/ScriptParser to split every script-bearing MDT into numbered
dialogue pieces, then decodes each piece preserving:
  - exact Japanese (we store the raw bytes as hex == the true verbatim record; the decoded
    gloss is best-effort via Grandia16x16.tbl, which is the original-Grandia table and
    mis-renders a few Digital Museum page-1 glyphs),
  - speaker attribution (portrait position left/middle/right) and original order,
  - per-text-run byte budgets + offsets so translations re-inject in place (Step 3).

Outputs per MDT (committed -- it's text, not game data):
  script/<MDT>/ja.txt    human-readable, grouped by piece category
  script/<MDT>/ja.json   machine-readable: pieces -> segments + text_runs (hex + gloss + budget)

Usage:
  extract.py all                 # every script-bearing MDT
  extract.py <MDT> [<MDT> ...]   # specific MDTs, e.g. extract.py E814.MDT EC0C.MDT
"""
from __future__ import annotations

import glob
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subst  # noqa: E402  (_is_portrait, iter_segments, _tokenize_box)
import decode as decode_mod  # noqa: E402  (load_table)

ROOT = Path(__file__).resolve().parent.parent
CP = ROOT / "tools/vendor/GrandiaTranslation/GrandiaTranslationTools/target/classes"
WORK = ROOT / "output/.extract_work"          # gitignored scratch
SCRIPT_DIR = ROOT / "script"

POS = {0x03: "left", 0x12: "middle", 0x21: "right"}

# MDT files that contain NO script section (parse-mdt emits no .SCN).
NO_SCRIPT = {"0000.MDT", "0004.MDT", "E8FF.MDT"}

# Pieces that are pure event/map bytecode, not dialogue. We still extract their text runs
# (they can hold incidental menu strings) but tag them so the readable view stays clean.
BYTECODE_PIECES = {"3000"}


def sh(*args: str) -> str:
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(f"command failed: {' '.join(map(str, args))}")
    return r.stdout


def java(*args: str) -> str:
    return sh("java", "-cp", str(CP), "com.grandia.cli.MDTParserCLI", *args)


def find_bin1() -> str:
    return glob.glob(str(ROOT / "input/**/*Track 1*.bin"), recursive=True)[0]


def _is_jp(ch: str) -> bool:
    o = ord(ch)
    return (0x3040 <= o <= 0x30FF      # hiragana + katakana
            or 0x4E00 <= o <= 0x9FFF   # CJK kanji
            or ch in "ー・「」『』、。！？")


def looks_texty(gloss: str) -> bool:
    """True if a flat text-run gloss reads like real dialogue/name text rather than bytecode
    params. Requires >=2 Japanese chars and a JP majority (filters runs of full-width latin
    'VV'/'FF' or stray symbols the engine uses as opcode operands). A '□' (missing-glyph byte)
    in a short run is the signature of an opcode operand (e.g. the 'ぼ□Xぬ' event pattern), so a
    run containing '□' only counts as text if it's clearly long (>=6 JP chars)."""
    jp = sum(_is_jp(c) for c in gloss)
    if "□" in gloss and jp < 6:
        return False
    real = sum(1 for c in gloss if c != "□" and not c.isspace())
    return jp >= 2 and (real == 0 or jp / real >= 0.5)


def piece_category(code: str) -> str:
    if code == "0":
        return "intro"            # dialogue mixed with map/camera bytecode (hardest)
    if code.startswith("5") or code.startswith("6"):
        return "dialogue"
    if code == "c000":
        return "location"
    if code.startswith("d"):
        return "door"
    if code == "e000":
        return "save-menu"
    if code == "e001":
        return "save-location"
    if code in BYTECODE_PIECES or code == "3000":
        return "map-setup"
    if code.startswith(("4", "9", "a")):
        return "event-menu"       # bytecode w/ possible embedded menu strings
    return "other"


def decode_run(run: bytes, table: dict[int, str], ascii_font: bool) -> tuple[str, int]:
    """Decode one text run to a gloss; return (gloss, glyph_count)."""
    out: list[str] = []
    i, n, glyphs = 0, len(run), 0
    while i < n:
        c = run[i]
        if ascii_font:
            out.append(chr(c) if 0x20 <= c <= 0x7E else "□"); i += 1
        elif 0x10 <= c <= 0x1F and i + 1 < n:
            key = (c << 8) | run[i + 1]
            out.append(table.get(key, "□")); i += 2
        else:
            out.append(table.get(c, "□")); i += 1
        glyphs += 1
    return "".join(out), glyphs


def tokenize_piece(data: bytes, table: dict[int, str]) -> list[dict]:
    """Classify a whole piece into tokens: portrait / ctrl / text. Tracks font state so 0x03
    (8x16 ASCII) runs decode as ASCII and 0x04 returns to 16x16. Text runs carry byte offset,
    length, glyph count, exact hex, and gloss."""
    toks: list[dict] = []
    i, n = 0, len(data)
    ascii_font = False
    while i < n:
        c = data[i]
        if subst._is_portrait(data, i):
            toks.append({"t": "portrait", "off": i, "pos": POS.get(data[i + 1], "?"),
                         "hex": data[i:i + 6].hex()})
            i += 6
        elif c <= 0x0F:
            if c == 0x03:
                ascii_font = True
            elif c == 0x04:
                ascii_font = False
            toks.append({"t": "ctrl", "off": i, "code": c})
            i += 1
        else:
            j = i
            while j < n and not (data[j] <= 0x0F or subst._is_portrait(data, j)):
                j += 2 if 0x10 <= data[j] <= 0x1F else 1
            run = data[i:j]
            gloss, glyphs = decode_run(run, table, ascii_font)
            toks.append({"t": "text", "off": i, "len": len(run), "glyphs": glyphs,
                         "hex": run.hex(), "jp": gloss})
            i = j
    return toks


def segment_view(data: bytes, table: dict[int, str]) -> list[dict]:
    """Portrait-delimited segments (matches subst.iter_segments indexing, used for re-injection).
    Each segment's gloss + total text byte budget (sum of fillable run lengths)."""
    segs: list[dict] = []
    for idx, posb, a, b in subst.iter_segments(data):
        seg = data[a:b]
        gloss_parts: list[str] = []
        budget = 0
        ascii_font = False
        for tok in subst._tokenize_box(seg):  # skips the 6-byte starting portrait code
            if tok[0] == "ctrl":
                cb = tok[1]
                if cb == b"\x03":
                    ascii_font = True
                elif cb == b"\x04":
                    ascii_font = False
                elif cb == b"\x01":
                    gloss_parts.append("\n        ")
                elif cb == b"\x02":
                    gloss_parts.append(" / ")
                # portrait/other controls: skip in gloss
            else:
                _, run_bytes, glyphs = tok
                g, _ = decode_run(run_bytes, table, ascii_font)
                gloss_parts.append(g)
                budget += len(run_bytes)
        segs.append({"idx": idx, "speaker": POS.get(posb, "?"),
                     "jp": "".join(gloss_parts).strip(), "budget": budget})
    return segs


def extract_mdt(name: str, bin1: str, table: dict[int, str]) -> dict:
    base = name[:-4] if name.upper().endswith(".MDT") else name
    name = base + ".MDT"
    w = WORK / base
    if w.exists():
        shutil.rmtree(w)
    (w / "parts").mkdir(parents=True, exist_ok=True)
    (w / "pieces").mkdir(parents=True, exist_ok=True)

    sh(sys.executable, str(ROOT / "src/iso.py"), "extract", bin1, name, str(w / name))
    java("parse-mdt", str(w), str(w / "parts"), ".MDT", "big")
    scn = w / "parts" / f"{base}.SCN"
    if not scn.exists():
        return {"mdt": name, "pieces": {}, "note": "no script section"}
    java("parse-script", str(scn), str(w / "parts" / f"{base}.OFS"), str(w / "pieces"))

    pieces: dict[str, dict] = {}
    for pf in sorted((w / "pieces").iterdir()):
        code = pf.name
        data = pf.read_bytes()
        toks = tokenize_piece(data, table)
        text_runs = []
        for k, t in enumerate(t2 for t2 in toks if t2["t"] == "text"):
            # Keep full verbatim hex + gloss for real text (what we translate); for bytecode/param
            # runs keep only the structural stub (their bytes are re-derivable from the disc).
            if looks_texty(t["jp"]):
                text_runs.append({"i": k, "off": t["off"], "len": t["len"],
                                  "glyphs": t["glyphs"], "hex": t["hex"], "jp": t["jp"]})
            else:
                text_runs.append({"i": k, "off": t["off"], "len": t["len"],
                                  "glyphs": t["glyphs"], "bytecode": True})
        has_port = any(t["t"] == "portrait" for t in toks)
        pieces[code] = {
            "category": piece_category(code),
            "size": len(data),
            "has_portraits": has_port,
            "segments": segment_view(data, table) if has_port else [],
            "text_runs": text_runs,
        }
    return {"mdt": name, "pieces": pieces}


def write_outputs(result: dict) -> None:
    name = result["mdt"]
    base = name[:-4]
    out_dir = SCRIPT_DIR / base
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ja.json").write_text(
        json.dumps({"generated": str(date.today()), **result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    lines: list[str] = [f"# {name} — verbatim JP extraction ({date.today()})",
                        "# Raw bytes (hex) in ja.json are the verbatim record; the JP below is a",
                        "# best-effort gloss (Grandia16x16.tbl). 'budget' = replaceable text bytes.",
                        ""]
    cat_order = ["intro", "dialogue", "location", "door", "save-location", "save-menu",
                 "event-menu", "map-setup", "other"]
    pieces = result.get("pieces", {})
    by_cat: dict[str, list[str]] = {}
    for code, p in pieces.items():
        by_cat.setdefault(p["category"], []).append(code)
    for cat in cat_order:
        for code in sorted(by_cat.get(cat, []), key=lambda c: (len(c), c)):
            p = pieces[code]
            ntext = len([r for r in p["text_runs"] if r["glyphs"] >= 2])
            lines.append(f"## piece {code}  [{cat}]  {p['size']}B  "
                         f"{ntext} text-runs{'  (portraits)' if p['has_portraits'] else ''}")
            if p["segments"]:
                for s in p["segments"]:
                    if s["jp"]:
                        lines.append(f"  [{s['idx']:>2}] {s['speaker']:<6} (budget {s['budget']:>3}) "
                                     f"| {s['jp']}")
            else:
                shown = [r for r in p["text_runs"] if looks_texty(r.get("jp", ""))]
                for r in shown:
                    lines.append(f"  run {r['i']:>2} @{r['off']:<4} ({r['len']:>3}B/"
                                 f"{r['glyphs']:>2}g) | {r['jp']}")
                hidden = len(p["text_runs"]) - len(shown)
                if hidden:
                    lines.append(f"  (+{hidden} bytecode/param runs hidden — see ja.json)")
            lines.append("")
    (out_dir / "ja.txt").write_text("\n".join(lines), encoding="utf-8")


def script_mdts(bin1: str) -> list[str]:
    out = sh(sys.executable, str(ROOT / "src/iso.py"), "list", bin1)
    names = []
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) >= 3 and parts[-1].endswith(".MDT"):
            n = parts[-1].rsplit("/", 1)[-1]
            if n not in NO_SCRIPT:
                names.append(n)
    return names


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    bin1 = find_bin1()
    table = decode_mod.load_table()
    WORK.mkdir(parents=True, exist_ok=True)

    targets = script_mdts(bin1) if sys.argv[1] == "all" else sys.argv[1:]

    summary = []
    for name in targets:
        result = extract_mdt(name, bin1, table)
        if not result.get("pieces"):
            print(f"{name}: no script section, skipped")
            continue
        write_outputs(result)
        npieces = len(result["pieces"])
        nruns = sum(len(p["text_runs"]) for p in result["pieces"].values())
        print(f"{name}: {npieces} pieces, {nruns} text-runs -> script/{name[:-4]}/")
        summary.append((name, npieces, nruns))
    print(f"\nDone: {len(summary)} MDTs extracted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
