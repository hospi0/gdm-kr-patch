#!/usr/bin/env python3
"""Generate a readable bilingual review doc from a translation (script/<MDT>_en.py + ja.json).

This pass's goal is an ACCURATE, COMPLETE, READABLE English script for human/agent error-checking
— NOT box-fitted text (terseness happens at the Step-3 pre-injection pass). So English here is
faithful prose; the 'budget' is shown only as later-injection info (OVER = will need Step-3
compression/relocation), never a reason to shorten the translation now.

Writes script/<MDT>/review.txt: per piece, in script order, each JP segment/run paired with its
English (and the byte budget for Step-3 reference). Untranslated text is flagged TODO.

Usage:  python3 src/review.py <MDT> [<MDT> ...]      |      python3 src/review.py all
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "script"))
sys.path.insert(0, str(ROOT / "src"))
from extract import looks_texty  # noqa: E402  (reuse the JP-content filter)

# Show story/name content; skip pure-bytecode pieces. 'save-menu'/'event-menu' hold the deferred
# system/menu text — included but only their genuinely-texty runs.
CAT_ORDER = ["intro", "dialogue", "location", "door", "save-location", "save-menu",
             "event-menu", "other"]
SKIP_CATS = {"map-setup"}


def load_en(base: str):
    try:
        m = importlib.import_module(f"{base}_en")
        return getattr(m, "SEG_TEXTS", {}), getattr(m, "RUN_TEXTS", {})
    except ModuleNotFoundError:
        return {}, {}


def collect_rows(base: str) -> list[dict]:
    """Structured bilingual rows for a MDT (shared by the text doc and the web review app).

    Each row: {piece, cat, kind: 'seg'|'run', key, speaker, jp, en (None=TODO), budget}.
    Same filtering as the text view: skip bytecode pieces, door particles, non-texty runs.
    """
    ja = json.load(open(ROOT / f"script/{base}/ja.json", encoding="utf-8"))
    seg_texts, run_texts = load_en(base)
    pieces = ja["pieces"]
    by_cat: dict[str, list[str]] = {}
    for code, p in pieces.items():
        by_cat.setdefault(p["category"], []).append(code)
    rows: list[dict] = []
    for cat in CAT_ORDER:
        if cat in SKIP_CATS:
            continue
        for code in sorted(by_cat.get(cat, []), key=lambda c: (len(c), c)):
            p = pieces[code]
            seg_map = seg_texts.get(code, {})
            run_map = run_texts.get(code, {})
            if p["segments"]:
                for s in p["segments"]:
                    if not s["jp"]:
                        continue
                    rows.append({"piece": code, "cat": cat, "kind": "seg", "key": s["idx"],
                                 "speaker": s["speaker"], "jp": s["jp"].replace("\n", " ").strip(),
                                 "en": seg_map.get(s["idx"]), "budget": s["budget"]})
            else:
                for r in p["text_runs"]:
                    if "jp" not in r or r.get("glyphs", 0) < 2:
                        continue
                    # show real text OR anything we've already translated (even if the gloss
                    # looks bytecode-ish, a run in run_map is intentional content)
                    if not looks_texty(r["jp"]) and r["i"] not in run_map:
                        continue
                    if r["jp"].strip().lstrip("ニ ") in ("への", "ホへ", "へ"):
                        continue
                    rows.append({"piece": code, "cat": cat, "kind": "run", "key": r["i"],
                                 "speaker": "", "jp": r["jp"], "en": run_map.get(r["i"]),
                                 "budget": r["len"]})
    return rows


def review(base: str) -> tuple[str, int, int]:
    out = [f"# {base}.MDT — bilingual review (Step 2c: accuracy pass, not box-fitted)",
           "# JP = best-effort gloss (read names by context); EN = translation; b = Step-3 byte budget.",
           ""]
    done = todo = 0
    cur = None
    for r in collect_rows(base):
        if r["piece"] != cur:
            cur = r["piece"]
            out.append(f"## piece {cur}  [{r['cat']}]")
        tag = f"  [{r['key']:>2}] {r['speaker']:<6}" if r["kind"] == "seg" else f"  run {r['key']:>2} "
        out.append(f"{tag} JP: {r['jp']}")
        if r["en"]:
            out.append(f"        EN: {r['en']}   (b{r['budget']})"); done += 1
        else:
            out.append("        EN: ** TODO **"); todo += 1
    out.append("")
    (ROOT / f"script/{base}/review.txt").write_text("\n".join(out), encoding="utf-8")
    return base, done, todo


def main() -> int:
    args = sys.argv[1:]
    if not args:
        sys.stderr.write(__doc__); return 2
    if args == ["all"]:
        args = sorted(p.parent.name for p in (ROOT / "script").glob("*/ja.json"))
    for mdt in args:
        base = mdt.removesuffix(".MDT")
        _, done, todo = review(base)
        print(f"script/{base}/review.txt: {done} translated, {todo} TODO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
