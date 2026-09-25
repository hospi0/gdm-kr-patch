# Theater GFX lane (agent a) — drama selection-screen graphics

Goal: translate the baked Japanese graphics on the drama **selection screen** (theater →
press C at the machine → "Listen to drama"): the 「上映メニュー」 header + up to 5 drama-title
thumbnail plates (e.g. 「ガンボ、宴会の後で」 on a starfield). These are **images, not text**.
English titles to draw (from `src/theater/captions/drama{1..5}.json`, read-only): 1 "Gumbo:
After the Banquet" · 2 "This Is the Way of a Man" · 3 "Where They Fall" · 4 "Beyond the End of
the World" · 5 "Cooking Showdown!"; header 上映メニュー → "Screening Menu" / "Now Showing".

Owned: `/FIELD/GM3.STZ` + `/FIELD/GM3.IDX` + **`/FIELD/DORAM.DAT`** (the actual plate source), `src/theater/gfx_*.py`, this doc, `output/gfx_*`.

## STATUS — DECODE fully cracked (all plates decode byte-exact from disc); only the ENCODER remains
Session 4 update (used the pre-load savestate `theater-menu-listen-cursor`): the drama-SELECTION
screen graphics live in **`/FIELD/DORAM.DAT`** (DORAM = ドラマ/drama; LBA 30999, 237552 B), an
outer offset-table archive. Two distinct codecs:

1. **Backgrounds (DORAM slots 3/5)** = the **ST1 Huffman codec** (`tools/mg_codec`/`mg_tree`).
   Decoding slot 3 reproduces the **purple curtain** byte-exact (`doram-curtain-decoded.png`).
2. **The 上映メニュー header + the title plates (DORAM slot 8)** = a **SECOND, engine-resident
   codec** — a fixed-Huffman bit decoder at HWRAM function **`0x0601A716`** with its decode table
   baked into the engine at **`0x0601A9E4`** (so the compressed blob carries NO tree). All
   per-sprite streams are concatenated in slot-8 sub-blob **[6]** (file off `0x9cc` = DORAM
   `0x26500`); a SINGLE call to `0x0601A716` decodes the whole block to VDP1 VRAM contiguously
   from `0x299c0`: header (144×40 @0x299c0) → empty template (152×48 @0x2b040) → **Gumbo plate**
   (152×48 @0x2ccc0) → the other 4 drama plates.

**How it was cracked (live trace from the pre-load menu state):** select 「[ドラマ]を聞く」 (button
`C`) → the 上映メニュー loads. `--bp 0x0601A716` caught the plate-decoder calls (R4=dst VRAM,
R5=src LWRAM=DORAM, R6); a write-watch on `0x25c299cc` pinned the decode loop PC `0x0601AC0A`.

**DECODE is DONE — proven byte-exact from the on-disc DORAM.DAT:** `src/theater/gfx_plate.py`
runs the real engine routine on `tools/sh2emu` (extended with `braf`/`bsrf`/`xtrct`, which it
lacked) over the HWRAM+LWRAM images. header/empty/**Gumbo** all decode at **100%** match vs VRAM
(`docs/theater-gfx/plate-{header,gumbo}-decoded-from-disc.png`). So we can read every plate's
exact 8bpp pixels + palette (DORAM slot 6 → CRAM word `0x500`) straight from disc.

### Plate codec — FULLY reverse-engineered (slot 8 [6]); the ENCODER is the remaining build
The whole slot-8 [6] block (header + ALL plates) is ONE stream, decoded by func `0x0601A716`
(setup) → body loop `0x0601ABE4..0x0601AC0A`. Confirmed:
- **Header @ [6]+0, 24 bytes** (DORAM 0x26500..0x26518): packs the per-symbol code lengths the
  setup reads to build the decode table. **Body starts @ [6]+0x18** (word-aligned).
- **Decode table** (rebuilt per stream into HWRAM `0x0601A9E4`, 256× u16 flat 8-bit lookup):
  entry = `(delta<<8) | (codelen<<4)`; **bit0=0 ⇒ leaf**, group size `2^(8−codelen)`. The symbols
  are **4-bit XOR-deltas** of a running nibble `acc` (`acc ^= delta; acc &= 0xF`; start 0).
  Codebook (delta → MSB-first code): `0xa`→`11`, `0xf`→`101`, `0x6`→`0100` `0x7`→`0101`
  `0x9`→`0110` `0xb`→`0111` `0xc`→`1000` `0xe`→`1001`, `0x0`→`00001` `0x2`→`00010` `0x3`→`00011`
  `0x4`→`00100` `0x5`→`00101` `0x8`→`00110` `0xd`→`00111`, `0x1`→`000000`, and **`000001` = RLE
  ESCAPE** (entry `0x1061`, bit0=1 → secondary table; used for the long flat/transparent runs).
- **Output packing:** 8 nibbles → one big-endian 32-bit word; byte = `(nibbleHi<<4)|nibbleLo`,
  first-decoded nibble = high nibble. Output is 8bpp; render via slot-6 palette @CRAM `0x500`.

**Why the encoder is a careful build (not a quick one) — and the zero-risk plan:**
1. The body bit-reader is **continuous from the header** (at body start the engine still holds
   header word0 in r14, r1=0x180): header and body bits are entangled, so you can't just swap the
   body. Safest: rebuild BOTH header (code-length def) + body for a chosen canonical Huffman,
   matching the setup's header format and the bit reader (barrel shifter, 32-bit BE words, r1 bit
   scaling). The full decoder disasm is in `work/theater/gfx/` traces; `0x0601A716` is the spec.
2. You may **omit the RLE escape** (emit `0x0`→`00001` for repeats) for a simpler-but-larger
   stream; the decoder still decodes it. Larger ⇒ grow [6] + fix the slot-8 directory ([2]/[4]/[5])
   + `relayout.py`. Or implement the escape to stay compact.
3. **HARD GATE:** round-trip every change through `gfx_plate.decode_plate` (the byte-exact oracle)
   — encode → decode must reproduce the input pixels — BEFORE writing any disc. Build
   `output/gfx_001` only after all plates round-trip. Decode is done; this is what makes the ship
   zero-risk.
- This matches the plan's "graphics-heavy / partial" outcome: the render half is done; the disc
  half is gated on reversing the codec (and a size-preserving re-compressor).

## Two graphics systems (don't confuse them)
### A. GM3.STZ "ST5" entries — raw 8bpp backgrounds (NOT the selection plates)
- GM3.IDX @ LBA 39126 (4096 B): 1024 BE `[tag:u16][start_sector:u16]` slots; `parse_idx`
  carries the wrapping low16. Only the **first 369 are real**; 369..1023 are 0xffff placeholders.
  Real = **124 ADX** (dramas = idx **295-299**, do NOT touch) + **245 ST5** (magic `53 54 35 00`).
- ST5 = 64-byte header, payload @ file offset **0x800**, **raw 1 byte/pixel** palette indices
  **0-127** (a 128-color bank → high bit never set; the skewed/low-value histogram is just dark
  imagery, NOT compression). Proven: `gfx_explore.decode_st5(blob, 256)` on **idx321** gives a
  clean **256×224 starfield**; idx0 = 264×231. These are editable in place.
- BUT these ST5 backgrounds are **not** what the selection menu draws (that's system B). They are
  background plates for other theater/field screens. (An earlier draft of this doc guessed ST5
  was DPCM-compressed — that was wrong; ST5 is raw. The compressed thing is system B.)

### B. VDP1 sprites — the actual 上映メニュー selection screen
Captured from **savestate 0** (the selection screen; provided by the coordinator) via the
harness `--dump-wram` (writes `vdp1-vram.bin`, `vdp2-cram.bin`) + `--png-dir`. Parsing the VDP1
command list (`gfx_explore.py vdp1 vdp1-vram.bin`) gives the exact draw list (352×224 screen):

| cmd | size | pos | VDP1 tex addr | CMDCOLR | element |
|---|---|---|---|---|---|
| 1 | 352×224 | (0,0)   | 0x01000 | 0x300 | curtain background |
| 2 | 352×224 | (0,0)   | 0x14400 | 0x300 | menu frame / slot layout |
| 3 | 144×40  | (104,8) | 0x299c0 | 0x500 | **上映メニュー header** |
| 5 | 152×48  | (16,54) | 0x2ccc0 | 0x500 | **ガンボ Gumbo plate (slot 1)** |
| 4,6,7,8,9 | 152×48 | (16/184,…) | 0x2b040 | 0x500 | empty plate template (slots 2-5 + slot1 base) |

- Each is **8bpp, linear (row-major)**, pixel value 0 = transparent. Palette = **VDP2 CRAM**,
  BGR555 **big-endian**; CMDCOLR is the CRAM **word** offset, so pixel `v` → `cram_word[CMDCOLR+v]`
  (header/plates use 0x500 → cram byte 0xA00). Reproduce with
  `gfx_explore.py sprite vdp1-vram.bin vdp2-cram.bin out.png --tex 0x2ccc0 --w 152 --h 48 --cmdcolr 0x500`
  or `tools/mg_gfx.py … --bitmap 152 48 --offset 0x2ccc0 --pal vdp2-cram.bin --pal-offset 0xa00 --pal-be`.
- Renders (proof): `docs/theater-gfx/header-decoded.png` (上映メニュー), `plate-gumbo-decoded.png`
  (ガンボ、宴会の後で on a gray starfield), `screening-menu-screen.png` (the live screen).
- Only Ticket 1 is owned in this save, so slots 2-5 use the empty template (text TBD when those
  tickets are owned). The other 4 title plates are presumably more compressed sprites of the same
  shape.

## /FIELD/DORAM.DAT — the compressed source (ST1 codec)
Outer archive = BE-u32 offset table at the head (`tools/mg_stb.py list|unpack|repack`), **9 slots**.
Decode the ST1 blobs with `tools/mg_tree.decode_blob` using the theater HWRAM image
(`work/theater/gfx/trace0/wram-hi.bin` → copy to `work/mgame/hwram.bin`):

| slot | size | what | how to decode |
|---|---|---|---|
| 0 | 8716 | ? (head `c60f8000…`) | TBD |
| 1 | 28672 | ? (head all-zero) | maybe raw |
| **2** | 512 | curtain palette (256× BGR555 BE) | — |
| **3** | 51652 | **curtain bg** (8 chunks ×16384) → PROVEN decode = purple curtain | `decode_blob(slot3, 0)` |
| **4** | 512 | frame palette | — |
| **5** | 62472 | menu-frame bg (10 chunks) | `decode_blob(slot5, 0)` (slow but works) |
| **6** | 512 | **plate palette** → CRAM word 0x500 (= the plates' CMDCOLR) | — |
| 7 | 1336 | ? (head `00010100 ffff…`) | TBD |
| **8** | 83132 | **header + 5 title plates + empty template** (nested archive) | split format — see below |

- The blob format that works (slots 3/5): `BE16 chunk_count`, then per chunk an **inline tree-def**
  (read by resident SH-2 `0x0601401A` → code-lengths + filter mode) + **nodes** (`0x060144EE`),
  then the Huffman bitstream; chunks thread one cursor. `mg_codec.decode` does the bit/delta/word
  output; `mg_codec.encode` re-emits with the SAME tree (so the game rebuilds an identical decoder);
  `mg_splice.patch_slot` does size-preserving in-place edits. Validated curtain = byte-exact.
- **slot 8 (the plates) does NOT fit that form.** Re-parsing it as an archive gives 7 sub-entries
  (`0x1c` offset table): [2]=396 B and [4]=1644 B and [5]=420 B look like tree/descriptor/index
  tables; **[6]=80624 B is a pure high-entropy bitstream** (head `4010e14d…`, no small BE16 count).
  The plate sprites pack **contiguously in VDP1 VRAM from 0x299c0** (header 0x1680 + empty 0x1c80 +
  Gumbo 0x1c80 …), so slot 8 decompresses to one contiguous region, but its tree-def(s) and
  bitstream are **stored separately** (a different sub-format). Pairing [2]/[4]/[5] trees with the
  [6] bitstream all decoded to garbage (~24% high bytes), so the exact tree-def location / chunk
  descriptor layout is unresolved.

## To finish (the only remaining gap)
1. **Get the plate tree(s).** Best: **live-trace** the plate decompress — boot a *fresh* "entering
   the selection screen" state, `--bp 0x06013F90 --dump-on-bp DIR`; the report logs R4 (src blob),
   R5 (dst VRAM), R6 (tree). This reveals slot 8's exact tree-def + bitstream offsets in one shot.
   **Blocker:** savestate 0 is post-load; reaching the machine from savestate 7 by scripted walking
   failed (no bp hit). **Ask the user/coordinator for a savestate *just before* selecting "Listen to
   drama"** (i.e. on the in-room 600a menu with the cursor on 「[ドラマ]を聞く」), or for working
   ticket-machine nav. Alternatively, finish the static RE of slot 8's [2]/[4]/[5] descriptor tables.
2. With the tree: `mg_codec.decode` slot 8 → verify the header/Gumbo pixels match VRAM (`0x299c0`,
   `0x2ccc0`) → redraw English (caption JSON `title_en`) at 144×40 / 152×48 in the slot-6 palette,
   reusing the existing stroke indices (`mg_codec.snap_to_tree`) → `mg_codec.encode` (same tree) →
   `mg_splice.patch_slot` into slot 8 → `mg_stb.repack` DORAM.DAT.
3. DORAM.DAT will likely change size → **relocate via `src/relayout.py`** (`--name /FIELD/DORAM.DAT`)
   → build `output/gfx_001` → verify from savestate 0 that English renders. (GM3.STZ / the ADX
   dramas are untouched by this — they were a red herring for the plates.)

## Reproduce / continue
```
# 1. capture the selection screen
S=".../savestates/<minigame-disc-hash>/0.savestate"
tools/ymir-harness/build/jinloop-harness --bios "$GDM_BIOS" \
  --disc input/Grandia*Digital*10M).cue --state "$S" \
  --out work/theater/gfx/trace0/r.json --script work/theater/gfx/idle.json \
  --png-dir work/theater/gfx/trace0 --dump-wram work/theater/gfx/trace0   # idle.json=[{"frames":20,"buttons":""}]
# 2. inspect + render
python3 src/theater/gfx_explore.py vdp1 work/theater/gfx/trace0/vdp1-vram.bin
python3 src/theater/gfx_explore.py sprite work/theater/gfx/trace0/vdp1-vram.bin \
  work/theater/gfx/trace0/vdp2-cram.bin out.png --tex 0x2ccc0 --w 152 --h 48 --cmdcolr 0x500
# 3. extract + decode the source
python3 -c "import sys;sys.path.insert(0,'src/theater');sys.path.insert(0,'src');import adx,iso;f=open('input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin','rb');[open('work/theater/gfx/DORAM.DAT','wb').write(adx.read_logical(f,l,sz)) for p,l,sz,r in iso.walk_records(f) if p=='/FIELD/DORAM.DAT']"
python3 tools/mg_stb.py unpack work/theater/gfx/DORAM.DAT work/theater/gfx/doram
cp work/theater/gfx/trace0/wram-hi.bin work/mgame/hwram.bin        # theater HWRAM for mg_tree
python3 -c "import sys;sys.path.insert(0,'tools');import mg_tree;cs=mg_tree.decode_blob(open('work/theater/gfx/doram/003.bin','rb').read(),0);open('curtain.bin','wb').write(b''.join(c['pixels'] for c in cs))"  # = curtain, proven
# 4. (gap) decode slot 8 plates -> edit -> mg_codec.encode -> mg_splice -> mg_stb.repack -> relayout
```

## Worktree / env (this lane)
Branch `theater-gfx`. `input/` + `tools/vendor/` symlinked from main (untracked; never `git add -A`).
`src/theater/{adx,build_e804_menu,review_drama,transcribe}.py` + `captions/*.json` are READ-ONLY
shared (import only). Harness CRAM dump (`--dump-cram`) and `tools/mg_gfx.py` already exist on main.
Savestate **0** = the selection screen (header + Gumbo plate visible).

## Encoder status (2026-06-30) — codec packing CRACKED, byte-exact output, termination pending

The plate ENCODER is now reverse-engineered and **proven byte-exact** against the real engine
decoder (sh2emu oracle): `decode(encode_block(block, orig_[6])) == block` for the **entire
0x15000-byte plate block** and every sub-plate (header / empty / Gumbo). See
`src/theater/gfx_plate_encode.py` + `src/theater/gfx_plate_roundtrip.py`
(`python3 src/theater/gfx_plate_roundtrip.py work/freeze/dump/wram-hi.bin work/theater/gfx/DORAM.DAT`).

### Corrected codec facts (the earlier head-start had the body offset wrong)
- Slot-8 **[6]** (DORAM 0x26500) is **ONE stream** decoding the WHOLE block contiguously to VRAM
  0x299c0; block size = **0x15000 = 86016 B** (from slot-8 dir entry [0] `0001 5000 …`): header
  144x40, empty 152x48 @0x2b040, Gumbo 152x48 @0x2ccc0, then the remaining plates.
- `word0` (u16 BE) @[6]+0. `(word0>>14)&3` = running-acc mode (0 mov / **1 XOR** / 2 sub / 3 nop);
  plates use **XOR** (`acc ^= delta`). `low13 = word0 & 0x1fff` (= 0x10).
- 18 code-length nibbles (9 B) at **[6]+low13+2** (=0x12). Main body bitstream starts byte-aligned
  at **[6]+low13+11** (=0x1b), read as **sequential big-endian 32-bit words, bits MSB-first** (==
  plain MSB-first byte packing). Codebook = canonical Huffman from those lengths == the documented
  book (verified by dumping the engine's built table @0x0601A9E4): `0xa`→`11`,`0xf`→`101`,…,
  `0x1`→`000000`, escape `0x10`→`000001`.
- Output **skip = 0x0a**: the first 10 output bytes (header plate's transparent top-left) are NOT
  symbol-coded (VRAM is 0 there); the body encodes `block[0x0a:]`. First real symbol = delta 0xc
  (pixel 0xc4 run).
- 2 nibbles/pixel, FIRST = HIGH nibble.
- How decode was made reproducible: oracle = `gfx_plate.decode_plate` with the **header-call regs**
  (R5=SRC, R4=VRAM dst) + an **in-theater HWRAM** dump (`work/freeze/dump/wram-hi.bin`) + raw
  DORAM.DAT loaded at LWRAM 0x00210000. The screening-menu savestate's WRAM is post-decode (DORAM
  not resident; built codebook table is stale) and gives garbage — use the freeze HWRAM.

### THE remaining gap — clean TERMINATION (RLE escape, dual-cursor)
The decode is **input-driven** (no output-count stop): it ends when a final **RLE escape** runs the
output up to exactly 0x15000 and its length/extension bits are read from a **SECOND cursor** — 16-bit
BE reads from **[6]+2** (the 16 bytes between word0 and the code-lengths), interleaved with the main
32-bit cursor at [6]+0x18 — landing on the stream's zero tail (`cmp/eq #0` @ ~0x0601a968 → rts).
There are 19 escapes in the block; each codes a **run of background (zero) nibbles** (lengths seen:
8,16,24,32,…,164 bytes) — pure compression. The **no-RLE** encoder here codes those runs as
repeated delta-0 (`00001`), so output is byte-exact but the body has no terminator: after all 86016
correct pixels it keeps consuming source (harness catches this as an out-of-range source read AFTER a
byte-exact block). A real-disc build must implement: (a) the escape run-length format from the
[6]+2 cursor, (b) emit a final escape that hits the target+zero-tail to terminate. Then: splice [6]
→ `tools/mg_stb.py` repack DORAM.DAT → `src/relayout.py` if grown → build `output/gfx_001` → verify
from `theater-screening-menu`. (Note: the screening menu would NOT load from `theater-menu-listen-cursor`
via scripted A/B/C/Start presses — they dismiss the in-room menu; capturing the live plate-decode
call needs working ticket-machine nav or a savestate mid-load.)

### RLE escape — concrete dual-stream data (for finishing the terminator)
Traced 2026-06-30 (`work/theater/gfx/t_rle.py`). The escape run-lengths come from a SECOND 16-bit
cursor read **sequentially from [6]+2**, MSB-first. For the header-block that second stream is the 8
words right after word0: `e14d ed60 2153 5568 88aa cdaf 0142 e000` (= DORAM 0x26502..0x26511), and
it ends in **`e000`** (trailing zeros = the terminator the `cmp/eq #0` exit lands on). The 19 escapes
each code a run of zero (background) nibbles; observed (out_nibble, run_nibbles, main-stream idx8
after the `000001` escape code):
`(264,32,7) (560,24,7) (848,24,7) (1136,16,7) (1432,8,5) (1720,8,7) (2008,8,5) (2296,8,7)
(2584,8,5) (9208,8,4) (9496,8,4) (9784,8,6) (10072,8,6) (10360,16,6) (10648,16,6) (10928,24,6)
(11216,32,4) (11496,328,4)`.
Run length is encoded **across both streams** (main-stream extension bits = idx8/secondary + the
[6]+2 second-stream bits) via the escape path at engine 0x0601A91A..0x0601A9B8 (the `dt r10` /
`mov.w @r9+,r11` secondary refills, r9 = the [6]+2 cursor). Implement that to (a) emit compact
zero-runs and (b) end with an escape whose run hits output==0x15000 and whose second-stream bits
reach the `e000` zero tail → clean `rts`. With that terminator the no-RLE-or-RLE body can be spliced
and shipped (repack + relayout + build output/gfx_001).

### RLE run-length decode — deeper trace (2026-06-30, t_rle3/t_rle2)
The escape (`000001`, sym 0x10) decodes a **run of zero nibbles** in one step: run length `r0`
nibbles is computed in the secondary path (engine `0x0601A87E..0x0601A8EA`; `r14 = r0>>3` zero
output-words filled at `0x0601A8E4`, `mov.l r6,@r8`). After the escape the decoder resumes with a
normal symbol. Per-escape (out_nibble, r0=run_nibbles, idx8 main-low2 = idx8&3, second-cursor words
consumed so far):
`(264,30,3,1) (560,18,3,2) (848,16,3,2) (1136,14,3,2) (1432,4,1,3) (1720,4,3,3) (2008,2,1,3)
(2296,2,3,3) (2584,2,1,4) (9208,2,0,4) (9496,4,0,4) (9784,4,2,5) (10072,6,2,5) (10360,8,2,5)
(10648,18,2,5) (10928,22,2,6) (11216,26,0,6) (11496,320,0,7)`.
The run length is a **variable-length code read from a SHARED bit pool refilled 16-bit-at-a-time
from the second cursor [6]+2** (words `e14d ed60 2153 5568 88aa cdaf 0142 e000`, MSB-first), gated by
the 2 main-stream bits after the escape code (idx8&3) and the secondary Huffman lookup
(`0x0601A872`+, braf jump tables at `0x0601A8AE/0x0601A8F6`). `r0` has NO closed-form from idx8&3
alone (idx8&3=3 → r0∈{30,18,16,14}); it needs the second-cursor bits decoded by that path. **The
`e000` tail (top16=0) is what trips `cmp/eq #0` → rts**, i.e. the stream terminates when the
run-length refill from the second cursor hits the zero word.

**To finish (well-scoped):** port `0x0601A872..0x0601A9B8` (the secondary run-length decoder) to get
the exact `nibbles -> (main 2 bits, second-cursor bits)` encoding, then in `encode_body` emit escapes
for flat zero runs and lay out the second-cursor stream so its zero tail coincides with the final
escape at output 0x15000. Round-trip gate = byte-exact **and** normal exit (no over-read).

## TERMINATOR SOLVED + SHIPPED (2026-06-30, `output/gfx_001`)

The clean-termination gap is closed and the English build is shipped. Key facts (traced live over
`0x0601A872..0x0601A9B8`, the run-length sub-routine of func `0x0601A716`):

- `0x0601A872` is entered **once at setup** (implicit *leading* run) and **again on every RLE
  escape** (`000001`). It reads a variable-length run-length code from the **second cursor r9 =
  [6]+2** (16-bit words, MSB-first, 4 nibbles/word; refill counter r10, buffer r11; prior run value
  carried in r12).
- First secondary nibble `q` selects the path:
  * `q < 13` → direct run = `q + r12 - 6` nibbles. **`q == 6` at setup ⇒ a ZERO leading run**, then
    control falls straight into the main literal loop (`bra 0x0601ac10`). No output written.
  * `q == 14 (0xe)` → the **extend** path (`0x0601a91a → 0x0601a942 → 0x0601a946..0x0601a968`): pulls
    following nibbles into r11 and, when **r11's top 16 bits become 0**, runs `cmp/eq #0,r0 ; bra
    0x0601a85a` = the function epilogue/`rts` — **the clean exit**. (`q == 15` → a similar loop via
    `0x0601a970`.)
- So the whole block ships as: **one ZERO leading run** (secondary nibble `0x6`), **every pixel a
  literal XOR-delta** (skip=0), then **one final main-stream escape** whose secondary read is `0xe`
  then zeros. The terminator secondary stream written at `[6]+2` is **`0x6e00 0x0000`** (`6`=leading
  run 0, `e`=extend-trigger, then zeros → top16==0 → rts). word0 `[0:2]` and the code-length table
  `[low13+2 : low13+11]` are preserved; only the secondary region `[2:low13+2]` is rewritten.

`gfx_plate_encode.encode_block()` implements this. **GATE (`gfx_plate_roundtrip.py`): BYTE-EXACT OK
+ NORMAL EXIT for the original block AND an English-edited block.**

**Ship pipeline** (`src/theater/gfx_ship.py`, plates rendered by `src/theater/gfx_build_plates.py`):
decode → render English → `encode_block` → engine round-trip gate → splice `[6]` (it is the last
blob of the last DORAM slot, so only the tail changes; no container-table edits) → `src/relayout.py`
repoints `/FIELD/DORAM.DAT` → `output/gfx_001` (Track1.bin + Track2.bin + cue). The English block
compresses *smaller* than the JP original (71726 B vs 80624 B for `[6]`; solid text-band fills →
long delta-0 runs), so DORAM.DAT shrank 8898 B; relayout still relocates it to a fresh LBA (193620).
Verified end-to-end: DORAM.DAT re-extracted from the built Track1.bin decodes byte-exact to the
English block.

Plate↔drama map (block order 1,3,5,2,4; identified by baked JP text):
header@0x0 → "Screening Menu"; 0x2d00 → d1 "Gumbo: After the Banquet"; 0x4980 → d3 "Where They
Fall"; 0x6600 → d5 "Cooking Showdown!"; 0x8280 → d2 "This Is the Way of a Man"; 0x9f00 → d4 "Beyond
the End of the World". Palette (captured CRAM @0xa00): drama text = idx 66 (white) on starfield idx
57 (black); header text = idx 193 (blue) on button idx 187 (yellow). Empty template @0x1680 left
unchanged.

**First-pass art / on-screen review pending.** English titles are drawn legibly on a *solid*
text band (the starfield / decorative art behind the JP text is not reconstructed — a polish TODO).
Headless capture of the live 上映メニュー screen is still blocked (from `theater-menu-listen-cursor`
the confirm that loads it isn't any of A/B/C/Start/dir — the menu just dismisses), so the on-screen
before/after needs a **user check**; the byte-exact + clean-exit round-trip is the ship gate and is
green.
