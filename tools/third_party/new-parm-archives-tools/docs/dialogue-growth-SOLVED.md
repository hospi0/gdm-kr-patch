# Dialogue growth SOLVED — full English in conversations with a mid-convo event op

This documents the fix that lets dialogue **boxes grow to full English** even in scripts that have a
mid-conversation **event op** between dialogue boxes (the hard case — e.g. E80C `500a`, the Jin
conversation). Before this, growing such a piece produced a garbage box (`つそたで9`) and an infinite
loop ("Sue's line shows twice"), or froze if worked around by merging boxes.

## The script format (E80C 500a, the model case)
A dialogue piece is an interpreter command stream. Relevant commands:
- `0x2NNN` — **render a dialogue box** of `NNN` inline content bytes (portrait + text + controls).
  The command **dispatcher** advances the script pointer by `NNN`.
- `0x3NNN` — a **box-preamble length word** that precedes the box command. This is the **renderer's**
  box extent (separate from the dispatcher's `0x2NNN`). The reconstructor historically left it stale.
- `0x50 01 …` — an **event op** between two boxes (sets a story flag). It is processed by the command
  interpreter, NOT rendered.

Structure of 500a: `[box1 = segs 0–7][event op 5001 0019 f000][box2 = segs 8–9]`.

## Root cause (two independent failures when box1 grows)
Diagnosed with the headless YMIR harness (`tools/ymir-harness/`) via SH-2 instruction trace +
watchpoints. SCNRL (the interpreter) is at `0x0601C000`; key PCs: dispatch loop `0x0601E5C4`, word
read `0x0601E5EC`, box handler `0x0601E700`, op handler `0x0601E9F2`.

1. **Word alignment.** The interpreter reads command words with SH-2 `mov.w`, which reads only at
   **even** addresses. Growing a box by an *odd* number of bytes pushes the following event op onto an
   odd address, so the engine reads the wrong 16-bit word (e.g. `0x5001` read as `0x0750`), skips the
   op, and the byte stream desyncs → garbage.
2. **Stale `0x3NNN`.** Even with alignment fixed, the renderer's box-extent word `0x3NNN` was left at
   its original value. After a grown box, the renderer's "current box" pointer (`[r14+2]`, written at
   `0x0601E31C`, restored each screen at `0x0601E2CE`) re-seats to the **piece start** instead of the
   next box → the "shows twice" loop.

## The fix (in `src/subst.py`, `substitute_piece_boxes_paginate`)
When rebuilding each box in a box-command piece:
1. **Pad box content to EVEN length** (filler byte after the box terminator, never rendered) so the
   op / next command stays word-aligned.
2. **Update the preceding `0x3NNN` word by the box's growth delta** (`new_content − orig_content`),
   preserving its original slack.

Both are length/structure-preserving for everything else, so the original 2-box+op structure is kept
→ the post-conversation flow (e.g. the monster-encyclopedia menu) is unaffected.

> A `--merge-boxes` approach (collapse the two boxes, move the op) also renders full English but
> CHANGES the structure and **freezes** the post-convo menu. It is DEPRECATED — do not use it.

## Recipe (the proven build, output/073)
```
python3 src/build_mdt.py --attempt NNN --paginate --align-scn --wrap 30 \
  --seg 500a:0,500a:2,500a:4,500a:5,500a:7,500a:8,500a:9 \
  --skip-pieces <other-pieces> E80C
```
- `--paginate` now carries the alignment + `0x3NNN` fix automatically (no flags needed for it).
- `--align-scn` keeps the graphics blob sector-aligned (the 049 trick); the grown MDT is relocated
  and the Java reconstructor recalculates pointers (never hand-patch pointers).
- `--wrap 30` keeps each screen ≤3 lines (box height limit).
- `--seg PIECE:IDX` selects which dialogue segments to translate (full English, box-expanded).

## How to verify (headless, no GUI)
```
tools/ymir-harness/build/jinloop-harness \
  --bios "<Saturn BIOS>" --disc output/NNN/Grandia-DM-patched.cue \
  --state "<a savestate at the convo>" \
  --inject-scn output/NNN/work/E80C/recon/E80C.SCN --inject-addr 0x28033c \
  --inject2 output/NNN/work/E80C/recon/E80C.OFS --inject2-addr 0x28031c \
  --script <input.json> --png-dir <out> --png-every 8
```
The injected SCN/OFS overwrite the loaded script in WRAM (needed because savestates have the dialogue
baked in). Make a GIF/contact-sheet with `tools/make_proof.py <png-dir> <prefix>`.

## Remaining cosmetics (low priority, pre-existing)
Stray `)` glyphs at line ends (control codes drawn in 8×16 mode). Not "junk" in the loop sense.
