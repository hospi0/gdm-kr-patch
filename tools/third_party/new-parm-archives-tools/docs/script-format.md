# Grandia (Saturn) script & font format — research notes

Sourced from the TrekkiesUnite118 `GrandiaTranslation` wiki (cloned into
`tools/vendor/GrandiaTranslation.wiki/`), the shipped `.tbl` font tables, and our own
Digital Museum experiments (see `attempts-step1.md`). This is the reference for the injector.

## MDT file header (512 bytes, big-endian on Saturn)
8-byte entries: 4-byte offset (Saturn HWRAM addr or file offset) + 4-byte size. Key entries:
- `0x20` — a HWRAM address. **Never change** (crash).
- `0x58` — **script header** (the "OFS": offsets/sizes of dialogue sequences).
- `0x60` — **script data** (the "SCN").
- `0xD8` — graphics/palette data.
- `0x1F8` — special: two offsets; 2nd = end of the `0xD8` data.
- `0x180` & `0x1F4` — **number of CD sectors to read for the file.** Must be updated when the
  file size (sector count) changes, or the game reads stale/short data → corruption/crash.

### Script-header sequence codes (the piece "names" we extract)
`0x0000` intro scripted sequence (camera/voiced; crash if wrong) — **our piece `0`** ·
`0x3000` map setup (crash if wrong) · `0xC000` current-location text · `0xD0xx` door target text ·
`0xE000` save-menu text · `0xE001` save-file location name. Others = dialogue/events.

## Fonts (from FDATA.BIN; tables in `Grandia*.tbl`)
- **8×16** — standard **ASCII** order (incl. lowercase). Selected mid-text by control `0x03`.
  This is what we inject English as. (`0x41`=A … `0x5A`=Z, `0x61`=a … `0x7A`=z, normal punctuation.)
- **16×16** — the **default dialogue font**, all-caps Latin + kana + kanji, via a **paging** scheme:
  - `0x20–0xFF` = single-byte **page-0** char (`0x20`=space, `0x21–0x2A`=０–９, `0x2B–0x44`=Ａ–Ｚ,
    `0x45+`=hiragana…).
  - `0x10–0x1F` = **page selector**; this byte + the next byte form a **2-byte** char
    (e.g. `0x10 0x2B`). These are TEXT, not control codes.
- **8×8** — menu font (ASCII + kana).

## `0x0F` is a 6-byte PORTRAIT/speaker code (from ScriptPortraitCorrector.java) — EXACT rule
**`0F [pos] [vAlign] [x] [x] [x]` = 6 bytes**, where `pos ∈ {03=left, 12=middle, 21=right}` and
`vAlign = 0A`. (Validated by `checkPosString`/`checkVAlignString`; constants
`PORTRAIT_CODE_LEFT/MIDDLE/RIGHT = 03/12/21`, `VERTICAL_ALIGN_CODE = 0A`.) A `0x0F` that is NOT
followed by a valid pos+vAlign is something else (treat as a 1-byte control). **Earlier bug:** we
matched only `0F (03|21) 0A 0C` and missed `0F 12` (middle), so middle-portrait codes were mis-read
as text and overwritten → graphics corruption (attempt 022). 2-byte char position bytes can be
`< 0x20` (e.g. `12 0b`), so do NOT assume the 2nd byte of a char is ≥ 0x20.

Use `src/validate_subst.py` after any substitution: it proves only text bytes changed (no
control/portrait/bytecode byte touched). Attempt 023 passes: 646 text bytes changed, all 32
portrait codes preserved.

(Older note kept for context:) `0F [code] [pos] [vAlign] [..] [..]` — 6 bytes. It selects which character portrait/speaker is
shown and its on-screen position/alignment. The `0F 03 0A 0C 00 NN` / `0F 21 0A 0C 00 NN` we see
are portrait codes (code `03`/`21` = different speakers; `0A`,`0C` = position/alignment; the last
two bytes a param). **Implications:**
- Preserve these 6 bytes verbatim during substitution (we do).
- Our expansion "screen breaks" used `0x02 0F 03 0A 0C 00 00`, i.e. they **set a portrait** every
  page — that's why a portrait (Liete) appears off-screen and can freeze. A real page break needs
  the *correct* speaker's portrait code (or to repeat the box's own), not a fabricated one.
- Text boxes that DON'T start with a `0F` portrait code aren't found by a `0F`-anchored scan, so
  their Japanese is left untranslated (the residual hiragana). The Step 2 parser must separate
  dialogue text from event bytecode without relying on a leading `0F`.

## Dialogue control codes (`0x00–0x0F`, from the 16×16 .tbl)
`0x01` newline · `0x02` new box · `0x03` switch to 8×16 font · `0x04` switch to 16×16 font ·
`0x05` CB · `0x06` SB · `0x07` end of dialogue · `0x08` TB · `0x0E` pause · `0x0F` box header
(6 bytes: `0F xx 0A 0C 00 NN`; `xx` 03/21 = text region variants).

## Making English work well (TrekkiesUnite method)
1. **Default the game to the 8×16 font** instead of prefixing every run with `0x03` (saves space).
   Runtime flag at HWRAM `0x0601CEA4` (`0x00`=16×16, `0x01`=8×16). The setting code is generated
   at runtime via XOR, so it's patched in **`BIN/SCNRL.BIN`**: at offset `0x22A4` change `0x9D`→`0xB4`.
2. **Fix box sizing for the smaller font.** The game still computes text-box size as if 16×16
   (boxes 2× too big → overflow). Force the size flag at `0x06001ECC` to `0x01` during drawing:
   in `SCNRL.BIN` at offset `0x20EE` change `0x2F2B`→`0xAF49`.

## Size-change behavior (Saturn) — and our findings
- Wiki: Saturn **tolerates file EXPANSION** (with the `0x180`/`0x1F4` sector-count fix) but
  **reduction crashes** → a smaller script must be **padded back to the original size**.
- Our experiments (Digital Museum, `attempts-step1.md`): with our current reconstructor (which
  pads the MDT back to original size), **equal/shrink in place works; growing the script in place
  crashes** — consistent with "the file/sector accounting must be right for expansion." True
  expansion likely requires updating `0x180`/`0x1F4` (and relocating, since the track is full).
  This is the open task to enable longer-than-original text.
