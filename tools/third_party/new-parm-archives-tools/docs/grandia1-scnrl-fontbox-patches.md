# Full-length names: TrekkiesUnite's complete Grandia-1 SCNRL patch set, ported to DM

**Breakthrough (2026-06-28):** by diffing the **EN (TrekkiesUnite) vs JP (original) Grandia-1
`SCNRL.BIN`** (both in `input/`, decoded with the OHATA XOR), TU's *entire* font/box-fit patch is just
**4 sites / 7 bytes**. All four match DM byte-for-byte at context-located offsets, so they port directly.

## TU's Grandia-1 patches (decoded SH2) and the DM equivalents
| Purpose | Grandia RAM | DM RAM (decoded file off) | decoded change | DM encrypted change |
|---|---|---|---|---|
| nop a 16×16 op | `0x0601DBB4` | `0x0601DBB4` (`0x1BB4`) | `8111` → `0009` (nop) | `c045` → `415d` |
| nop a 16×16 op | `0x0601DBBE` | `0x0601DBBE` (`0x1BBE`) | `0545` → `0009` (nop) | `4411` → `415d` |
| box width = 8px | `0x0601E0EE` | `0x0601E0FA` (`0x20FA`) | `6063` → `e001` (mov #1,r0) | `2137` → `a155` |
| default font 8×16 | `0x0601E2A4` | `0x0601E2B0` (`0x22B0`) | `c901` → `e001` (and→mov #1,r0) | `8649` → `af49` (1 byte: `86`→`af`) |

(Encrypted = decoded ⊕ "OHATA"[off%5]; verify before writing.) `work/.../grandia1/` has the decoded
EN/JP/DM SCNRL dumps.

## Why the prior session (`scnrl-font-patch` memory) failed
It worked from the wiki, which only documented the font site (`0x22A4`) and *one* box site (`0x20EE`):
1. It used DM offset `0x20EE` for the box patch — **wrong**; the real DM offset is `0x20FA` (DM SCNRL is
   12 bytes larger, so post-`0x20xx` code is shifted +12). `0x20EE` in DM is unrelated data → garbage.
2. It **never knew about the two `nop` patches** (`0x1BB4`/`0x1BBE`) — these disable the 16×16-specific
   width ops and are very likely what removes the "fuzzy/overlapping" regression it saw.
So its conclusion ("global patch is regressive, not worth it") was from an **incomplete** patch set.

## Verified so far (this session, via the YMIR harness)
- Injected the DM-patched decoded SCNRL at RAM `0x0601C000`; **all 4 sites read back correct** in WRAM.
- **Dialogue renders clean** with the patch active (E810 screening room: full English mixed-case, no
  fuzz, no regression). The font/box patches do **not** break dialogue.

## Remaining work (the integration)
1. **Re-encode banner names as 8×16 ASCII** (mixed-case, full-length) — under 8×16-default the box
   reads bytes as ASCII, so the current page-0 encoding would garble (page-0 `0x2B`='A' → 8×16 `'+'`).
   Keep the `0x2NNN` box command + `0xc0` window-color, name as raw ASCII, `0x07`-terminated.
2. **Compose the 4 patches into `SCNRL.BIN`** alongside the resolver-widen patch (different offsets, so
   they coexist), in the build pipeline.
3. **Regression-test the GLOBAL effects** (this is the risk — it's an all-or-nothing default-font flip):
   - **Menus** (CMDMN/SHOP/SVLD/etc.) — they mix 8×16/16×16; may need checking/re-fit.
   - **Untranslated JP** field areas (3 MDTs) — JP 2-byte glyphs have no 8×16 page → would garble.
   - **16×16 banners we just fixed** — should become clean 8×16; confirm no overflow with the box patch.
4. **Verify banners render full-length** — needs a savestate created **on a patched disc** (savestates
   bake the resident SCNRL, so they mask an on-disc SCNRL change; and partial injection on an
   unpatched-name area desyncs). The harness can then verify reliably.

## DM incompatibility found + fixed (2026-06-28, rc_06 -> rc_07)
User tested rc_06 (all 4 patches): **most banners rendered full-length 8x16**, BUT entering the
**Library** (and other `c000`/`e001` area-banner rooms) **warped to the casino + reverted the font to
16x16** (so 8x16 names then showed as kana, e.g. "Wのたつづひちは"). Debugged via live SCNRL injection
on the user's savestates (`7FF1/1` at the door, `7FF1/0` post-glitch):
- Reverting **all 3 box patches** (font-only) -> Library renders "Library" in 8x16, no warp.
- Reverting **only the two nops** (keep font + `0x20FA`) -> also fixes it. So the **`nop` patches
  (`0x1BB4`/`0x1BBE`) are the culprit** — in DM they sit in code the room scripts use, so NOPing them
  desyncs the scene (TU's Grandia-1 didn't have these rooms). The font setter (`0x0601E2B2`) never
  runs during room entry, so the font state is inherited; the nops corrupt it.
- **Fix:** `FONT_BOX_PATCH` now applies **only the default-font patch (`0x22B0`)**. 8x16 is half-width,
  so names fit without the box-width patch (dialogue precedent: 8x16 boxes never overflowed without it).
- **Residual (cosmetic):** a `c000`/`e001` banner box is over-sized for short 8x16 text -> a pink tail
  tile (the box-width patch would have fixed this, but it's bundled with the harmful nops). Refine by
  padding the 8x16 name with trailing spaces to fill the box, OR find a DM-safe box-width-only patch.
  Door banners (`d0xx`, which carry the `0xc0` window-color) should be unaffected.

## Prep that would unblock verification
A fresh YMIR savestate **on the patched test disc**, positioned (a) right before a door/area banner,
(b) in a system menu, and (c) in an untranslated JP area — so the harness can confirm full-length
banners + catch menu/JP regressions without the savestate masking the patched SCNRL.
