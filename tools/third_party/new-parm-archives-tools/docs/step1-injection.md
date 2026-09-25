# Step 1 — Arbitrary-length text injection (pipeline)

Goal: prove we can inject English dialogue of **any length** into Digital Museum without crashes
or corruption, then document the verified pipeline and real limits. This gates Steps 2 and 3.

Status: **GATE PASSED ✅** — both equal-length substitution (010, renders English + plays) and
arbitrary-length **expansion** (016, renders a long paginated English box + plays) are confirmed
in YMIR. Remaining work is rendering polish (clean substitution coverage + screen-break format),
tracked in `attempts-step1.md`.

## Verified working recipe (the answer to "can we inject any length?")
1. Extract `E800.MDT` (`src/iso.py`), parse to parts + script pieces (Java CLI).
2. Edit dialogue **inside boxes** (`0F 03/21 0A 0C 00 NN` … `0x07`): replace JP glyph runs with
   `0x03` (8×16 ASCII font) + English; treat `0x10–0x1F`+next as 2-byte JP chars (`src/subst.py`).
3. **Length:** equal-or-shorter fits in place (pad MDT back to original size). To go **longer**,
   keep ≤3 lines per screen and **paginate with a `0x02` screen break**, then **relocate** the
   bigger MDT to the end of the track (`src/relayout.py`) — the data track is full so in-place
   growth has no room, and the engine accepts a relocated bigger file (012/016).
4. Reconstruct script + MDT (Java CLI; it fixes the header sector fields), inject sector-aware
   into the `MODE1/2352` track (`src/inject.py` / relocate), build into a new `output/NNN/`.
5. Verify manually in YMIR.

**Hard limits found:** a single box overflows vertically past ~3 lines (014/015 crash) → must
paginate. The TrekkiesUnite default-8×16-font patch is original-Grandia-specific and not portable
to Digital Museum, so we keep the per-run `0x03` switch.

---
Status (historical): scaffolding — pipeline below is the original target.

## Build & tooling status (2026-06-17)
- ✅ `tools/setup.sh` clones upstream `GrandiaTranslation` and builds the Maven project in
  `GrandiaTranslationTools/` (not the repo root).
- ✅ **JDK fix:** upstream targets JDK 8 and uses `javax.xml.bind.DatatypeConverter`, removed
  from the JDK in Java 11+. We re-add JAXB via `tools/patches/01-jaxb-datatypeconverter.patch`
  (auto-applied by `setup.sh`). Builds cleanly on Java 24. Produces `target/*.jar` + `target/classes`.
- ⚠️ **No CLI upstream.** The `com.grandia.cli.MDTParserCLI` referenced in the original
  injection guide does **not** exist in the public repo — it was custom work. Upstream ships
  **GUI (Swing)** front-ends (`com.grandia.gui.Grandia*`) over core logic in
  `com.grandia.file.*` (`MDTFileParser`, `ScriptParser`, `ScriptReconstructor`,
  `MDTFileReconstructor`, etc.).
  - **Next task:** write a thin CLI/wrapper (Java `com.grandia.cli` added via a patch, or a
    Python driver) that calls the `com.grandia.file.*` classes headlessly so the pipeline below
    can be scripted into `output/NNN/` without manual GUI clicks.
- ✅ **Headless CLI added** (`com.grandia.cli.MDTParserCLI`, `tools/patches/02`) exposing
  `parse-mdt / parse-script / reconstruct-script / reconstruct-mdt`.
- ✅ **Cross-platform path fix** (`tools/patches/03`): `ScriptParser` hardcoded a Windows `\\`
  separator, so on macOS pieces were written as `\0` and the reconstructor couldn't find them.
- ✅ **ISO9660 reader** (`src/iso.py`) reads the `MODE1/2352` track directly: enumerates all
  **36 `.MDT` files**, and locates `/FIELD/E800.MDT` at **LBA 31115, size 503808** (raw offset
  `73182496`) — matching the documented sector.
- ✅ **Lossless round-trip proven:** extract E800 → parse-mdt → parse-script (22 pieces) →
  reconstruct-script → reconstruct-mdt yields a **byte-identical** 503808-byte MDT. Pointer
  reconstruction is correct for Digital Museum.
- ✅ **Sector-aware injector** (`src/inject.py`): writes 2048-byte user data per raw sector at
  `lba*2352+16`, leaving EDC/ECC stale (emulators don't verify it).
- 🔎 **Dialogue location:** the intro dialogue is **inline inside script piece `0`** (mixed with
  event bytecode), header `0F 03 0A 0C 00 02` … `07`, using Grandia's 2-byte JP codes. (DM
  differs from original Grandia where text pieces were separate.)

### ⚠️ The Step 1 limitation, quantified
`E800.MDT` is 503808 bytes = exactly **246 sectors**, and `E804.MDT` begins at the very next
sector (LBA 31361). The rebuilt MDT's content sums to 503612 bytes, so there are only
**~196 bytes of in-place slack**. A 100+ word English box (~568 bytes) **does not fit in place** —
it would overrun E804. `src/inject.py` refuses such an overrun unless forced.

**To prove arbitrary-length (100+ word) injection we therefore need one of:**
1. **Single-file relocation** — move E800.MDT to appended space at the end of the data track and
   patch its one ISO9660 directory record (LBA + size). Simplest; nothing else shifts.
2. **Track relayout** — shift E804.MDT onward and rewrite all affected directory records.
   More general; Step 3 may need this if the engine uses hardcoded LBAs.
3. **Fit-in-hole demo only** — inject ≤196 bytes to confirm the pipeline + English rendering.

### Progress on the proof
- ✅ **`output/001` — render gate PASSED.** Equal-length swap (`TEST INJECT 01`, no shift)
  **confirmed rendering in YMIR by the user.** Font switch `0x03`, control codes, sector-aware
  injection and stale-ECC tolerance all work.
- ✅ **Relocation engine built** (`src/relayout.py`, uses `iso.find_record`): appends raw
  MODE1/2352 sectors at track end, writes the larger MDT there, repoints the file's directory
  record (both-endian LBA + size), and bumps the PVD volume size.
- ⏳ **`output/002` — the 100-word proof, awaiting YMIR test.** E800 grew to 247 sectors and was
  relocated to LBA 193620. If it renders, Step 1 is fully proven (and confirms the engine loads
  E800 via the filesystem). If the intro hangs loading E800, the engine uses a hardcoded LBA →
  fall back to in-place track relayout. See `output/002/README.md`.

The 44-byte DM offset shift mentioned in the old guide was **not** needed by these classes for
E800 (round-trip is exact without it); revisit per-MDT if a later file mis-parses.

## Why length is not the enemy
- The crash risk is **pointers**, not length. Internal `OFS` tables point at exact byte offsets
  of each dialogue string. Change a length and every later pointer is wrong.
  → **Never hand-patch pointers.** The Java reconstructor recalculates them all.
- Control code `0x03` switches to the game's **8x16 single-byte ASCII** font (`A`=0x41…).
  English in single-byte is *less* dense than 2-byte Japanese, so translated lines can be longer
  than the originals.

## Target
- `E800.MDT` — the intro sequence ("after they fall").
- Lives at ISO **sector 31115** (offset `63723520`), sector size `2048`.

## Pipeline
**A. Extract**
1. `MDTFileParser` extracts the `.MDT` archive → SCN/OFS/GFX/ASM parts.
2. `ScriptParser` breaks the SCN block into individual dialogue pieces in `script/`.
   - Digital Museum needs a **44-byte offset shift** (handled by our patched tools — see
     `tools/patches/`).

**B. Modify**
- Pick a piece, replace JP bytes with English ASCII. Relevant control codes:
  - `0x0F 0x03 0x0A 0x0C 0x00 0x02` — standard dialogue window header
  - `0x03` — switch to 8x16 English font (**required** before ASCII text)
  - `0x07` — end-of-dialogue marker
- For the first test: insert **marked filler ≥100 words** (clearly non-final placeholder).

**C. Reconstruct**
- `ScriptReconstructor` → new SCN + mathematically corrected OFS.
- `MDTFileReconstructor` → merges SCN/OFS with GFX/ASM into a new `.MDT`.

**D. Inject**
- **Direct binary patch** — do NOT use `mkisofs`/ISO editors (they break the Saturn boot header).
- `seek()` to sector 31115 and overwrite the MDT region. Stay within the original "hole" or keep
  the next file 2048-byte aligned.
- Output the patched track into a **new** `output/NNN/` folder.

## Verify
- Boot `output/NNN/` in **YMIR**. Click through the intro: if the long text advances with no
  black screen / corruption, pointer reconstruction succeeded. (Manual; no auto-capture.)

## Limits to characterize (→ `docs/step1-limits.md`)
- Max chars per dialogue box / per line; line-wrap behavior; multi-box sequencing; which control
  codes are safe; the size of the sector "hole" before we must re-lay-out the ISO.
- `src/limits_probe.py` generates escalating test strings to find these empirically.
