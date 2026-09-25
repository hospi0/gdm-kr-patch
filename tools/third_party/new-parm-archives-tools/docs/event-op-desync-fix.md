# Event-op desync fix — growing dialogue inside flag-guarded routines

A reusable recipe for the failure class where a script piece **plays correctly the first time but
mis-executes after** (replays a scene, warps the party off-map, or runs garbage), once its dialogue
boxes were grown to full English. First diagnosed end-to-end on **E800 piece 0** (the Alent Museum
intro). Companion to `dialogue-growth-SOLVED.md` (which solved the simpler single-box case, E80C
500a). Cross-link: [[dialogue-growth-solved]].

## Failure signature
After a build grows dialogue (`build_final.py --widen`, `build_rc.py`), in-game you see one or more of:
- a **scene replays** when you re-enter the room (E800: Liete's intro plays again every hall entry);
- the party is **warped off-map** / placed wrong, with graphical glitches, after the scene;
- **garbage** (stray/colored tiles beyond the line-end cosmetic) right after the last grown box.

The first playthrough is usually **fine** — the corruption shows only on the *second* pass / re-entry.
That timing is the tell: a **conditional skip** taken on re-entry uses a length that growth left stale.

## Mechanism (what actually breaks)
A field piece is an interpreter command stream of 16-bit words (see `subst.parse_box_commands`):
- `0x2NNN` — render a dialogue box of `NNN` inline content bytes.
- `0x3NNN` — a **conditional-block skip-length**: emitted as `… 1000 3NNN <body> f000`. When the
  preceding flag test fails, the interpreter **jumps `NNN` bytes** to skip the whole block.
- `0x50 xx` + operand — an **event op** (set flag / give item / sprite). `f000` = return/end.

`NNN` is a **relative length that must equal the block body size**. Growing dialogue boxes inside the
block enlarges the body, so every `0x3NNN` spanning those boxes must grow by the **total** box growth.

E800 piece 0 is three flag-guarded routines (`f000`-separated). Routine A (the whole intro, guard
flag `0x01`) opens `1000 3690` → `0x3690` = 1680 ≈ its 1678-byte body, and that one skip-length spans
**all 13 of the intro's dialogue boxes**. On first entry the guard *runs* A inline (skip unused) → the
intro renders. On re-entry the guard *skips* A using `NNN` → if `NNN` is stale-short the jump lands
**mid-routine** instead of at routine B → garbage execution = replay + off-map warp.

### The specific bug
`subst.substitute_piece_boxes_paginate` updated each `0x3NNN` by only the **first box after the word**,
then reset. That under-counts any block spanning multiple boxes:

```
E800 routine A body:  1678 B → 2394 B   (+716, all 13 boxes)
0x3690 skip (buggy):  1680   → 1702      (+22, box 1 only)   ✗ stale by 694 B
0x3690 skip (fixed):  1680   → 2396      (+716)              ✓ lands on routine B
```

The single-box case (E80C 500a, one `0x3NNN` per box where the next box sits past the span) was
correct by luck and is unchanged.

## The fix (span-based `0x3NNN`)
In `substitute_piece_boxes_paginate`, bind each `0x3NNN` to the **byte span it covers** (`NNN` bytes
after the word) and add the cumulative growth of **every** box whose original offset falls inside that
span — nesting-safe (a box inside two blocks adds to both). Keep the existing invariants:
- **even-length box content** (word-alignment: the SH-2 `mov.w` dispatcher reads at even addresses; an
  odd box pushes the next op onto an odd byte → misread). Pad with a trailing `0x04` past the
  terminator.
- the box command's own `0x2NNN` length word = new content length (so the dispatcher advances right).

Skip-length and box-length fields are 12-bit (`0x0FFF` max); the code raises if a grown block exceeds
it. **Never hand-patch the piece OFS table** — the Java reconstructor recomputes inter-piece offsets.

## How to detect it on a new MDT (Phase-A op-mapping)
1. Parse the piece (`build_mdt.java parse-mdt` → `parse-script`) and walk it as a command stream;
   list every `0x2NNN` box, `0x3NNN` skip, `0x50` op, and `f000`.
2. For each `0x3NNN`, check how many boxes fall in its `NNN`-byte span. **>1 box ⇒ the old code
   under-counted it** (the scan in this fix flagged E800, D800, EA00, EB00, EB18, E800 5001, and many
   `2000` pieces).
3. **Classify every `0x50` operand** before assuming it's a pointer. In E800 they are flag/sprite
   **immediates** (`0x07xx`, `0x08xx` — values that exceed the piece size, so they cannot be intra-piece
   SCN offsets), **not** absolute targets. There was nothing to "re-point"; do not shift op operands by
   the growth delta or you double-break the flow. (Confirm with the SH-2 trace in
   `dialogue-growth-SOLVED.md` §Root cause — watchpoints on dispatch `0x0601E5C4`, op handler
   `0x0601E9F2` — if an operand's role is ambiguous.)

## Verify
- **Offline (decisive here):** re-parse the piece from the reconstructed SCN; confirm the stream
  re-parses to its exact length, all `0x50` ops present, and each `0x3NNN` skip target lands on the
  next routine's first instruction (E800: word@8 +2 +2396 = 2406 = routine-B `1001`, the same `-2`
  offset vanilla had). Confirm the merged-disc SCN is byte-identical to the verified reconstruction.
- **Headless (`tools/jinloop.py` from an in-scene savestate):** the scene renders full English,
  advances past the last line into the post-scene dialogue, `revisit=0`, and ends **on-map**.
- **GUI (user, the gate the harness can't do):** load the RC, watch the scene, then **leave and
  re-enter** the room → the scene must NOT replay; party ends on-map; no glitches.

## Remaining cosmetic (separate, game-wide)
The magenta tile at line ends is the `0x04` (switch-to-16x16) byte rendering a glyph when hit in 8×16
mode — emitted before every newline/terminator. It is pre-existing, affects all grown dialogue, and is
independent of this fix. Tracked as OPEN-2 in `step3-followups.md` / `dialogue-growth-SOLVED.md`
§Remaining; needs emulator iteration on the font-switch sequence.

## Files
- `src/subst.py` → `substitute_piece_boxes_paginate` (the span-based `0x3NNN` update).
- `tools/build_final.py` routes every paginated MDT through it (no per-MDT wiring needed; E800 keeps
  full prose with no MIXED/`grow_filter` fallback because there are no op pointer-operands).
- `tools/build_rc.py` → `output/rc_NN/` (dialogue `--widen` + menus merge in one command).
