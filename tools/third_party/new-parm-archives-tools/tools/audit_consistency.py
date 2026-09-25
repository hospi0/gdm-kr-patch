#!/usr/bin/env python3
"""Lane R audit pass 3: cross-surface term-consistency sweep.

Gathers every JP->EN mapping the project ships across all surfaces (dictionary,
WDATA item names, DICDT monster names/descriptions, TEXT2 battle strings, viewer
labels, door names, script/*_en.py inline, theater captions) and flags:

  1. CONFLICT: same JP key rendered with different EN across surfaces (incl. vs
     the canonical dictionary/terms.json).
  2. EN-FORM DRIFT: known localization-variant pairs that must be uniform
     (Ax/Axe, Feena/Fena/Fina, casing, apostrophe style) present in >1 form.

Output: a text report to stdout.  AUDIT-ONLY; reads project data, writes nothing.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(rel):
    p = ROOT / rel
    if not p.exists():
        return None
    return json.loads(p.read_text())


# ---- gather (jp, en, surface) triples -------------------------------------
triples = []  # (jp, en, surface)


def add(jp, en, surface):
    if jp is None or en is None:
        return
    jp = jp.strip()
    en = en.strip()
    if not jp or not en:
        return
    triples.append((jp, en, surface))


# 1. canonical dictionary
d = load_json("dictionary/terms.json")
if d:
    for jp, v in d["terms"].items():
        add(jp, v.get("en"), "terms.json")

# 2. docs/menus JSON EN lists (idx/jp/en)
for fn in ("monster-names-en.json", "monster-locales-en.json",
           "monster-uilabels-en.json"):
    arr = load_json(f"docs/menus/{fn}")
    if arr:
        for e in arr:
            add(e.get("jp"), e.get("en"), fn)

# monster descriptions (jp keyed by idx in two files)
mn_jp = load_json("docs/menus/monster-descriptions-jp.json")
mn_en = load_json("docs/menus/monster-descriptions-en.json")

# 3. design-materials (menu + slots)
dm = load_json("docs/menus/design-materials-en.json")
if dm:
    for e in dm.get("menu", []):
        add(e.get("jp"), e.get("en"), "design-materials.menu")
    for slot in dm.get("slots", []):
        for e in slot:
            add(e.get("jp"), e.get("en"), "design-materials.slots")

# 4. WDATA item / magic / desc translators
def load_py_dict(rel, names):
    p = ROOT / rel
    if not p.exists():
        return {}
    ns = {"__file__": str(p)}   # some translators use Path(__file__) at import
    try:
        exec(compile(p.read_text(), str(p), "exec"), ns)
    except Exception as e:
        print(f"# WARN: could not exec {rel}: {e}", file=sys.stderr)
        return {}
    out = {}
    for n in names:
        v = ns.get(n)
        if isinstance(v, dict):
            out[n] = v
    return out


for rel, names in [
    ("menus/wdata_items.py", ["TERMS"]),
    ("menus/wdata_magic.py", ["TERMS", "MAGIC", "MOVES"]),
    ("menus/battle_text.py", ["CMD", "MON", "AI"]),
    ("menus/cmdmn_table.py", ["TABLE", "TERMS", "PAGE0"]),
    ("menus/field_items.py", ["NEW"]),          # Lane X3: TEXT2 sec8 field item DB
]:
    dd = load_py_dict(rel, names)
    for nm, mp in dd.items():
        surface = f"{Path(rel).name}:{nm}"
        for jp, en in mp.items():
            if isinstance(en, str):
                add(jp, en, surface)

# 5. theater caption titles + speaker names
for i in range(1, 6):
    cj = load_json(f"src/theater/captions/drama{i}.json")
    if cj:
        add(cj.get("title_jp"), cj.get("title_en"), f"drama{i}.title")

# ---- 1. CONFLICT detection -------------------------------------------------
by_jp = defaultdict(set)
by_jp_surfaces = defaultdict(list)
for jp, en, s in triples:
    by_jp[jp].add(en)
    by_jp_surfaces[jp].append((en, s))

print("=" * 70)
print("PASS 1: SAME JP KEY -> DIFFERENT EN ACROSS SURFACES")
print("=" * 70)
conflicts = 0
for jp in sorted(by_jp):
    ens = by_jp[jp]
    if len(ens) > 1:
        # ignore pure trailing-space / case-identical dupes? keep case, show
        conflicts += 1
        print(f"\nJP {jp!r}:")
        for en, s in sorted(set(by_jp_surfaces[jp])):
            print(f"    {en!r:40} <- {s}")
print(f"\n[{conflicts} conflicting JP keys]")

# ---- 2. EN-FORM DRIFT ------------------------------------------------------
print("\n" + "=" * 70)
print("PASS 2: EN-FORM DRIFT (variant spellings that must be uniform)")
print("=" * 70)

# collect all EN strings + where they appear
en_where = defaultdict(set)
for jp, en, s in triples:
    en_where[en].add(s)

all_en = list(en_where)
alltext = "\n".join(all_en)

# character-name variants
name_variants = {
    "Feena": [r"\bFena\b", r"\bFina\b", r"\bFeina\b"],
    "Justin": [r"\bJastin\b", r"\bJustine\b"],
    "Gadwin": [r"\bGadowin\b"],
    "Mullen": [r"\bMuellen\b", r"\bMyullen\b"],
    "Liete": [r"\bRiete\b", r"\bLeite\b"],
    "Puffy": [r"\bPui\b", r"\bPuui\b"],
}
for canon, wrong in name_variants.items():
    for w in wrong:
        for en in all_en:
            if re.search(w, en):
                print(f"  NAME DRIFT: {en!r} (expected canonical {canon!r}) in {sorted(en_where[en])}")

# Ax vs Axe
ax = [e for e in all_en if re.search(r"\bAx\b", e)]
axe = [e for e in all_en if re.search(r"\bAxe\b", e)]
if ax and axe:
    print(f"  AX/AXE DRIFT: 'Ax' forms={ax}  ||  'Axe' forms={axe}")
elif axe:
    print(f"  AX/AXE: only 'Axe' forms present: {axe}")

# Robe of the X vs X Robe (already flagged via conflicts but surface here too)
# generic: same word set different order — skip (noisy)

# apostrophe style: straight ' vs curly ’
curly = [e for e in all_en if "’" in e]
if curly:
    print(f"  APOSTROPHE: curly-quote forms present (prefer straight '): {curly}")

# casing: same lowercased EN with different casings across surfaces
lower_map = defaultdict(set)
for en in all_en:
    lower_map[en.lower()].add(en)
for lo, forms in sorted(lower_map.items()):
    if len(forms) > 1:
        print(f"  CASE DRIFT: {sorted(forms)} in " +
              ", ".join(sorted({s for f in forms for s in en_where[f]})))

print(f"\n[total triples gathered: {len(triples)} across "
      f"{len({s for _,_,s in triples})} surfaces]")

# ---- 3. sec2 LIST forms vs the G1 rip (Lane X3, Wave-2 consistency pass) ---
print("\n" + "=" * 70)
print("PASS 3: WDATA sec2 LIST forms vs docs/menus/g1-item-list-aligned.json")
print("=" * 70)
g1items = load_json("docs/menus/g1-item-list-aligned.json")
g1_list = {}
g1_full = {}
if g1items:
    for it in g1items.get("items", []):
        if it.get("jp"):
            if it.get("en_list"):
                g1_list.setdefault(it["jp"], it["en_list"])
            if it.get("en_full"):
                g1_full.setdefault(it["jp"], it["en_full"])
tsv = ROOT / "menus/work/sec2_review.tsv"
n_ok = n_diff = n_dm = 0
if tsv.exists():
    for ln in tsv.read_text().splitlines()[1:]:
        f = ln.split("\t")
        if len(f) < 5:
            continue
        idx, jp, full_en, disp, source = f[0], f[1], f[2], f[3], f[4]
        g1 = g1_list.get(jp)
        if g1 is None:
            n_dm += 1
            continue
        if disp == g1:
            n_ok += 1
        else:
            n_diff += 1
            print(f"  LIST DRIFT idx {idx}: {jp!r} ships {disp!r} != G1 {g1!r} (src {source})")
    print(f"  [{n_ok} match G1, {n_diff} drift, {n_dm} DM-only/authored]")
else:
    print("  (menus/work/sec2_review.tsv missing — run menus/sec2_translate.py first)")

# ---- 4. terms.json vs the G1 rips (full names / spells / enemies) ----------
print("\n" + "=" * 70)
print("PASS 4: dictionary/terms.json vs the G1 disc rips")
print("=" * 70)
proj = {}
if d:
    for jp, v in d["terms"].items():
        if v.get("en"):
            proj[jp] = v["en"]
g1t = load_json("docs/menus/g1-terms-aligned.json")
g1ext = load_json("docs/menus/g1-terms-aligned-ext.json")
checked = drift = 0
seen_pairs = set()
def chk(jp, g1_en, src):
    global checked, drift
    en = proj.get(jp)
    if en is None or not g1_en or (jp, src) in seen_pairs:
        return
    seen_pairs.add((jp, src))
    checked += 1
    if en != g1_en:
        drift += 1
        print(f"  G1 DRIFT: {jp!r} terms.json {en!r} != G1 {g1_en!r}  [{src}]")
if g1t:
    for t in g1t.get("terms", []):
        chk(t.get("jp"), t.get("en"), f"g1-terms:{t.get('category')}")
for jp, full in g1_full.items():
    chk(jp, full, "g1-item-list:en_full")
if g1ext:
    for t in g1ext.get("spell_list_forms", []):
        chk(t.get("jp"), t.get("en"), "g1-ext:spell_list")
print(f"  [{checked} JP keys checked against G1, {drift} drift]")

# ---- 5. BBG sec2 battle-message table vs its TEXT2 sibling ------------------
print("\n" + "=" * 70)
print("PASS 5: pN7 BBG battle-message TRANS vs menus/work/text2_map.json (mirror gate)")
print("=" * 70)
t2 = load_json("menus/work/text2_map.json") or {}
t2vals = set(t2.values())
try:
    sys.path.insert(0, str(ROOT / "tools"))
    import importlib
    pn7 = importlib.import_module("pN7_battle_msgtable")
    missing = [v for k, v in sorted(pn7.TRANS.items())
               if v not in t2vals and v != "Sample"]
    if missing:
        for v in missing:
            print(f"  MIRROR DRIFT: pN7 TRANS {v!r} not present in text2_map.json values")
    print(f"  [{len(pn7.TRANS)} pN7 entries, {len(missing)} not mirrored in TEXT2]")
except Exception as e:  # pragma: no cover
    print(f"  (could not import pN7_battle_msgtable: {e})")
