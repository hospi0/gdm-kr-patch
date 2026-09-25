#!/usr/bin/env python3
"""Validate a Step-2c translation file (script/<MDT>_en.py) against the extracted pieces.

Checks, per piece in SEG_TEXTS / RUN_TEXTS:
  - equal-length substitution holds (subst.substitute_piece_perseg never changes piece length);
  - no segment/run English OVERFLOWS its usable equal-length room (which would drop words).

Run extraction first (output/.extract_work/<base>/pieces/ must exist), e.g.:
    python3 src/extract.py <MDT> && python3 src/validate_en.py <MDT>
Exit 0 = all fit; 1 = overflow(s) found (still injectable, but those entries truncate -> Step-3
relocate/abbreviate). Use it as the per-MDT gate before committing a translation.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "script"))
import subst  # noqa: E402

WORK = ROOT / "output/.extract_work"


def usable_room_perseg(piece: bytes, idx: int) -> int:
    for i, _p, a, b in subst.iter_segments(piece):
        if i == idx:
            return sum(len(t[1]) - 1 for t in subst._tokenize_box(piece[a:b])
                       if t[0] == "text" and t[2] >= 4)
    return -1


def usable_room_perrun(piece: bytes, run_i: int) -> int:
    runs = [t for t in _piece_text_runs(piece)]
    return (len(runs[run_i][1]) - 1) if 0 <= run_i < len(runs) else -1


def _piece_text_runs(data: bytes):
    out, i, n = [], 0, len(data)
    while i < n:
        c = data[i]
        if subst._is_portrait(data, i):
            i += 6
        elif c <= 0x0F:
            i += 1
        else:
            j = i
            while j < n and not (data[j] <= 0x0F or subst._is_portrait(data, j)):
                j += 2 if 0x10 <= data[j] <= 0x1F else 1
            out.append(("text", data[i:j])); i = j
    return out


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__); return 2
    base = sys.argv[1].removesuffix(".MDT")
    en = importlib.import_module(f"{base}_en")
    pieces_dir = WORK / base / "pieces"
    if not pieces_dir.exists():
        sys.stderr.write(f"missing {pieces_dir}; run: python3 src/extract.py {base}.MDT\n"); return 2

    overflow = 0
    for code, seg_map in getattr(en, "SEG_TEXTS", {}).items():
        piece = (pieces_dir / code).read_bytes()
        out = subst.substitute_piece_perseg(piece, seg_map, min_glyphs=4)
        assert len(out) == len(piece), f"{code}: length changed!"
        for idx, txt in seg_map.items():
            room = usable_room_perseg(piece, idx)
            if len(txt) > room:
                print(f"  OVER {code} seg {idx}: {len(txt)} > room {room}: {txt!r}")
                overflow += 1
    for code, run_map in getattr(en, "RUN_TEXTS", {}).items():
        piece = (pieces_dir / code).read_bytes()
        runs = _piece_text_runs(piece)
        for ri, txt in run_map.items():
            room = (len(runs[ri][1]) - 1) if 0 <= ri < len(runs) else -1
            flag = "OVER" if len(txt) > room else "ok"
            if flag == "OVER":
                overflow += 1
            print(f"  {flag:>4} {code} run {ri}: {len(txt)} vs room {room}: {txt!r}")
    print(f"\n{base}: {'ALL FIT' if overflow == 0 else f'{overflow} overflow(s) (Step-3 expand)'}")
    return 1 if overflow else 0


if __name__ == "__main__":
    raise SystemExit(main())
