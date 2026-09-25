# Full-length door/location banner names — why they can't be full, and the review path

**Question (user, 2026-06-28):** make door/location banner names full-length (e.g. "SCREENING ROOM",
not "SCREENING"). **Answer: not achievable cleanly** — here's the extensive investigation and the
practical path (a terse-fit review page).

## The hard limit (verified live)
A banner is a `0x2NNN` box-render command; the box holds **only ~`budget` glyphs, where `budget` = the
glyph count of the original Japanese name** (the box is sized from the JP content). Render more and the
box **overflows → the scene desyncs/freezes**.

Proven by WRAM-injecting the E800 d001 ("Archives") banner and re-triggering it (the harness can walk
the field — Up/Down/Left/Right):
- `"ARCHIVES"` (8 glyphs ≤ budget 12) → renders clean. (`work/jinloop/arch/candNew`, `fa`)
- `"ARCHIVES ROOM"` (13 glyphs > 12) → the box overflows, the scene desyncs, the party walks off into
  the casino/game-room. (`work/jinloop/arch/fd`)
- 8×16 in the banner (`0x03` + ASCII) → kana garbage (banners render the **default 16×16** font and the
  `0x03` switch only changes the table, not for this fixed-16 banner path). (`candC`)

So we already render the **maximum** the box allows; `best_fit_name` word-truncates the rest.

## Why "just make it fit" doesn't work (prior RE, memory `scnrl-font-patch`)
The TrekkiesUnite trick is a global `SCNRL.BIN` patch to default to 8×16 (half-width). For DM that byte
is found (`SCNRL 0x22B0 0x86→0xAF`, XOR key "OHATA"), but a prior session proved it's **regressive**:
- It flips the glyph **table** to 8×16 but **keeps the 16px advance** → fuzzy/overlapping text.
- The real prize (the **box-width / measurement** byte) is **global** and was never cleanly pinned; the
  width comes from hardcoded `mov #0x10` (=16px) sites feeding a width-accumulation function — forcing
  8px corrupts the computed width and **shrinks/garbles every 16×16 banner and menu**.
- It is **all-or-nothing**: a global 8×16/8px would break the very banners we just fixed.

Conclusion: there is **no clean per-banner way** to widen the box. Full-length banner names are out;
clean truncation / terse forms are in.

## The practical path — terse-fit review (delivered)
`docs/menus/door-names-review.html` (served locally): every door/location banner name with its **Max**
(box budget), the current auto word-fit, and an editable **UPPERCASE terse form ≤ Max** per location
(page-0 has no lowercase and no apostrophe → shows as space). The user picks readable terse forms
(e.g. "Hall of History" → "HISTORY HALL" (12), "Sky Corridor" → "SKYWAY"); we apply them to
`RUN_TEXTS`. ~50 unique banner names; the worst cases are the long room names (Bloody Rose Room,
Lightning Star Room, Outer Wall Passage) and tiny-budget ones (House 3 → 3 chars).

## If full-length ever becomes a hard requirement
The only route is the box-measurement engine patch (dynamic-trace the box-dim calc on a freeze repro,
find a NON-global gate for the banner path) — a separate, high-risk sub-project that must NOT regress
the 16×16 banner/menu rendering. Not recommended over terse fits.
