# Menu & item translation — reproducible pipeline (SOLVED end-to-end)

This documents the **working, headless-validated** pipeline for translating Grandia:
Digital Museum's **system menus** (the field command menu, status, item/equip actions,
magic/level-up messages) to English. It is a sibling track to the dialogue work; all
menu code/artifacts live under `menus/`.

> **Complete build:** the whole menu/item translation now assembles into one icon-safe disc via
> `python3 menus/build_full_disc.py output/menu-NNN` (current: `output/menu-020`). It combines the
> label pipeline below + item LIST names (WDATA sec2, in place) + 16x16 names/descriptions (WDATA
> packed icon-safe + FIELD/TEXT2 + BATLE/TEXT2 relocated). See
> `docs/item-names-investigation-HANDOFF.md` for the icon-safe `pack_wdata` technique and the two
> field-width limits (list columns 9/12 chars; description box ≤37 chars).

## Primary method — the upstream menu editors (full mixed-case words)
The upstream GrandiaTranslation tools (TrekkiesUnite lineage) already ship purpose-built
editors for these files — `CMDMNFileEditor` (command menu), plus `SHOPFileEditor`,
`SVLDFileEditor` (save/load), `CNFIGFileEditor`, `ITGETFileEditor`, `BBGFileReconstructor`
(battle). `CMDMNFileEditor` is **Digital-Museum-aware** (`isDigitalMuseum` adds the 44-byte
offset; `MEM_OFFSET_START = 0x060B2000` = the verified load address) and is the right tool:
- it writes English in the **8x16 ASCII font** (`03` + ASCII + `00`) → real **mixed case**
  ("Items", "Equip", "Magic", "Moves", "Status", "Discard", …; even the party **Names**),
- it **grows** strings and **auto-repoints** the pointer table (scans the file for `060B`/`060C`
  HWRAM pointers and shifts every one past the edit by the byte delta),
- English values come from `translation.properties` (`cmdmn.*`), the official localization.

Upstream ships only Swing GUIs, so gdm-max adds a headless CLI
(`tools/patches/04-add-menu-editor-cli.patch` → `com.grandia.cli.MenuEditorCLI`).

### TL;DR (the recipe)
```
# 0. one-time: tools/setup.sh clones upstream + applies tools/patches/*.patch + mvn package
# 1. extract the menu module from the JP disc
python3 src/iso.py extract "input/...(Track 1).bin" CMDMN.BIN menus/extracted/CMDMN.BIN

# 2. translate via the upstream editor (grows + repoints; reads translation.properties)
cd tools/vendor/GrandiaTranslation/GrandiaTranslationTools
CP="target/classes:$(mvn -q dependency:build-classpath -Dmdep.outputFile=/dev/stdout)"
java -cp "$CP" com.grandia.cli.MenuEditorCLI cmdmn \
    "$REPO/menus/extracted/CMDMN.BIN" "$REPO/menus/build/upstream/" dm

# 3. inject into the disc (handles GROWN files: updates the ISO dir-record size too)
python3 menus/build_disc.py --name CMDMN.BIN --file menus/build/upstream/CMDMN.BIN \
    --out output/menu-NNN

# 4. validate headlessly (open the menu from a field savestate, screenshot)
tools/ymir-harness/build/jinloop-harness --bios "$BIOS" \
    --disc output/menu-NNN/Grandia-DM-patched.cue --state "$STATE" \
    --out menus/work/proof/report.json --script <plan.json: idle, press "A", idle> \
    --png-dir menus/work/proof/frames --png-every 30
```
Proof: `docs/menus/proof-menu-Items.png` — "Items" / "GOLD PCS" / Justin·Sue·Feena, mixed case.

> **Note on growth & disc layout:** a grown menu file must still fit its original *sector span*
> (CMDMN: 46 sectors / 94208 B; the upstream output is ~92.8 KB, fine) and `menus/build_disc.py`
> updates the ISO9660 directory-record size so the loader reads every byte. If a file ever grows
> past its span it needs relocation (like the MDT path), not this in-place write.

## Item & magic names + DM gallery labels — `/FIELD/WDATA.DAT` (own tool)
The system-menu *labels* are in CMDMN etc., but **item / magic / skill names, their descriptions,
and the DM museum gallery labels** live in `/FIELD/WDATA.DAT` (loads to LWRAM `0x002F0000`). There
is no upstream editor for it, so gdm-max has `menus/wdata.py`.

Format (RE'd): a **13-entry big-endian u32 section-offset table at file `0x0`**, then sections of
consecutive **null-terminated** strings the engine walks **by index** (Nth string = N nulls in;
no absolute pointers). Names render via the 8x16 ASCII font → mixed case. Sections:
`[3]=0x4C44` item/magic names, `[4]=0x57B0` gallery labels (映写室/図書室/資料室/シアター = Screening
Room / Library / Archives / Theater exhibits), `[6..]` descriptions. Placeholders read 禁/きんし
(disabled slots — skip).

Because strings are index-walked, `wdata.py` **grows** a name (real item names need it: 力の種 = 5
bytes → "Power Seed" = 13) by splicing the new bytes and **bumping every header section-offset that
starts after the edit** by the byte delta; within-section indexing is preserved (null count
unchanged). Verified: `selftest` round-trips byte-identical; an 8-seed edit grows the file +37 B,
the seeds decode correctly, and every later section is byte-identical after the shift. Must still
fit the file's sector span (27 sectors).
```
python3 menus/wdata.py dump  menus/extracted/WDATA.DAT          # list strings
python3 menus/wdata.py build menus/extracted/WDATA.DAT out.DAT map.json   # {"0x0552D":"Power Seed",...}
python3 menus/build_disc.py --out output/menu-NNN --patch WDATA.DAT=out.DAT [--patch ...]
```
**Item/magic names DONE** (266 entries, Grandia canon): translations in `menus/wdata_items.py`
(also merged into `dictionary/terms.json` for project-wide consistency). Full English grows the file
+1376 B → **28 sectors > its 27-sector span**, so WDATA is **relocated** with the proven
`src/relayout.py` (append at track end, repoint the directory record LBA+size, bump PVD volume size —
the same method verified for dialogue MDTs):
```
python3 menus/wdata.py build menus/extracted/WDATA.DAT menus/build/upstream/WDATA.DAT <map.json>
python3 menus/build_disc.py --out output/menu-NNN --patch CMDMN.BIN=... (the 5 in-place files)
python3 src/relayout.py --bin output/menu-NNN/Track1.bin --name WDATA.DAT \
    --mdt menus/build/upstream/WDATA.DAT --out output/menu-NNN/Track1.relocated.bin
```
Verified by re-extracting WDATA from the relocated disc (all item names decode in full English).

### WDATA.DAT full section map (header[0..12], text sections in **bold**)
| sec | file off | entries | content |
|----|----------|---------|---------|
| 0,1,2 | 0x34 / 0x3E28 / 0x3F28 | — | binary stat/record data (not text) |
| **3** | 0x4C44 | 266 | **item/weapon/armor/accessory/magic-item names** ✅ DONE |
| **4** | 0x57B0 | 288 | **item descriptions + DM exhibit-menu labels** — ✅ DONE (`menus/wdata_desc4.py`; machine-assisted prose) |
| 5 | 0x6EAC | — | binary |
| **7** | 0xAA00 | 117 | **magic/move names** (Burn/Howl families, Refresh, Gravity, Diggin', character moves) — ✅ DONE (`menus/wdata_magic.py`; 30 transliterated spell names flagged in exceptions.json for canon review) |
| **8** | 0xAD48 | 118 | **magic/move descriptions** — ✅ DONE (`menus/wdata_desc8.py`; machine-assisted prose, review recommended) |
| 6,9,10,11,12 | … | — | binary |

**WDATA.DAT is now fully English** — all 789 text entries across sec3/4/7/8 (names + descriptions +
DM exhibit labels) translate with 0 unmapped / 0 residual Japanese. Build the whole map reproducibly
with `python3 menus/build_wdata_map.py` (walks each section, applies `wdata_items`/`wdata_desc4`/
`wdata_magic`/`wdata_desc8`), then `wdata.py build` + relocate. Descriptions (sec4/sec8) are
machine-assisted prose; 30 uncertain spell-name transliterations are flagged in exceptions.json.
In-emulator confirm needs an item/magic-screen savestate (`docs/VALIDATION-TODO.md` §2b).

## Fallback method — equal-length, in place (no Java, no growth)
`menus/build_cmdmn.py` + `menus/cmdmn_table.py` patch strings **equal byte length** using
UPPERCASE page-0 single-byte glyphs (`menus/page0.py`), then `src/inject.py` writes them in
place. No pointer changes, but UPPERCASE-only and tight budgets force abbreviations
(ITEM/GEAR/DROP). Use only for fields the upstream editor doesn't cover, or to sanity-check.
First proof of this path: `docs/menus/proof-menu-ITEM.png`.

## Key findings (the why)

1. **Menus are font-rendered, not graphics.** Opening the field menu (button **A**) in YMIR
   shows 道具/ゴールド/STATUS as live text. So menus are translatable like dialogue — and the
   game is the *full Grandia engine* (party = Justin/Sue/Feena/Gadwin/Rapp/Milda/Guido/Liete),
   so the **official Grandia localization (== TrekkiesUnite Saturn patch) terms apply directly**.

2. **The field command menu lives in `/FIELD/CMDMN.BIN`** ("CoMmanD MeNu"), **uncompressed**.
   Its string table sits near the end (file ~`0x16060`). Strings are **null-terminated** and
   stored consecutively; a pointer table (absolute addresses, fixed load) points to group
   starts and the engine **null-walks** the entries within a group.
   - It loads **contiguously to WRAM `0x060B2000`** (verified: whole-file byte match), i.e.
     file offset `F` ↔ WRAM `0x060B2000 + F`.
   - The string region is at WRAM `0x060C8000`+. Find live menu text by dumping WRAM
     (`--dump-wram`) and decoding with `menus/scan_text.py`.

3. **Menus RELOAD from disc on open.** A WRAM injection of the patched strings is *overwritten*
   when you open the menu (the engine re-reads CMDMN from the disc). **Therefore patch the DISC,
   not WRAM** — the opposite of the baked-in dialogue case. (Confirmed: inject → open → the slot
   reverts to 道具; disc-patch → open → renders ITEM.) This is *good news*: a normal player on a
   fresh boot sees the English menus with no savestate trickery.

4. **Growth IS possible — the upstream editor repoints.** CMDMN's strings are referenced by an
   absolute-pointer table (loaded at `0x060B2000`); the engine null-walks within a group. Growing
   a string shifts everything after it, but `CMDMNFileEditor` rebuilds the table automatically
   (scans for `060B`/`060C` pointers, shifts each past the edit by the delta), so **full words
   fit**. The only hard limit is the file's **sector span** (don't overrun the next file). The
   earlier worry that "menu growth freezes" applies to the *in-MDT* names layer
   (`step3-box-overflow-finding`), where there is no repointer — not to CMDMN via this tool.

5. **English uses the 8x16 ASCII font → mixed case.** The editor writes `03` + ASCII + `00`, so
   menus read "Items"/"Equip"/"Discard", not uppercase abbreviations. (The fallback path below,
   which can't grow, uses 16x16 page-0 single-byte **UPPERCASE** A-Z/0-9/`! ? : ・ -` — no lowercase
   — space-padded to the exact JP byte length.)

## Files
- `tools/patches/04-add-menu-editor-cli.patch` — headless `com.grandia.cli.MenuEditorCLI`
  wrapper over the upstream editors (applied by `tools/setup.sh`).
- `menus/build_disc.py` — inject a (grown) menu file into Track1 + cue, updating the ISO
  directory-record size (handles upstream-grown files).
- `menus/scan_text.py` — decode Grandia text runs in any binary/WRAM dump (find string tables).
- `menus/page0.py`, `menus/cmdmn_table.py`, `menus/build_cmdmn.py` — the **fallback** equal-length
  path (no Java/growth); see above.
- `menus/extracted/`, `menus/build/`, `menus/work/` — scratch (gitignored): JP binaries, editor
  output, harness runs/WRAM dumps/proof frames.

## Verification
Re-extract CMDMN from the patched Track1 and decode — strings read back as mixed-case English
(Items, Equip, Magic, Moves, Status, Discard, …) and the party Names (Justin/Sue/Feena).
Visual proof: `docs/menus/proof-menu-Items.png` (upstream) and `proof-menu-ITEM.png` (fallback).

## What's NOT yet located / done (next targets)
The field command menu (CMDMN.BIN) is **done** via the upstream editor. Next, each has an upstream
editor to drive through `MenuEditorCLI` (extend it the same way) + `translation.properties` values:
- **Shop** → `SHOPFileEditor` (`/FIELD/SHOP.BIN`).
- **Save/Load** → `SVLDFileEditor` (`SVLD.BIN` / `SAVER.BIN` / `SVRDT.DAT`).
- **Config** → `CNFIGFileEditor` (`CNFIG.BIN`).
- **Item-get / item names** → `ITGETFileEditor` (`ITGET.BIN`); confirm where inventory item names live.
- **Battle** → `BBGFileReconstructor` (`BATLE/*.BBG`; the system text is bundled per-background).
For anything without an upstream editor: dump WRAM on that screen → `menus/scan_text.py` to find the
live string table → trace to its disc file (decompress if needed) → translate → `build_disc.py` →
harness-verify. See `docs/menus-handoff.md`.

## Battle text — `/BATLE/TEXT2.BIN` (resident; WDATA-shaped)
The live battle UI text is in **`/BATLE/TEXT2.BIN`** (the same text is also bundled into each
`BATLE/*.BBG`, but TEXT2.BIN is the single resident file — far simpler than editing 33 BBGs).
Same format as WDATA (header section table + index-walked null-terminated strings), so `wdata.py`
handles it (the header length is now auto-detected: 11 entries here vs 13 in WDATA). Sections:
| sec | content | translator |
|----|---------|------------|
| 3  | battle command menu (Attack/Defend/Magic/Item/Special/Combo/Evade/Wait/K.O./Command), skill-learn, escape messages, weapon/element types | `menus/battle_text.py` (CMD) |
| 5  | **~200 monster/boss names** (the bestiary) | `menus/battle_text.py` (MON) |
| 10 | AI tactics menu (Thrift/Boost/Passive/Trust/Safe/All-out/Wicked) | `menus/battle_text.py` (AI) |
| 4/6/8/9 | spell names / move descriptions / item names / exhibit labels — DUPLICATE of WDATA | reuse `wdata_magic`/`wdata_desc8`/`wdata_items`/`wdata_desc4` |

All 1130 text entries translated (0 unmapped). Full English grows it +7754 B (15 sectors > its
11-sector span), so it is **relocated** — `relayout.py` is now **path-aware** (`--name /BATLE/TEXT2.BIN`)
to disambiguate from `/FIELD/TEXT2.BIN`. Build recipe (full combined disc `output/menu-008`):
```
python3 menus/build_text2_map.py
python3 menus/wdata.py build menus/extracted/BATLE_TEXT2.BIN menus/build/upstream/BATLE_TEXT2.BIN menus/work/text2_map.json
python3 menus/build_disc.py --out output/menu-NNN --patch CMDMN.BIN=... (the 5 in-place files)
python3 src/relayout.py --bin .../Track1.bin --name WDATA.DAT       --mdt .../WDATA.DAT       --out .../t.bin && mv
python3 src/relayout.py --bin .../Track1.bin --name /BATLE/TEXT2.BIN --mdt .../BATLE_TEXT2.BIN --out .../t.bin && mv
```
Verified by re-extracting TEXT2 from the relocated disc (Attack/Defend/Special/King Horn/All-out…
decode in English; WDATA + TEXT2 relocate sequentially with no overlap). Monster names + command
labels merged into terms.json; messages/AI prose are machine-assisted. In-emulator confirm needs a
battle savestate. **BBG battle backgrounds are NOT edited** (the shared text lives in TEXT2.BIN).

## Field item DB — `/FIELD/TEXT2.BIN` (full equipment list)
`/FIELD/TEXT2.BIN` is WDATA-shaped and parallels `/BATLE/TEXT2.BIN`, but its sec8/sec9 are the
**complete field item database** (482 item names + 474 descriptions) — a superset of WDATA's 266,
including every weapon/armor/accessory and all story/key items (Spirit Stone, Hero's Bracelet,
Master Key, letters, keys…). Sec 3/4/5/6/10 duplicate BATLE/TEXT2 (commands/spells/monsters/
move-desc/AI) and reuse those translators.
- **sec8 names: DONE** — `menus/field_items.py` (324 new + reuse). 482/482 mapped; merged to terms.json.
- **sec9 descriptions: DONE** — `menus/field_desc.py` (314 new: weapon/armor stat+flavor, key-item
  text, skill-EXP items) + reuse of `wdata_desc4`/`wdata_desc8`. 1540/1540 entries mapped. Machine-assisted prose.
Built (names + dup sections) and relocated; combined disc `output/menu-009` now relocates THREE
files sequentially with no overlap: WDATA.DAT, /BATLE/TEXT2.BIN, /FIELD/TEXT2.BIN.

### Casino (investigated)
The game-room AREA menus (game select, prize, controls) are **already translated** in the dialogue
pipeline (`script/E814_en.py`). The in-minigame betting/coin UI is baked into the **compressed,
streamed `GM3.STZ`** (garbage when decoded) — out of scope for string-table patching. So there is no
casino menu `.BIN` to run through this pipeline. (The casino/theater **exit bug** in
`VALIDATION-TODO §7` is a separate event-flow issue, not a text problem.)
