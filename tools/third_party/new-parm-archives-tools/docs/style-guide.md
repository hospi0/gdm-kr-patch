# G1 EN Style Guide — visual atlas findings (Lane R2, polish round)

Canonical visual reference for matching gdm-max's English presentation to the
TrekkiesUnite **Grandia 1 English fan patch** (v1.0.0-Final, Saturn). Everything below is
**measured from live emulator captures** of the patched disc running in the headless YMIR
harness, plus byte-level inspection of the patched vs. JP disc. Reference screenshots live
in `docs/lanes/pREF/` (32 PNGs); how each was reached is documented in
`docs/lanes/laneR2-style-atlas.md`.

Color values are given as sampled RGB. The Saturn uses 5-bit-per-channel color, so values
step in multiples of 8 (248 = pure white channel, etc.).

---

## 1. Fonts on the disc (the fan patch's technique)

| font | size | where | usage |
|---|---|---|---|
| ASCII 8x16 | 8x16 fixed-width | already on the JP disc (PS1-style English font), selected via control code `0x03` | dialog, item full names, descriptions, banners' text plates, menu values |
| ASCII 8x8 | 8x8 fixed-width, half-width cell | JIS X0201 range | list columns (item lists, spell lists, battle labels), HUD labels |
| 16x16 JP | 16x16 | `FDATA.BIN` | JP text; unused by EN surfaces |

Key fan-patch mechanics (byte-verified by diffing EN vs JP discs):

- **Default font switch:** `SCNRL.BIN` offset `0x22A4`: byte `0x9D → 0xB4`. This makes the
  engine default to the 8x16 ASCII font instead of requiring `0x03` per-string. Only 7 bytes
  differ in the whole file (`0x1BB4/5` `C0 45→41 5D`, `0x1BBE/F` `44 11→41 5D`,
  `0x20EE/F` `2F 2B→AF 49`, `0x22A4` `9D→B4`).
- **Battle labels:** every `.BBG` battle file grew by exactly **+12120 bytes** (text section
  +12240) containing appended English strings in two forms: 8x8 ALL-CAPS list forms
  (`PARTY`, `JUSTIN`, `COMBO`, `CRITICAL`, `KILLER MOVES`, spell/move short forms) and
  Title Case forms (`Party`, `Combo`, `Enter Command`, `" Skill Level went up!"`,
  `"Escape Successful"`).
- **The fan patch REBUILT the ISO** with larger files (MDTs grew). Our project instead uses
  size-aware injection + xdelta; the point is the *presentation*, not the packaging.
- **Post-battle results text** (`ENDW.DAT`) is **pre-rendered compressed graphics**, not
  font-rendered strings (same file size, diffs at compressed ranges incl. `0x3B46–0x5B4A`).
  Its palette below comes from live captures.

## 2. Dialog windows (field)

Reference: `pREF-dialog-font-8x16.png`, `pREF-dialog-choice-box.png`,
`pREF-dialog-acquired-item.png`, `pREF-dialog-puff-bubble.png`.

- **Font:** 8x16 fixed-width ASCII, **8px advance** (≈7px glyph core + 1px), line height
  ≈15–16px. No proportional spacing.
- **Text fill:** white `(248,248,248)` with a **1px black outline** on all sides.
- **Window border:** two-tone gold — light `(200,192,128)`, dark `(184,160,104)`.
- **Window fill:** dark brown, two-tone `(64,48,32)` / `(40,32,16)` (subtle dither/gradient).
- **Punctuation/casing:** sentence case, straight apostrophes and double quotes rendered from
  the ASCII set (`"Warrior's Helmet"`), `!`/`?` used freely.
- Choice boxes and item-acquired boxes use the same font/palette as dialog.

## 3. Field UI

- **Area name plate** (`pREF-areaplate-marna-road.png`): Title Case ("Marna Road") in 8x16
  white-on-outline text inside a slim gold-bordered plate.
- **Signposts** (`pREF-signpost-to-gantz-house.png`): Title Case with possessives kept
  ("To Gantz's House").
- **World map** (`pREF-worldmap-messina.png`): location names as large pre-rendered/stylized
  Title Case text ("Marna Road", "Part Town...") over the map art.

## 4. Pause menu (Items / Equip / Magic / Moves / Status)

Reference: `pREF-pause-items-base.png`, `pREF-pause-items-use.png`,
`pREF-pause-equip-change.png`, `pREF-pause-magic-level1.png`, `pREF-pause-moves-level1.png`,
`pREF-pause-status.png`, `pREF-options-screen.png`.

- **Labels** (headers, stat names): yellow `(248,248,0)`.
- **Values** (numbers, item names in lists): white `(240,240,240)`.
- **Background:** green `(88,136,80)` window fill.
- **List columns** use the 8x8 ALL-CAPS short-forms (≤9 chars, per Lane R1's rip — see
  `docs/menus/g1-item-list-aligned.json`); detail lines / descriptions use 8x16 sentence
  case ("+5 attack  A child's toy").

## 5. Battle UI

Reference: `pREF-battle-cmdring-*.png`, `pREF-battle-defend-bar-*.png`,
`pREF-battle-tactics-screen.png`, `pREF-battle-items-menu.png`, `pREF-battle-moves-menu.png`,
`pREF-battle-action-banner-puffy-kick.png`, `pREF-battle-2hits-popup.png`,
`pREF-battle-intro-banner-giant-centipede.png`, `pREF-battle-enemy-panel-centipede-defend.png`.

### Command ring & HUD (8x8 ALL-CAPS)
- Ring slot labels: `COMBO`, `CRITICAL`, `DEFEND`, `LOOK`, `ESCAPE`, `TACTICS`, `ITEMS`,
  `MOVES`, `MAGIC` — all 8x8 ALL-CAPS.
- HUD strip labels: `NAME` `HP` `ACTION` `STATUS` (P-STATUS), `WAIT`, `COM`, `ACT`;
  active prompt `ENTER CMD`.
- Moves/Magic submenu: move list short-forms 8x8 ALL-CAPS (`PUFY KICK`, `"RAH-RAH"` — note
  quotes preserved in list form), `SP-8` cost format, headers `MAGIC LV 3` / `Moves` /
  `SP 20/ 20`; description line 8x16 sentence case ("Attack 1 enemy by throwing Puffy"),
  `Skill Type` label Title Case.
- Tactics screen: `Use Single Tactics` / `Use Party Tactics` (Title Case, L/R tabs),
  values `MANUAL`, `PLAY FAIR` (ALL-CAPS).

### Defend bar
- Three-segment bar: **`Endure` | `Defend` | `Evade`** — Title Case, 8x16, on a red/brown
  bar with L/R end tabs.

### Banners & popups
- **Battle-intro enemy banner** and **action banners**: Title Case 8x16 white text on a
  **blue plate with a thin white/blue border** ("Giant Centipede", "Puffy Kick").
- **Combo hits popup:** `2 HITS!` in yellow.
- CRITICAL hit popup: not captured (see DEFER in lane doc); the ring label form is
  `CRITICAL` (8x8 caps), and BBG strings include Title Case `Critical`.

## 6. Post-battle results screens (the yellow-fill / red-border question)

Reference: `pREF-results-skills-page.png`, `pREF-results-exp-points-page.png`.

- Page title **"Battle Result"** (Title Case, large pre-rendered glyphs from `ENDW.DAT`):
  **fill `(209,64,6)`** (orange-red) with **border `(69,18,6)`** (dark red-brown), on a blue
  panel background `(0,88,208)`.
- **Skills page:** tab "Skills"; skill labels **yellow `(248,248,0)`**, gauge bars red
  `(216,0,0)` / dark red `(120,0,0)`; numeric values white with 1px black outline.
- **EXP page:** tab "EXP Points"; same yellow-label / white-value scheme.
- So the "yellow fill + red border" convention concretely = yellow `(248,248,0)` labels and
  red `(216,0,0)`/`(120,0,0)` bars/accents; the big title glyphs are orange-red fill
  `(209,64,6)` with dark `(69,18,6)` border.

## 7. Save browser

Reference: `pREF-savebrowser-empty.png`, `pREF-savebrowser-populated-cd1.png`,
`pREF-savebrowser-overwrite-prompt.png`.

- 8x16 white text on the standard brown/gold dialog window; slot rows show save metadata;
  overwrite confirmation is a standard choice box. Same palette as §2.

## 8. Casing conventions (summary table)

| surface | casing | font |
|---|---|---|
| 8x8 list columns (items, spells/moves, battle labels, HUD) | ALL-CAPS, ≤9 chars | 8x8 |
| Full names, banners, area plates, signposts, defend bar | Title Case | 8x16 |
| Dialog, descriptions, battle detail lines | Sentence case | 8x16 |
| Results page titles & tabs ("Battle Result", "Skills", "EXP Points") | Title Case | pre-rendered |
| Tactics values (MANUAL, PLAY FAIR) | ALL-CAPS | 8x8/8x16 |

This matches the battle-chrome CANON pass already landed in rc_44–rc_46 (Title Case
"Magic", "Evasion", Endure/Defend/Evade) and the Lane R1 ALL-CAPS ≤9-char list finding.
