# Museum VIEWER subsystems — format RE + black-screen root cause (P3)

Reverse-engineering result for the four museum **viewers** launched from the (already-English)
terminal menus, plus the **ending credits** roll. These are a **separate UI subsystem** from the
SCNRL/MDT dialogue text (memory `museum-viewers-separate-subsystem`) — the same engine *class* as
the Game-Room minigames (`docs/mgame-format.md`), but with important differences documented here.

Tooling reused: `tools/mg_stb.py` (offset-table archive), `tools/mg_gfx.py` (tile/bitmap→PNG),
the jin-loop harness (`tools/ymir-harness`, now also dumps **final CRAM** → `cram-final.bin`).

## TL;DR — the key feasibility question, answered

**The viewer text is pre-rendered BITMAP art, NOT a font+text-index.** No viewer file contains the
on-screen Japanese as SJIS, and there is no shared glyph-font + index table. `EDFNT.DAT` — the
plan's "candidate shared viewer font" — is **not a font**: it is a container of **pre-rendered
text-line bitmaps** (one whole line of text per slot). So "translating" a viewer = **redrawing the
text bitmaps** (the minigame path). The good news: the **credits (EDFNT) are uncompressed** and the
**monster art (MT00x) is uncompressed**, so large parts need no codec at all.

| Subsystem | Overlay (`.BIN`) | Data | Format | Translatability |
|---|---|---|---|---|
| **Ending credits** | — | `FIELD/EDFNT.DAT` (285 KB) | **uncompressed 4bpp**, offset-table archive of 124 text-line strips, all **24 px tall**, width = `slot_size/12` | **EASY — decode→edit→`mg_stb repack` (constant-size), disc-patchable now** |
| **Monster Encyclopedia** | `MONST.BIN` (236 KB) | `MT000…MT00F`+`MT0FF` art; **`DICDT.DAT`** names | overlay @ HWRAM `0x0602c7c0`; `MT0xx` = **uncompressed 8bpp** + 512-B palette; **names = `DICDT.DAT` packed list, standard Grandia 16×16 tbl** | art plain 8bpp; **names TRANSLATABLE (Grandia tbl, see below)**. Black screen = empty bestiary (not a bug) |
| **Design Materials** | `MATER.BIN` (46 KB) | **`MTMES.DAT`** (1004 B: 6×17 tbl TEXT strings), **`MTOUT.DAT`** (bg + UI + 6 menu labels), `MT{cat}{page}.BIN` = the 6×17 plate-art banks (that's why MT000–MT5FF exist), `SYS_R.STB` | overlay @ HWRAM `0x0602c018`; loads its data files by NAME (`MTOUT.DAT`/`MTMES.DAT`/`SYS_R.STB` strings at `MATER.BIN` 0xad0c/0xad18/0xad24; `MT000.BIN`/`MTXT0.BIN` templates at 0xb146/0xb136) via the file-index table | **FULLY TRANSLATED (Lane F + Lane K, 2026-07)** — thumbnail-page header tabs + per-plate captions English via `tools/viewer_mtmes.py` (FULL-WIDTH tbl; see section below); category-select MENU labels (MTOUT slot 3) + baked 設定資料集→DESIGN MATERIALS banner + selected-label bars (MTOUT slot 2 sub-blob 6) English via `tools/viewer_mtout_gfx.py` → `patches/viewer/MTOUT.DAT.xdelta3` |
| **Expression Collection** | `FACER.BIN` (46 KB) | `FACE.DAT` (4.3 MB), `FACE0/1/2.DAT` | overlay @ `0x0602c018` (same template as MATER); `FACE0.DAT` = offset-table of (512-B palette, image) | face/expression art (bitmaps) |
| **Save-data Browser** | `SAVER.BIN` (66 KB) | `SVLD.BIN`, `SVRBG.DAT`, `SVRDT.DAT` | (newly identified — the `SV*` family) | the in-museum save-scene selector; `GM3.STZ`/`.IDX` hold the actual scene-save payloads (248 MB) |

Each viewer follows the **same idiom as the minigames**: a dedicated `XXX.BIN` SH-2 **overlay**
(loads to HWRAM `0x0602xxxx`) + dedicated data files — exactly like `KNPAN.BIN`/`KNPAN.DAT`.
`MATER.BIN` and `FACER.BIN` share a byte-identical overlay header/prologue (same build template).

## ★ Compressed viewers use the SAME ST1 codec as the minigames (CRACKED)

The compressed-overlay viewers (Design Materials, Expressions, Save-browser, and the Monster
viewer's UI) are decompressed by the **same resident `0x0601xxxx` engine as the Game-Room
minigames** — so `tools/mg_codec.py` + `tools/mg_tree.py` apply directly. Evidence:

- **Static:** `MATER.BIN` (the design overlay, loads to HWRAM `0x0602c018`) calls resident
  functions via two jump-tables (`0x0601000c`, `0x060100e0`) whose entries land in
  `0x06013xxx–0x06015xxx` — the minigame engine range (chunk-loop caller `0x06013F90`, codec
  `0x06015DF0`, tree-builders `0x0601401A/491C/44EE`). That engine code is **resident and
  byte-identical** in the museum HWRAM dumps (`0x06013F90` prologue matches).
- **Live + decoded byte-exact:** breakpointing the chunk-loop caller **`0x06013F90`** on monster-
  viewer entry (`--bp`, savestate 1) caught one call: **R4(src)=`0x002BF3D0`** (LWRAM blob),
  R5=`0x00230000` (dest), R6=`0x06028800` (the Huffman tree base). Snapshotting LWRAM at the hit
  (`--dump-on-bp`) and running `mg_tree.decode_blob(lwram, 0xBF3D0, hwram=<museum dump>)` decodes
  it cleanly: **count=3 chunks, treedef `1100 8000…`, modes 1/1/0, roots 0x810/0x810/0x808 →
  36 864 bytes**, a **2-colour (0x7F/0) UI/font mask** (the viewer's static UI, which loads even
  with an empty bestiary). This is the **same chunk-stream framing** (`mg_tree.decode_blob`) as
  KNPAN — no new codec needed.

**Method to localise + decode any viewer's graphics** (reuse, no new codec): `--bp 0x06013F90` on a
savestate that *enters* the viewer → read **R4 = blob source** (and R5 dest) from `report.json`
`bp_trace`; `--dump-on-bp` to snapshot LWRAM; `mg_tree.decode_blob(lwram, R4-0x200000)`. Repeat for
Design Materials / Expressions once a savestate that opens them exists (assets stay resident, so the
caller only fires on viewer ENTRY — scrolling an already-open viewer does NOT re-fire it). Final
geometry (sprite dims/bpp/tiling) for re-authoring comes from the VDP draw command at display time
(needs the viewer actually showing content, e.g. a populated bestiary) — exactly the per-asset
"layout mapping" the minigame logos also needed. Re-encode/splice = `tools/mg_splice.py`.

## EDFNT.DAT — the credits (fully cracked, uncompressed)

Parses with `mg_stb.py list` as a BE-u32 offset-table archive: `table_size=0x1f4` → 125 slots, 124
used. **Every slot is a 4bpp, 24-px-tall pre-rendered text strip**; render with
`mg_gfx.py SLOT.bin out.png --bpp 4 --bitmap W 24` where `W = slot_size*2/24 = slot_size/12`
(every slot size is divisible by 12; only the final slot 124 is padding). ~77 % of each slot is
value 0 = transparent; strokes use 4bpp values up to 15 (anti-aliased).

Content = the full **cast + staff credits roll**, e.g.:
- slot 0 `声優` (Voice cast); 1 `ジャスティン / 瀧本 富士子`; 2 `フィーナ / 日高 のり子`; 3 `スー / 西原 久美子` … (character / VA pairs)
- slot 13 `設定／デザイン提供`; 20 `グランディア デジタルミュージアム`; 21 `制作スタッフ`; 22 `メインプログラム`; 24 `戦闘プログラム`; 30 `ミニゲーム制作`
- slots 32–38 = the **minigame titles** (cross-references the minigame names): `お盆でゴン`,
  `スーあやうし！ガンツの花嫁大作戦`, `フィーナのぱんつ`, `男の熱血100億番勝負`, `甲板掃除 -Remix-`,
  `早食い王 -グランディア杯-`, `バールの逆襲`.

Contact sheets: `work/museum/edfnt_page{0..3}.png`. **Constant-size repack works** (each English
strip authored at the original slot's width×24, transparent-padded), so EDFNT is **disc-patchable
in place** with no relocation. This is the cleanest PoC target offline; in-game proof needs the
credits screen reached (trigger TBD — likely post-ending or a menu; ask the user for a savestate).

## MT00x — monster portrait banks (uncompressed 8bpp)

`mg_stb.py list MT000.BIN` → 2 slots: slot 0 = 315 392-B image, slot 1 = 512-B BGR555 palette.
The image is **uncompressed 8bpp**: byte `0x27` is the background fill (50–93 % per region, = white
`(248,248,248)` in the bank palette) with monster art drawn over it; 253 distinct values. (Exact
cell tiling not fully pinned — it renders banded as linear/16×16; irrelevant since the art is not
translated, only the names are.) 18 banks (`MT000`–`MT00F`, `MT0FF`) → the bestiary art.

## ★ Monster names — DICDT.DAT, standard Grandia encoding (TRANSLATABLE)

**Confirmed not-a-bug + names located** using the user's populated-bestiary savestates
(`saves/monster-book1-list`, `saves/monster-detail-redoni`): with monsters registered the viewer
renders perfectly — the book-1 list (青オニ/赤オニ/暴れカエル/…, locked entries blacked out) and the
detail page (名前/出現地/stats + sprite). The black screen was an **empty bestiary**, full stop.

The monster **names are NOT a custom viewer encoding** — they use the **standard Grandia 16×16 font
table** (`tools/vendor/.../Grandia16x16.tbl`), the SAME encoding as the item-name work
([[item-names-two-tables]]). Found by encoding the on-screen names with that tbl and locating them:
- **`/FIELD/DICDT.DAT`** ("dictionary data" = the encyclopedia's file) — a **packed, NUL-separated
  name list** at file `0x29c3c` (loads to LWRAM `0x240000`+`0x29c3c` = `0x269c3c`, matches the live
  copy). **169 monster names, 1194 bytes**, variable-width tbl encoding (kanji 2 B, kana 1 B).
  Decoded list → `docs/menus/monster-names-dicdt.json`. Preceded by an index/record table
  (`eb000000` header + repeated `d7e6aeb4ef…` placeholder records) — so length-changing edits need
  that index checked (safest first pass: tbl-ASCII names within budget; growth needs the index/
  pointer handling, à la the item-name tables).
- The same names also appear in **`/BATLE/M_DAT.BIN`** (battle monster records: name + stats +
  attack names like 子オニ投げ) — translating there would also fix in-battle names (bigger scope).
- The detail-page **sprite** is the **uncompressed MT00x** art (selecting a monster did NOT fire the
  `0x06013F90` codec → sprites are loaded uncompressed, only the UI/font is ST1-compressed).

→ **Monster names are translatable via the existing Grandia-tbl / dictionary pipeline** (run them
through `src/dict_cli.py` per CLAUDE.md rule 5). This is the most tractable real-viewer target.

### DONE — 169 names translated & PROVEN IN-GAME (`tools/dicdt.py`)
`tools/dicdt.py dump|patch` edits DICDT's section table: section 5 (names), section 6 (locales) are
packed NUL-separated, ordinal-indexed (no pointer table, no absolute refs → free to relocate; on a
size change `patch` rewrites the block and fixes later section offsets). **English encodes as
`0x03` (switch to the 8×16 half-width font) + ASCII** — the viewer honours it: **mixed-case,
lowercase, long names fit the list box** (the full-width 16×16 Roman in the tbl clips past ~9 chars).
All 169 translated, **139 aligned to the canonical dictionary** (`dictionary/terms.json`, official
Grandia loc — Rampage Frog/Ammonar/Otherworld Warrior/Boargon/…), 30 draft (Gaia* variants) flagged
in the review page `script/monster-names-review.html`. Validated in the harness on
`saves/monster-book1-list` (inject the patched DICDT at LWRAM `0x240000`, scroll → list redraws in
clean English): `docs/museum-gfx/monster-names-english-ingame.png`. Build path: `dicdt.py patch` →
`src/relayout.py --name DICDT.DAT` (grows section 5 1196→~2060 B, relocates the file).
**DONE (text):** section 4 labels, section 5 names, section 6 locales, **section 7 descriptions
(all 162 monsters / 493 lines translated + proven in-game, every line trimmed to ≤38 half-width
chars = the detail-box width; 40-char lines clip the last char)**. Encode = `0x03`+ASCII;
review pages `script/monster-{names,locales,descriptions}-review.html`.
### Stat-block labels (ステータス/レベル/たいきゅうりょく/…) — investigated, GRAPHICS (deferred)
The detail-page stat labels are **not editable text**. Confirmed via the harness on the populated
detail page (`work/museum/detail_v3/`, Blue Oni): they are **not tbl-encoded** in DICDT, MONST.BIN,
MT0xx, or WRAM (the only ステータス/レベル hits are description fragments in DICDT sec7). Only **one**
codec call (`0x06013F90`) fires for the whole guide, and its blob is the **gray rounded sprite-panel
mask** (2-colour, 192×192-ish), NOT the labels. So the labels are a **pre-rendered graphic** baked
into the book-page/parchment UI, drawn from an uncompressed source not in the obvious viewer files;
VDP2-VRAM tile renders were inconclusive (needs the exact tilemap/palette/cell format). **Translating
them = a dedicated graphics-RE + redraw task** (locate the parchment/label texture + format → redraw
8 labels → re-encode/patch), disproportionate to 8 short words whose meaning is clear from the
numbers. **Recommendation: defer**; the encyclopedia's meaningful text (names/labels/locales/493
descriptions) is done and proven.

**SHIPPED into the build:** `tools/build_dicdt.py` (driven by the committed
`docs/menus/monster-{uilabels,names,locales,descriptions}-en.json`) builds the English DICDT and is
wired into `tools/build_rc.py` step 3 (relocate into the final track). **`output/rc_20`** carries it;
verified on that RC track — the detail page renders English (`Blue Oni` / `Rama Mountains`).
**Cold-boot caveat for testers:** the game rebuilds its file-index table from the ISO dir at COLD
BOOT, so cold-boot (or a save made ON rc_20) shows English; an OLD savestate from a different build
keeps a stale table pointing at the original DICDT LBA (still vanilla JP there) — re-boot to pick up
the English copy. (Harness validation injects the corrected FAD at `0x06029b08`.)

**Remaining:** user review of the name/locale/description draft pages; (optional, later) the
stat-label graphics redraw; a real cold-boot smoke test of rc_20's encyclopedia in YMIR.

### ★ Shipping mechanism — DICDT is loaded via a FILE-INDEX TABLE, not the ISO path at use-time
The monster guide loads DICDT by a **resident file-index table** (HWRAM `0x06029b08`), each entry =
`[8-char name][FAD u32][size u32]` (DICDT = `"DICDTDAT"`, FAD `31035`=LBA 30885+150, size 186004).
That table is **built at COLD BOOT from the ISO directory** (the string `"DICDTDAT"` is not on disc
verbatim → it's assembled from ISO dir entries). Consequences:
- A grown DICDT does NOT fit in place (91-sector hole = +364 B; full English = +863 B, and DORAM.BIN
  starts immediately at the next LBA). So it must be **relocated** (`src/relayout.py --name DICDT.DAT`
  → appends at track end, updates the ISO dir entry).
- On a **cold boot** the table is rebuilt from the (relayout-updated) ISO dir → the game reads the
  relocated English DICDT automatically. **No code/LBA patch needed for a shipped disc.**
- A **savestate** has the OLD table baked in (from its original-disc boot), so harness validation
  against a relayout disc needs the table entry re-pointed: inject `BE32 FAD, BE32 size` at HWRAM
  `0x06029b08` (`work/museum/ftbl_patch.bin`) after LoadState. **Proven**: room save
  `saves/library-monster-table` + relayout disc + this FAD inject → open the guide → list, the
  "Monster Book 1" label, and the detail page all render English from the on-disc DICDT
  (`docs/museum-gfx/monster-{list,detail}-english-fromdisc.png` — "Name: Blue Oni / Habitat: Rama
  Mountains"). The far-LBA seek makes the load slow (~500 frames) — wait it out in nav scripts.
- For the main rc build: relayout DICDT into the track and confirm once via a cold boot (or the FAD
  inject). Other viewer files likely use the same table → same relocate-or-cold-boot rule.

## ★ Monster-Encyclopedia BLACK SCREEN — root cause

**Reproduced in the harness** (rc_15 disc + YMIR `1.savestate` at the Library monster terminal,
nav Down→C…). New evidence (this session):

1. **It is NOT a palette-application bug.** Final CRAM (`--dump-wram` now also writes
   `cram-final.bin`) is a **normal, populated palette** (67 % non-zero, valid colours) and is
   **byte-identical before launch and after** — the menu palette, never replaced. The screen is
   near-black with only faint art outlines, but the palette is fine.
2. **The viewer never loads its art.** The monster image (`0x27` fill) is **absent from VDP2 VRAM
   and from WRAM** (longest `0x27` run = 1–6 bytes vs the file's 159 752-byte fill). With a deeper
   nav the **`MONST.BIN` overlay does load** (its header `0602c7c0 0602c808…` appears at HWRAM
   `0x0602c000`) and the screen then goes **fully black** — overlay runs, but no monster bank is
   ever DMA'd in.
3. **It is NOT our patch / NOT a relocation bug.** `MONST.BIN`/`MT00x`/`EDFNT.DAT` are at
   **identical LBAs** on the original and rc_15 discs (we never patch FIELD viewer files). Booting
   the **original unpatched disc** with the same savestate+nav yields the **byte-identical** black
   screen and **byte-identical final CRAM**. So the translation work did **not** cause it
   (consistent with the launch bytecode being unchanged since pre-Phase-C).
4. **Leading explanation: content-gating (empty encyclopedia).** This game gates content behind
   event-VM unlock/save flags (memories `casino-minigames-coin-gated`,
   `minigame-logos-need-unlock-save`). The captured prompt is *"Select a monster book with the
   D-Pad, confirm with A/C — a list of monsters is shown."* The Design-Materials viewer (always-
   available content) renders fine; the Monster viewer launches its overlay but shows **no monster
   bank** — exactly what an **empty bestiary** (no monsters encountered in this save) would do.
   So the "black screen" is most likely **an empty viewer with this save**, not an engine break.

**To confirm/close:** drive the full interaction from a save with a **populated monster
encyclopedia** (monsters registered) — see "Asks" below. Repro dirs:
`work/museum/mon_blackscreen/` (faint-outline), `work/museum/mon_deep/` (overlay loads, full
black), `work/museum/mon_orig/` (original disc, identical).

## ★ Design Materials (設定資料集, MATER.BIN) — FULLY TRANSLATED (Lane F text + Lane K category page, 2026-07)

**The viewer's text is plain tbl TEXT after all** (not the ST1 blob) — two data files:

- **`/FIELD/MTMES.DAT`** (1004 B): header = 6 BE-u32 slot offsets; each slot = **17 NUL-separated
  Grandia-16×16-tbl strings**: `[0]` category title + `[1..16]` the 16 plate captions, NUL-padded to
  4-byte alignment. Categories: 美術設定1/2, モンスター設定, キャラクター設定1/2/3. The 16 captions map
  ordinally (row-major) to the thumbnail grid = art banks **`MT{cat}00..MT{cat}0F.BIN`** — the whole
  MT000–MT5FF family is the design-plate art (uncompressed 8bpp watercolor scans; the JP annotations
  visible on the plates are baked into the scans → not translatable).
- **`/FIELD/MTOUT.DAT`** (110644 B): 4 slots — `[0]` 512-B BGR555 palette, `[1]` 352×224 8bpp purple
  background, `[2]` tiled/atlas UI art (glyph atlas + banner sprites, format not fully RE'd),
  `[3]` (last, 68 B) the **6 category-select MENU labels** (NUL-separated tbl strings).

**Where each string renders + renderer quirks (all proven in-harness):**
| Element | Source | Renderer | English? |
|---|---|---|---|
| Thumbnail-page **category tab** (top-left banner) | MTMES slot title | 16×16 tbl text, honours 1-byte codes; **ignores `0x03`** (ASCII garbles: "Art Design 1"→今のば Ｚちはづっな) | **YES — full-width uppercase, ≤9 glyphs** (tab box is FIXED ~146 px) |
| Thumbnail-page **caption banner** (appears right of the tab for the selected plate) | MTMES caption `[1..16]` | same tbl renderer; banner **starts at fixed x≈188 and hard-clips at the 352px edge** | **YES — ≤10 glyphs** ("TOWN OF PARM" clipped to "TOWN OF PA"; "LECK MINES" fits exactly) |
| Category-select page **labels** (6, staggered) + the zoom-in transition | **MTOUT slot 3** | the page renderer parses bytes ≥0x20 as 1-byte tbl codes through the LWRAM `0x200a00` XOR-RLE font (A–Z at 0x0B–0x24) — full-width Roman DOES render. The historic "pixel noise" was a **runaway label parse**: the slot-3 block must end in a **double NUL inside the file**, else a garbage 7th label overflows the sprite staging and trashes the label structs. `viewer_mtmes.py` now NUL-pads MTOUT to its vanilla 110644 B | **YES (Lane K)** — `ART 1`/`ART 2`/`MONSTERS`/`CAST 1/2/3`. Row-2 label ≤5 cells (selected-bar window 128–272 + fixed piece sprite at x278 — see `design-materials-en.json` `notes.menu`) |
| Selected-label **bar** + 設定資料集 **banner** | baked art in **MTOUT slot 2 sub-blob 6** (slot2+0x7f0, 29168 B, resident field-sprite codec `0x0601A716` — NOT the ST1 codec; decoder oracle `src/theater/gfx_plate.py`) → 0xC900 B of 8bpp VDP1 textures: banner 144×24 @ +0x1680, six 144×16 strips @ +0x9300 | strips are **REVERSE-VIDEO masks**: 0x83 = solid bar, 0 = glyph-shaped holes; the white tbl-text label sprites underneath show through the holes (author strokes-as-0x83 and you get blue text with no bar) | **YES (Lane K)** — banner "DESIGN MATERIALS", strips re-authored via `tools/viewer_mtout_gfx.py` (real in-game glyph decoder `0x06030ADE` as oracle, optimal length-limited-Huffman re-encode, byte-exact round-trip); ships as `patches/viewer/MTOUT.DAT.xdelta3` |
| Page view (the plate) | MT{cat}{page}.BIN art | — | baked scans, defer |

**Shipped:** `tools/viewer_mtmes.py dump|patch|inject|fold` driven by
`docs/menus/design-materials-en.json` (titles ≤9 / captions ≤10, full-width A-Z/0-9/space; fuller
wordings preserved in `en_deferred`; monster-name truncations logged in `dictionary/exceptions.json`).
Both files are **NUL-padded to their vanilla sizes** (MTMES 1004 B, MTOUT 110644 B) → in-place
inject at LBA 190587/190588, same sector counts, no relocation, no file-index poke needed, and
existing savestates' baked file-index sizes stay valid. `fold` = the RC step: MTMES text re-patch +
MTOUT via `patches/viewer/MTOUT.DAT.xdelta3` (md5-gated vanilla→english, idempotent — Lane K).
The 美術設定1/2 tab titles were renamed SCENERY→**ART 1/ART 2** to match the category-page label
length limit (see the table above). Full category-page RE + validation:
`docs/lanes/laneK-category.md`. Proof: `docs/lanes/laneK-*.png`,
`docs/museum-gfx/design-viewer-thumbs-english-{parmtown,leckmines}.png` (+ garble evidence
`design-viewer-fullwidth-garble-evidence.png`, vanilla ref `design-viewer-vanilla-reference.png`).
**Category unlock gating:** the six categories are museum unlockables — with a fresh/limited game
save only 美術設定1 is unlocked and the D-Pad "does nothing" on the category page (vanilla behavior,
not a patch bug). Forcing the flag block `0xFF ×16 @ 0x06021ea4` area (poke 16 bytes at
`0x06021ea0`) unlocks all six; then Up/Down moves the highlight normally.

**Headless access trick (no E808 terminal walk needed):** the viewer overlay is loaded by NAME via
the resident file-index table, and the overlay header carries its own load address — so poking the
**`MONSTBIN` entry's FAD/size (HWRAM `0x0602a038`) to MATER.BIN's (FAD 160845, size 45680)** makes
the *library* monster terminal (`saves/library-monster-table`, proven C→Down→C nav) launch the
DESIGN viewer instead. Registered iteration state: `saves/design-viewer-category` (viewer open at
the category page). NB: the archives room itself is reachable by poking the `E804MDT` entry
(0x06029b48) to E808.MDT's FAD/size and walking Up from `saves/cloudbridge-save` (the theater-door
hijack) — Darlin/Milda NPCs + dialogue work, but the 600b terminal's trigger spot was not found by
C-sweeps (open item; the user reached it manually in rc_15).

## Rollout plan (per the plan's "ship one viewer + generalise")

1. **Credits (EDFNT) — ship first, offline-complete now.** Author English strips (role headers +
   romanised names) at each slot's `W×24` 4bpp, `mg_stb repack` constant-size, inject in place.
   Gate: reaching the credits screen for the in-game shot (need trigger/savestate).
2. **Monster names** — find the name strips (overlay vs a bank); if uncompressed strips like
   EDFNT, same easy path. First needs a populated-encyclopedia save to even see the viewer.
3. **Design Materials / Expression / Save-browser** — compressed payloads in the overlays:
   confirm whether the **ST1 codec** (`tools/mg_codec.py` + `mg_tree.py`) applies (look for the
   BE16-chunk-count + inline-treedef signature) or a different framing; then decode→redraw→
   re-encode (`mg_splice.py`) as for the minigames.

## Savestates (catalogued in `saves/`)

Registered via `tools/save_register.py` (CLAUDE.md savestate workflow). Provided by the user:
`monster-book1-list` + `monster-detail-redoni` (populated bestiary — viewer WORKS),
`theater-screening-menu`, `minigame-deckswab-title`, `gameroom-arcade`, `cloudbridge-save`,
`field-near-theater`, plus the rc_15 set (`rc15-monster-menu` = empty-bestiary black screen,
`rc15-savebrowser`, `rc15-library-hub`).

**Still needed for full rollout:** savestates that **open** Design Materials and Expression
Collection (their ST1 blobs decompress only on viewer *entry* — capture R4 via `--bp 0x06013F90`);
and how the **ending credits** screen is reached for the EDFNT in-game shot.

## PoC shipped (offline) — EDFNT credits in English

`tools/edfnt.py` (new) does `dump` / `author` / `patch` for EDFNT.DAT. Patching 9 credit lines to
English (`work/museum/edfnt_en.json`) produces `EDFNT_en.DAT`: **same file size, byte-identical
offset table, exactly the 9 intended slots changed** → in-place disc-patchable (same LBA, no
relocation). Re-decoding the repacked bytes renders clean English credits
(`docs/museum-gfx/edfnt-credits-english-offline.png`). This validates the full
decode→author→constant-size-repack→render pipeline for the **uncompressed text-strip** viewer
class. Constraint: each English line must fit the slot's *fixed* width (narrow 2-kanji headers like
slot 0 `声優`/48 px only hold ~4 chars — `author` auto-shrinks the font 18→9 px, else errors;
truly-longer headers would need slot growth + offset-table relocation, à la `src/relayout.py`).

Committed proof images: `docs/museum-gfx/` — `edfnt-credits-english-offline.png` (PoC),
`edfnt-credits-jp-cast.png` (original JP cast page), `edfnt-slot1-jp-strip.png` (raw 384×24 strip),
`monster-bank-mt000-sample.png` (uncompressed 8bpp monster art), `monster-viewer-blackscreen.png`.

## Tooling changes this session
- `tools/ymir-harness/main.cpp`: `--dump-wram` now also writes **`cram-final.bin`** (live VDP2
  CRAM after the run, via `SaveState`) — distinct from `--dump-cram` (savestate CRAM, pre-Load).
</content>
