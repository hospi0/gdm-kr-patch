# Minigame-engine graphics/text format (MGAME.BIN + MG* assets)

Reverse-engineering result for the **Game-Room minigame engine** UI text — the shared
Start/Rank/Quit menu (`はじめ` / `じゅんい` / `やめる`) and the per-minigame title logos
(`甲板掃除REMIX`, `お盆でゴン!`, …). This subsystem is **disjoint** from the MDT/SCNRL
dialogue pipeline (E814.MDT etc.) — it loads its own engine + assets and renders with its
own graphics. Tooling: `tools/mg_stb.py`, `tools/mg_gfx.py`, `tools/mg_text.py`, and the
harness flags `--inject-vram1` / `--dump-cram`.

## TL;DR verdict
- The minigame UI text is **pre-rendered 8bpp bitmaps drawn as VDP1 sprites** — **not** a
  tile-font + index table, and **not** any text encoding. "Translating" = redrawing bitmap art.
- **Rendering is fully cracked and proven:** an English `START / RANK / QUIT` menu renders
  correctly, in the menu's own palette and position, in the YMIR harness
  (`work/mgame/POC-english-menu.png`). The graphics format, geometry, and palette are known.
- **The compression codec is now FULLY REVERSED and validated** (`tools/mg_codec.py`). It is a
  **static-Huffman bit decoder + per-stream delta filter (copy/xor/add) + 32-bit additive
  bias**, emitting big-endian 32-bit words to VRAM in ~16 KB chunks. `decode()` reproduces the
  on-disc bg chunk **100 % byte-exact** vs the save-4 ground-truth VRAM (both from live LWRAM and
  **directly from the on-disc file**); `encode()` roundtrips exactly with the same tree.
- **The real source file is `FIELD/KNPAN.DAT`** (甲板 = *kanpan*, "deck") — NOT the
  `MG0_C.STB`/`MGSHP.DAT` files the earlier draft of this doc assumed. KNPAN.DAT is loaded by
  CD-DMA **verbatim** into LWRAM 0x210000 (16384/16384 byte-exact), so it is **directly
  disc-patchable** — there is no opaque load transform. It is an offset-table archive of
  *(512-byte BGR555 palette, compressed-graphics)* pairs; **slot 1** (18,924 B) is the
  bg+logo+menu "甲板掃除REMIX" screen.
- Feasibility class: **graphics-heavy, codec SOLVED, disc-patchable.** Deck-swab is SHIPPED.
- **The static Huffman tree-builder is now SOLVED too** (`tools/sh2emu.py` + `tools/mg_tree.py`),
  so any minigame's title screen is decodable AND re-encodable **fully offline** (no live HWRAM
  capture, no need to reach the coin-gated screen). Validated byte-exact on all 6 KNPAN chunks +
  cross-validated on MGFRG/RFROG/OBONG/MGSUE. See "Static tree-builder — SOLVED" below. Remaining
  per game = layout mapping + bespoke logo art + splice/build; in-game *screenshot* validation of
  the other games additionally needs the coin-gate unlocked (validation-only poke, never shipped).

## How the menu is drawn (authoritative — from the live VDP1 command list)
Captured from savestate 4 (the deck-swab menu, assets resident). Parsing the VDP1 command
table in `vdp1-vram.bin` gives the exact draw list:

| cmd | size | pos (x,y) | tex addr (VDP1 VRAM) | color mode | what |
|---|---|---|---|---|---|
| 1 | 352×224 | (0,0)   | 0x14000 | 8bpp/256-bank, CMDCOLR 0x300 | background + title logo |
| 2 | 128×32  | (112,120) | 0x27400 | 8bpp/256-bank, CMDCOLR 0x500 | `はじめ` (Start) |
| 3 | 128×32  | (112,152) | 0x28400 | 8bpp/256-bank, CMDCOLR 0x500 | `じゅんい` (Rank) |
| 4 | 128×32  | (112,184) | 0x29400 | 8bpp/256-bank, CMDCOLR 0x500 | `やめる` (Quit) |
| 5,6 | 64×64 | (68/84,88) | 0x2c400 | 4bpp/64-LUT | pirate character (animated) |

So each menu item is an independent **128×32, 8bpp, linear (row-major)** sprite texture.
Pixel value 0 = transparent; the visible strokes use palette indices ~3–16 (`は` histogram:
value 0 ≈ 3787 px, then 16/6/15/12/11/5/4/7/9/14). The palette is **VDP2 CRAM** (`--dump-cram`
→ `cram.bin`, 4096 B, BGR555 big-endian); the sprite's CMDCOLR (0x500 for the menu, 0x300 for
the bg) is the CRAM base, so a pixel value `v` selects CRAM entry `0x500 + v`. Rendering
`vdp1-vram.bin` 0x27400 as a 128×32 8bpp bitmap with `cram.bin` at pal-offset `0x500*2` reproduces
`はじめ` exactly (`work/mgame/hajime-realpal.png`).

## Container / archive formats (fully RE'd → `tools/mg_stb.py`)
Two layers:

1. **Outer archive** (`MG*.STB`, and the `MGFRG.BIN`/`MGSUE.BIN` overlays): a **big-endian
   uint32 offset table** at the file head. `word[0]` = table size in bytes → `size/4` slots;
   slots hold absolute file offsets, terminated by `0xFFFFFFFF` then zero-padded. Sub-blob `i`
   spans `offset[i] .. offset[i+1]` (EOF for the last). `tools/mg_stb.py list|unpack|repack`.
   - e.g. `MG0_C.STB`: table_size 0x200 (128 slots), 10 used sub-blobs.

2. **Inner resource header** on each sub-blob: ASCII magic `"ST1\0"` (some `"ST3\0"`), then
   BE u32 fields: `word[1]` low half = header length (0x30/0x34/0x38/0x44); `word[4]` = an item
   count; `word[2]/word[3]` = sub-section offsets/size packed again in `word[6]`. The payload
   after the header is **compressed** for the graphics-bearing blobs (see below).
   `MGFRG.BIN`/`MGSUE.BIN` interleave **(512-byte 256×BGR555 palette, image)** pairs instead.

## Where the bytes live (SOLVED — it is `KNPAN.DAT`, not the MG*/MGSHP files)
> The earlier draft of this section guessed `MGSHP.DAT`/`MGSPR.DAT`/`MG0_C.STB`. That was wrong
> for the deck-swab "REMIX" screen. The actual deck-swab (甲板掃除) assets are
> `FIELD/KNPAN.BIN` (engine overlay), **`FIELD/KNPAN.DAT`** (graphics) and `FIELD/KNSPR.DAT`
> (sprites). `KNPAN` = *kanpan* = 甲板 ("deck"). Found by capturing the live decompressor source
> in LWRAM and searching the disc: the source is byte-identical to `KNPAN.DAT` (CD-DMA'd verbatim
> to LWRAM 0x210000, 16384/16384 contiguous match), at `iso.py` LBA 160557.

**`KNPAN.DAT` (97,500 B) layout** — `tools/mg_stb.py list` parses it (same offset-table format):
an 11-slot BE-u32 offset table, then alternating **(512-byte palette, compressed graphics)**
pairs:

| slot | off | size | what |
|---|---|---|---|
| 0 | 0x00002c | 512   | palette (256×BGR555) |
| 1 | 0x00022c | 18924 | **bg + logo + menu** ("甲板掃除REMIX" screen) — VDP1 sprites |
| 2 | 0x004c18 | 512   | palette |
| 3 | 0x004e18 | 1900  | compressed graphics |
| 4..7 |   | 512 / 29924 / 512 / 1152 | palette, big playfield, palette, small gfx |
| 8 | 0x00d2e8 | 6120  | nested offset-table archive |
| 9/10 |   | 8716 / 28672 | palette-ish / mostly-zero |

The compressed graphics blobs are consumed by the resident **ST1 Huffman+delta codec** below.

## The codec (resident decompressor @ HWRAM 0x06015DF0) — REVERSED
Located by driving save-5 → menu (nav solved) and watchpointing the VDP1-VRAM writes; the writer
is PC `0x06015E8A` inside the function at **`0x06015DF0`**. Disassembled with the new
`tools/sh2dis.py`. Implemented in **`tools/mg_codec.py`** (`decode`, `decode_ex`, `encode`).

Per-stream parameters (set by the caller at `0x06013F90`; args R4=tree base, R5=root, R6=filter
mode, R7=bias; src/dst kept in `[0x06014D9C]`/`[0x06014DA0]`; flag `[0x06014D4C]` selects the
word-output path, =0 here):

- **Bit input** — MSB-first from big-endian 32-bit source words. Initial mask =
  `0x80000000 >> 8*(src&3)` (start at byte `src&3`); src is then word-aligned down. Mask rotates
  right each bit; when it wraps from 0x1, the next source word is loaded.
- **Huffman walk** — node at byte-offset `node` in the tree table has children `u16[base+node+4]`
  (bit 0) and `u16[base+node+6]` (bit 1). Walk from `root` while `node > 0x800`. When
  `node <= 0x800` it is a leaf: `node==0x800` ⇒ **end-of-stream**; else symbol = `node >> 3`.
- **Delta filter** — running 1-byte accumulator `acc` (persists across the whole stream),
  selected by `mode` via the self-modifying op-table at `0x060162C8` =
  {0:`mov` copy, 1:`xor`, 2:`add`, 3:`nop`}. Output byte = `copy`→sym, `xor`→acc^=sym,
  `add`→acc=(acc+sym)&0xff.
- **Word assembly** — four filtered bytes pack big-endian into a 32-bit word, `bias` (=r7·0x10001)
  is added, the word is stored to dst, dst+=4; at EOS any partial word is flushed.
- Output is produced in **~16 KB chunks**, one decompressor call per chunk; a blob is a sequence
  of chunks each with its own (root, mode) descriptor sharing the blob's Huffman forest.

**Validation (deterministic):**
- `decode()` of KNPAN.DAT slot-1 chunk-0 (src off 0x263, root 0xFB0, mode 1) → **16384 bytes,
  EOS-terminated, 100.00 % byte-exact** vs the save-4 ground-truth VDP1 VRAM at 0x14000 (the
  bg). Verified both from the live LWRAM source and **straight from the on-disc `KNPAN.DAT`**.
- `encode()` of that chunk's pixels with the same tree → decode round-trips **byte-exact**
  (16384/16384); re-encoded size 6736 B ≈ original 6737 B. The forest covers 246/256 byte values.

## Container framing (mapped; remaining work for a full standalone re-encoder)
The blob is **self-describing**. The chunk-loop caller at `0x06013F90`:
1. sets the stream cursor `[0x06014D9C] = blob source`,
2. calls the **tree builder** `0x0601491C` **twice** (builds the Huffman forest at 0x06028800
   from inline length/structure data; nodes are 8 bytes, written by `0x0601401A`),
3. reads a **BE16 chunk count** from the cursor (cursor += 2),
4. per chunk: `bsr 0x0601401A` (→ filter mode), `bsr 0x060144EE` (→ root), then
   `jsr 0x06015DF0` (decompress); repeats `count` times.

To re-encode in place we either keep both tree-defs + descriptors byte-identical and swap only
the per-chunk bitstreams (size changes ripple → use the KNPAN offset table to relocate the slot,
à la `src/relayout.py`), or fully reverse `0x0601491C`/`0x0601401A`/`0x060144EE` to regenerate the
header for new art. `mg_codec.encode()` already emits a valid bitstream for any given tree+root.

## Proven render PoC (the tractable half)
`tools/mg_text.py` draws ASCII into a 128×32 8bpp menu-sprite bitmap reusing the menu's own
stroke indices. The 3-item block (`START`/`RANK`/`QUIT`, 12,288 B) injected into VDP1 VRAM at
0x27400 via `--inject-vram1` (savestate patch, before LoadState) and booted from save 4 renders
the English menu correctly — palette, position, transparency all intact
(`work/mgame/POC-english-menu.png` vs original `work/mgame/orig-jp-menu.png`).

> Note: `--inject-vram1` patches VDP1 VRAM in the **savestate**, which proves the *art* renders.
> It is **not** a disc-patch proof (save 4 already has assets resident); a shippable patch still
> requires the codec work above. This matches the plan's "graphics-heavy / partial" outcome.

## Minigame ID / file map (for the logo sweep, once the codec is cracked)
0 = Deck-Swab `MGSHP`/`MGAME` (only one freely bootable; others coin-gated **by design**),
1 = Frogs `MGFRG`/`MG1_1`, 2 = Sue-Bride `MGSUE`, 3–7 `MG3_1…MG7_1` (`MG2_1` absent).
Logos are per-minigame pre-rendered bitmaps inside those archives (same compressed-graphics case).

## Save-5 → menu navigation (SOLVED)
The earlier note that save 5 couldn't be driven to the menu is fixed. The terminal launch
sequence (frames, control-pad): idle 20, **C** 8, idle 32, **C** 8, idle 32, **Down** 8, idle 16,
**C** 8, then idle ~260 for the load. (C talks → text → menu with cursor on もどる/back; Down →
ゲームを始める; C launches.) Reproduced headless in `work/mgame/nav2/` and used to trace the
decompressor and capture the source.

## Tools added (document in `tools/setup.sh` style)
- `tools/mg_stb.py list|unpack|repack FILE …` — outer offset-table archive (un)packer (constant-size repack). Works on `KNPAN.DAT` too.
- `tools/mg_gfx.py FILE OUT.png [--bpp --tile --cols --bitmap W H --pal --pal-offset --pal-be]` — Saturn 4/8bpp tile/bitmap → PNG (BGR555); no deps.
- `tools/mg_text.py "TEXT" out.bin [--w --h --val --hi --scale --x --y]` — render ASCII into an 8bpp menu-sprite bitmap.
- **`tools/mg_codec.py decode|encode`** — the ST1 Huffman+delta codec (decompress + re-compress); validated 100% vs ground truth + roundtrip-exact.
- **`tools/sh2dis.py FILE --start ADDR [--count N]`** — minimal SH-2 disassembler used to reverse the codec.
- `tools/mg_loop.py` — autonomous inject→run→screenshot wrapper (VRAM-inject render-proof).
- Harness (`tools/ymir-harness/main.cpp`): `--inject-vram1`/`--inject-vram1-addr`, `--dump-cram`,
  and **`--dump-on-bp DIR` + `--dump-bp-hit N`** (snapshot LWRAM/HWRAM/VDP1-VRAM at the Nth
  breakpoint hit — used to capture the clean, unconsumed decompressor source).

## Container framing — SOLVED (`tools/mg_knpan.py`)
The deck-swab title screen is **three independent decompression calls** (chunk-loop caller
`0x06013F90`, arg R4 = blob source), one per KNPAN offset-table slot — found by breakpointing the
caller and reading R4:

| call | R4 (file off) | slot | dst (VDP1) | chunks |
|---|---|---|---|---|
| bg/logo | 0x22C | 1 | 0x14000 | 0,1,2,3,4 (one 352×224 8bpp sprite) |
| menu    | 0x4E18 | 3 | 0x27400 | 5 (3× 128×32 START/RANK/QUIT sprites) |
| *(playfield, a different minigame)* | 0x5784 | 5 | 0x40000 | — |

Each blob = **header** (two inline Huffman tree-defs + BE16 chunk count + first root) then chunks
**threaded by a shared source cursor**. Per chunk the caller reads a fresh inline tree-def
(`0x0601401A` rebuilds the forest at `0x06028800`) + a root (`0x060144EE`), then decompresses
(`0x06015DF0`). **Critical detail:** the decompressor exit (`0x06015EA4–0x06015ECE`) backs the
source cursor up **0–4 bytes to a byte boundary** from the final bit mask, so each chunk's EOS word
**overlaps** the next tree-def. `mg_codec.decode_end()` models this exactly; `mg_knpan.patch()`
rebuilds each blob in place (descriptors kept byte-verbatim, OR-merged onto each EOS word) and is
confined to its slot. Full re-encode round-trips **byte-identical**.

The 6 deck-swab chunks (file off / dst / root / mode / size):
`0x263/0x14000/0xFB0/1/16384 · 0x1CE5/0x18000/0xF98/1/16384 · 0x354D/0x1C000/0x808/0/16384 ·
0x3D71/0x20000/0x808/0/16384 · 0x4595/0x24000/0x808/0/13312 · 0x4E4E/0x27400/0x890/1/12288`.
Per-chunk trees were captured live from HWRAM `0x06028800` at each decompressor hit
(`work/mgame/tree_h8..h13.bin`); they are deterministic from the verbatim descriptors, so
re-encoding (same tree) stays engine-valid.

## Status — SHIPPED (deck-swab) ✓
- **Full slot-1 decode validated**: all 6 chunks 100 % byte-exact vs the save-4 VDP1 VRAM
  (whole screen, not just chunk 0). Container parser/splicer = `tools/mg_knpan.py`.
- **English deck-swab screen proven in-game** on a built disc (`output/mg_NN`, KNPAN.DAT injected
  in place at LBA 160557, same size): **`DECK SWAB REMIX`** logo + **`START / RANK / QUIT`** menu
  render from the real on-disc decompression — correct palette/position/transparency, no
  garble/freeze. Booted save 5, drove idle/C/idle/C/idle/Down/idle/C, screenshotted, vision-verified.
  Proof: `work/mgame/SHIPPED-english-logo+menu-ingame.png`.
- Logo authoring = `tools/mg_logo.py` (greyscale-kanji detect → horizontal wood in-paint with the
  interlocked chrome `REMIX` protected → embossed `DECK SWAB`). Menu = `tools/mg_text.py`.
- A small `除`/`REMIX` chrome remnant remains where the two are pixel-interlocked in the original
  art (one connected component) — cosmetic, not a tooling limit.

## Static tree-builder — SOLVED (`tools/sh2emu.py` + `tools/mg_tree.py`)
The per-chunk Huffman forest is now built **statically/offline** from the inline tree-defs, removing
the dependence on live HWRAM capture (and therefore on reaching each coin-gated screen). Rather than
hand-port the bit-level builder, we **execute the real resident engine code** with a minimal SH-2
interpreter (`tools/sh2emu.py`). The build is two engine routines, threaded by the caller
`0x06013F90` (BE16 chunk count, then per chunk: build, build, decode):
- **`0x0601401A`** — reads the inline tree-def → fills a per-symbol code-length table at
  `tree[sym*8]` (the `[0,0x800)` region); **returns the chunk's delta-filter mode** in r0. The
  tree-def is `[byte0 nibbles][byte1][32-byte 256-bit symbol-presence bitmap][code-length data…]`;
  helpers `0x060147C0` (÷ → byte index), `0x0601491C` (mod → bit index), `0x06014AC4` (bit test).
- **`0x060144EE`** — builds the internal Huffman nodes from those lengths (engine-specific code
  assignment — e.g. the transparent symbol gets the length-1 `1` branch); **returns the root node
  offset** in r0. (The earlier draft mislabeled this routine as just a "root reader".)

`tools/mg_tree.py`: `build_chunk(blob, treedef_off)` → `(tree, mode, root, cursor_after)`;
`decode_blob(blob, blob_src)` threads a whole title-screen blob. **`mg_tree.py selftest` is
byte-exact**: all 6 KNPAN chunks decode identically to the live-captured `tree_h8..h13` ground truth,
with matching mode+root. Cross-validated on independent files: `MGFRG.BIN` slot-1 decodes to crisp
`タイトル画面` text (`docs/mgame-gfx/mgfrg-placeholder-titlescreen-decoded.png`), and RFROG/OBONG/MGSUE
chunks **encode→decode round-trip byte-exact** — i.e. the full offline decode→edit→re-encode SHIP
pipeline works for any minigame, no emulator needed.

## Real per-game title assets (corrected map)
The `MG*.BIN` files (`MGFRG.BIN`, `MGSUE.BIN`, …) are **engine overlays**: their slot-1 is a generic
`タイトル画面` placeholder, and they carry the **shared** `START/RANK/QUIT` menu blob (MGSUE.BIN
slot-3 is **byte-identical** to KNPAN.DAT's menu → the English menu ports directly). The real
per-game title-screen graphics are dedicated **KNPAN-style `.DAT` containers** in `/FIELD/` (same
offset-table-of-(palette,ST1-gfx) format), found by the `XXX.BIN`+`XXX.DAT`+sprites naming analogy
that already held for deck-swab (`KNPAN.BIN`/`KNPAN.DAT`/`KNSPR.DAT`):
- **Frogs** → `RFROG.DAT` (+`RFROG.BIN`); **Tray-bonk (お盆)** → `OBONG.DAT`; deck-swab → `KNPAN.DAT`.
- Sue-Bride → `SUEWN.BIN`/`SWN6*.DAT`; plus `TITKN.DAT`/`TITL.DAT` (collection title screens).
Within a game's `.DAT` the bg and logo are often **separate sprites in different slots** (e.g.
`RFROG.DAT` slot-1 = flat bg, logo elsewhere) — unlike deck-swab where bg+logo were one slot. So the
remaining per-game work is **layout mapping** (which slot=logo, its dst/dims/palette region) + bespoke
English logo art, then splice (à la `mg_knpan.patch`) + build. The codec + static tree builder are
done and game-agnostic.

## Remaining for full in-game validation (not done)
`mg_tree` makes every game's screen decodable+re-encodable offline. In-game *screenshot* validation
of the non-deck-swab games still needs the coin-gate unlocked: the games are gated by a coin
balance / per-game unlock flag in WRAM (MGAME.BIN + launch bytecode are byte-identical, not our bug).
Plan (validation-harness only, NEVER shipped): boot save 5, find the coin/unlock address (search the
displayed value or breakpoint the terminal's gating check), then poke it via the harness'
**existing `--inject-scn FILE --inject-addr ADDR`** (writes bytes into WRAM after LoadState — already
present, no new flag needed), and drive each terminal's nav. The room has multiple terminals, so each
game needs its own walk-to-terminal nav sequence (deck-swab's is documented above).

## Full-sweep investigation (2026-06-28 — offline pipeline reproduced; in-game BLOCKED)
Worktree re-derived the offline pipeline from scratch (gitignored `work/` does not carry over):
regenerated `work/mgame/hwram.bin` from a fresh save-5 HWRAM dump, extracted the per-game `.DAT`/`.BIN`
containers with `src/iso.py extract` (note: extract takes the **basename**, e.g. `RFROG.DAT`, not the
full `/FIELD/...` path), and confirmed `tools/mg_tree.decode_blob` reproduces KNPAN's 6 chunks
byte-exact (matching offsets/modes/roots in `mg_knpan.CHUNKS`). So decode/encode/render is fully
reproducible with NO emulator. New tool `tools/mg_explore.py` decodes every chunk-bearing slot of a
KNPAN-style `.DAT` and renders each to PNG (paired 512B palette) for slot identification.

**Slot-structure findings (decoded + rendered offline):**
- **Menus are per-game and DECODE TO READABLE JAPANESE** (8bpp 128×32 sprites stacked). The earlier
  "shared menu ports directly to every game" is only *partly* true:
  - **Sue (`MGSUE.BIN` slot 3, `00011100ffff9000…`) is byte-identical to KNPAN's 3-item menu**
    (はじめ/じゅんい/やめる) — ports directly. ✓
  - **Tray-bonk (`OBONG.DAT` slot 3) is a DIFFERENT 5-item menu**: はじめ / じゅんい / やめる /
    とくてん (score) / つづき (continue) — 20480 B = 5×(128×32). Must be re-authored, not ported.
  - So menu re-authoring is per-game; only the 3-item games share KNPAN's blob.
- **The `MG*.BIN` engine overlays carry: a green "Ranking" screen (slot 5, `Ranking` in orange),
  the menu (slot 3), a 512×224 playfield (slot 7, 114688 B), and sprite atlases.** The dedicated
  `.DAT` (RFROG/OBONG/…) carries the title **bg** (RFROG slot 1 = flat blue, OBONG slot 9 = wooden
  お盆 trays) + sprite/font atlases.
- **The per-game TITLE LOGO (the "甲板掃除REMIX" equivalent) was NOT cleanly isolated offline.** The
  large non-bg slots (RFROG s35 28416 B; MGSUE s1 43520 B; OBONG s1 33152 B) decode to **garble at
  every guessed width** — they are not 8bpp-linear-352 like the deck-swab logo, so they need real
  per-game **layout mapping** (dst/dims/bpp/tiling). Resolving that reliably needs a **real in-game
  title capture** to know the geometry — which is gated (below).

**In-game validation BLOCKER (the gate for "proven in-game"):** save 5 drops the player in the Game
Room facing the deck-swab PC; the documented `idle/C/idle/C/idle/Down/idle/C` nav reaches the deck-swab
menu fine. But the **other 6 minigames are arcade cabinets around the room**, and:
  1. a **follower NPC (green turtle)** stands next to the player and intercepts the C interact button
     wherever you walk (it speaks "やあ お兄ちゃん達！久しぶりだね!!");
  2. headless blind nav to a specific cabinet **face** is unreliable (6 identical arch cabinets, no
     screen feedback until a frame lands);
  3. when the player IS adjacent+facing a cabinet, **C produces no menu/message** — consistent with
     the other games being **gated/inert** in save 5 (only deck-swab unlocked), so there is no event
     to breakpoint at the gate from this position.
Net: the coin/unlock ADDRESS was **not** located (no interaction fires to trace), and nav to each
cabinet was **not** mapped. **Fastest unblock = the user provides savestates positioned facing each
cabinet (like save 5 faces deck-swab), or a save with all games unlocked / coins maxed.** Then each
title renders, geometry is captured, logos can be authored + offline-validated + shipped.

### Unlock-hunt follow-up (event-VM trace)
Tracing the event-VM dispatch (`0x0601E5EC`) during the deck-swab talk shows the **game-room script
runs in LWRAM ~0x280CB0** (opcodes captured: `0x1001 0x4040 0x1000 0x3006 0x8000 …`). So the gate is
a per-cabinet unlock-flag test inside this event-VM script — locating the exact flag needs the
**event-VM opcode set reversed** (a separate large effort; no flag-bank doc exists yet). The displayed
deck-swab interaction is a field menu **もどる / ゲームを始める (Start) / ゲームの説明を見る (Instructions)** —
**no coin counter is shown**, confirming the gate is per-game unlock flags, not a visible coin balance.
Savestates 0–9 hold no game-room save with different unlock state (1=shop GOLD 1000g, 0/3=theater,
2=casino), so no memory-diff shortcut. **Coordinator-approved fallback taken: offline menu authoring +
in-game proof via the one reachable terminal (below).**

## MENUS TRANSLATED + generic splicer (2026-06-28) — offline-validated, shared menu IN-GAME PROVEN
- **`tools/mg_splice.py`** — GENERIC KNPAN-style blob re-encoder (what `mg_knpan.py` does for deck-swab,
  for ANY `.DAT`/`.BIN`): threaded, size-preserving, descriptor-OR-merge, driven by `mg_tree.decode_blob`.
  Roundtrips **byte-identical** on KNPAN/MGSUE/OBONG menu slots + RFROG/OBONG multi-chunk bg slots.
- **OBONG (tray) 5-item menu → `START / RANK / QUIT / SCORE / RESUME`** (`とくてん`→SCORE, `つづき`→RESUME):
  authored (`mg_text.py`, val=16 scale=2 to fit the slot's Huffman budget — English block-letters compress
  worse than the kana the tree was built for, so size-fit needs the short-code stroke value 16), spliced
  size-preserving into `OBONG.DAT` slot3 (0x41c0), **decodes byte-exact + renders correctly**
  (`docs/mgame-gfx/obong-menu-english-offline.png`). On the built disc `OBONG.DAT` re-extracts + decodes
  to the authored English.
- **Sue 3-item menu** = byte-identical to KNPAN's shared menu → English `START/RANK/QUIT` ports directly
  into `MGSUE.BIN` slot3 (0x5618), offline-validated (`docs/mgame-gfx/sue-menu-english-offline.png`).
- **IN-GAME PROOF of the shared 3-item menu**: the SAME English menu spliced into `KNPAN.DAT` slot3 and
  injected on disc renders **`START / RANK / QUIT`** in the deck-swab terminal, booted from save 5, from the
  real on-disc decompression (`docs/mgame-gfx/shared-menu-english-ingame.png`). Proves `mg_splice.py` emits
  engine-valid output and the shared-menu English path works in-game; Sue's menu is byte-identical so it is
  equivalently proven. (Non-deck-swab games can't be screenshotted directly — still gated.)
- Disc built at `output/mg_01/` (OBONG + Sue + KNPAN English menus injected in place, all same-size).
  **Validation-only:** nothing unlock/coin-related is baked in; E814/launch bytecode untouched.

### Still remaining (per game)
- **Title LOGOS** for all 7 games: NOT authored — candidate logo slots decode to garble at every guessed
  geometry, so they need a real in-game title capture (gated) OR per-game sprite-setup RE for dims/bpp/tiling.
- **Menus for the STB-overlay games** (3=パンチラ→"PEEK!", 5=Baseball, 6=Speed-Eat, 7=Baal): their menu
  blobs live nested inside `MG3_1/MG5_1/MG6_1/MG7_1.STB` (the inner ST1/ST3 archive layer), not at the
  top-level offset table — need nested unpacking before splicing. Final English names (user):
  FROGS, SUE'S WEDDING, PEEK!, TRAY BONK!, BASEBALL, SPEED EATING, BAAL.

## SWEEP session 2 (2026-06-28) — all reachable menus done; 3 logos resolved; STB menus = no per-game blob

Offline pipeline re-derived from scratch (regenerated `work/mgame/hwram.bin` from a fresh save-5
HWRAM dump via the harness `--dump-wram`, extracted every `.DAT`/`.BIN`/`.STB` with `src/iso.py`).
`mg_splice.roundtrip` byte-exact on KNPAN bg+menu slots; static tree builder operational.

### New tooling
- **`mg_codec.snap_to_tree(pixels, tree, root, mode, palette_rgb)`** — palette-aware delta-safe
  pre-pass. The fixed per-chunk Huffman tree only has leaves for the **filter-symbols present in
  the ORIGINAL stream** (mode 0 = raw value, mode 1 = consecutive XOR, mode 2 = consecutive add),
  so authored art that introduces a new symbol can't be encoded. `snap_to_tree` nudges each
  unencodable byte to the in-tree value whose palette colour is nearest the target; unedited
  original pixels pass through unchanged. `mg_splice.patch_slot(..., snap=True, palette_rgb=)`
  wires it in. **This is what makes arbitrary logo/menu authoring fit the frozen forest.**
  Note: sparse-tree chunks (deck-swab wood bg) still constrain placement; rich-tree chunks
  (colourful logos, 254-255 leaves) snap ~losslessly.
- **`mg_text.FONT` completed** (added W V Z J, digits, `-` `'` `.`). A missing **`W`** glyph — not
  the codec — was dropping letters in the first logo attempts.
- **`mg_menu.py author DAT BLOB SLOT_END OUT ITEMS`** — author an N-item English menu sprite-stack
  (centred per 128x32 cell) + size-preserving splice + decode-roundtrip check.
- **`mg_logo_author.py DAT BLOB SLOT_END W H PAL_OFF "A|B" OUT`** — clear a resolved title slot to
  transparent + centred embossed English title + snap-splice. Geometry args from the table below.

### Per-game MENU status (offline-validated unless noted)
| # | game (E814 name) | menu file/slot | items (JP→EN) | status |
|---|---|---|---|---|
| 0 | Deck-Swabbing REMIX | KNPAN.DAT s3 @0x4E18 | はじめ/じゅんい/やめる → START/RANK/QUIT | **IN-GAME PROVEN** |
| 1 | Leen Hates Frogs! | MGFRG.BIN s3 @0x2bd0 | original art is **already English** START/RANKING/EXIT | no change needed |
| 2 | Sue! Gantz's Bride Plot | MGSUE.BIN s3 @0x5618 | byte-identical to KNPAN shared → START/RANK/QUIT | offline ✓ |
| 4 | Bonk-a-Tray! | OBONG.DAT s3 @0x41c0 | +とくてん/つづき → +SCORE/CONTINUE (5-item) | offline ✓ |
| 3,5,6,7 | Feena's Panties / Hot-Blooded Showdown! / Big-Eater Grandia Cup / Baal's Revenge | MG3/5/6/7_1.STB | **NO per-game menu blob found** | see below |

Dictionary (commit 396acc8): はじめ=Start, じゅんい=Rank, やめる=Quit, とくてん=Score, つづき=Continue.

### STB-only games (3/5/6/7) — there is NO KNPAN-style menu blob in their `.STB`
`MG[n]_1.STB` is an outer offset-table archive whose sub-blobs are each an **`ST1\0`-magic resource**
(0x30/0x34/0x38-byte header: w1 lo = header len, w2/w3 = intra-blob offsets, w4 = item count, w5 =
load address, w7 ≈ dims). The payload after the header is **NOT a KNPAN chunk-stream** (no BE16
chunk count + treedef; high-entropy → a *different* compression framing than the inline-chunk codec).
A full scan of every 2-aligned offset for the menu signature (`00 0N 11 ..` count+treedef, validated
to hit MGFRG s3) finds **zero** menu chunk-streams in MG3/5/6/7_1.STB, MG__S.STB, MG0_C.STB, MGAME.BIN.
**Conclusion:** these four games carry no per-game Start/Rank/Quit blob; they almost certainly reuse
a SHARED menu rendered by the engine at runtime (the four games that *do* bundle a menu each have a
dedicated `.BIN` overlay; 3/5/6/7 have none). Translating that path needs either (a) the ST1-wrapped
resource codec reversed, or (b) the gated overlay/in-game capture to confirm which shared blob is
drawn. Both are gated/separate-RE; documented, not blocked-by-our-tooling.

### Per-game LOGO geometry (recovered offline by rendering decoded slots)
| game | title file/slot | geometry | palette | result |
|---|---|---|---|---|
| Deck-Swabbing REMIX | KNPAN.DAT s1 @0x22C | 352x224 8bpp linear | slot0 @0x2c | re-authored "DECK-/SWABBING REMIX" — **IN-GAME PROVEN** |
| Leen Hates Frogs! | RFROG.DAT s35 @0x34b48 | **296x96** 8bpp linear | slot34 @0x34948 | JP リーンのカエルはいやっ renders crisp; EN authored offline (gated) |
| Bonk-a-Tray! | OBONG.DAT s1 @0x23c | **296x112** 8bpp linear | slot0 @0x3c | JP お盆でゴン! renders crisp; EN authored offline (gated) |
| Sue! Gantz's Bride Plot | MGSUE.BIN s1 @0x258 (43520B) | **320×136 8bpp linear** (NOT tiled/4bpp — "4-streak" was a wrong-width shear; 238 distinct vals, val 0 = transparent 55%; width found by max vertical-continuity of the transparency mask) | slot0 @0x58 **BGR555 big-endian** | **SOLVED** — JP スーあやうし！ガンツの花嫁大作戦 renders crisp; EN "SUE! GANTZ'S / BRIDE PLOT" authored + offline-validated (gated) |
| Feena/Showdown/Big-Eater/Baal | inside MG3/5/6/7_1.STB ST1 resources | ST1-resource codec lives in a gated overlay (see "SWEEP session 3"); not decodable offline | — | **blocked offline** (needs unlock save) |

Engine uses a **296-wide** title sprite for the dedicated-`.DAT` games (Frogs, Tray-Bonk both 296×{96,112}).
Authored logos clear the slot to transparent (index 0) + centred embossed English title; the colourful
logo slots have near-full Huffman trees (254-255 leaves) so `snap_to_tree` is ~lossless.

### Discs built (validation-only; NOTHING unlock/coin baked in; E814/launch bytecode untouched)
- `output/mg_02` — KNPAN.DAT (English logo + menu) → deck-swab terminal **proven in-game** from save 5
  (`docs/mgame-gfx/deckswab-logo-menu-english-ingame.png`).
- `output/mg_03` — adds MGSUE.BIN + OBONG.DAT English menus (all size-preserving, in-place); on-disc
  re-extract + decode confirms English. Sue/Tray-Bonk menus are gated → offline-validated only.
- `output/mg_04` — adds the **English Sue title logo** into MGSUE.BIN slot1 (size-preserving, in-place
  @LBA 174528). On-disc re-extract is byte-identical to the authored file and its slot1 decodes to the
  authored 320×136 English pixels. Gated → offline-validated only.

## SWEEP session 3 (2026-06-29) — Sue logo geometry SOLVED; ST1 codec verdict = different format, gated

### TASK 2 — Sue logo geometry (SOLVED, authored, offline-validated)
`MGSUE.BIN` is a **KNPAN-style archive** (inline-chunk framing, resident Huffman+delta codec — NOT
ST1). Slot 1 @0x258 decodes byte-exact via `mg_tree.decode_blob` to **43520 B = 16384+16384+10752**
(3 chunks, modes 1/1/0) — a single linear 8bpp framebuffer. Pixel stats: 238 distinct values, max 255
(genuinely 8bpp, not 4bpp), value 0 = transparent (55%). The earlier "garble / 4-streak ⇒ tiled/4bpp"
was a **wrong-width shear**. Recovered the width by maximizing vertical-continuity of the transparency
mask over all widths 32..700: **W=320 (exact, 320×136) scored 0.973** (next: 640 @0.947). Rendered
320×136 8bpp linear with slot0 palette as **BGR555 big-endian** → the JP logo renders perfectly:
top banner スーあやうし！ + bottom ガンツの花嫁大作戦 + gold star burst. Authored EN
"SUE! GANTZ'S / BRIDE PLOT" via `mg_logo_author.py … 320 136 0x58 --core 203 --outline 64 --scale 4`;
size-preserving snap-splice into slot1; round-trip byte-exact (all 19672 changed bytes confined to
0x2cc..0x5414 inside the 0x258..0x5418 slot); decode of the authored slot == intended pixels.
Preview `work/mgame/authored/sue_logo_en.png`. (Gated → in-game proof pending unlock save.)

> **⚠️ SUPERSEDED (see "SWEEP session 4" below).** The session-3 verdict that follows
> ("ST1 different/gated, games 3/5/6/7 impossible offline") is **WRONG**. It only looked at
> `MG[n]_1.STB` (which are ST1 *sprite-atlas data* archives, a red herring) and missed each
> game's **engine-overlay companion `.DAT`/`.BIN`** (`FI_DT.DAT`, `BY100.DAT`, `BARLG.DAT`,
> `HYABG.BIN`). Those ARE KNPAN-style and decode with the **existing resident codec, fully
> offline**. All four logos + the 3/5 menus are now authored & offline-validated. Read
> session 4 first; the text below is kept only for history.

### TASK 1 verdict — the ST1 resources are a DIFFERENT format from the KNPAN inline-chunk codec, and their decompressor is GATED (not obtainable offline)
The games **3/5/6/7** logos/menus live in `MG3/5/6/7_1.STB` as `ST1\0`-header sub-blobs. Tested whether
these are the SAME resident Huffman+delta codec with merely different framing — **they are not**, on
five independent lines of evidence:
1. **Framing is fundamentally different.** Each ST1 sub-blob has a fixed **0x30-byte header** (BE32
   fields: w1 lo = header len; w2/w3 = section sizes/offsets, re-packed in w6; w4 = item count;
   w10 = a VDP1-VRAM-style dst e.g. 0xa000/0xc000/0xe000; w7 ≈ dims/clip). KNPAN blobs instead begin
   with a **BE16 chunk count + an inline tree-def** (`11 01 …` / `01 00 …` + 32-byte symbol bitmap).
   There is no inline tree-def anywhere in an ST1 blob.
2. **The resident codec cannot decode it.** Forcing the engine tree-builder at the ST1 header boundary
   returns an **invalid filter mode (15)** — valid modes are only 0/1/2/3 (the delta op-table has 4
   entries) — i.e. the bytes are not a tree-def. Forcing a decode anyway **never reaches the EOS leaf**
   (runs off the end; had to be killed) — a valid stream terminates at node 0x800.
3. **No ST1 dispatch exists in any offline code.** The literal `ST1\0`/`ST3\0` magic appears in **zero**
   bytes of save-5 resident HWRAM/LWRAM, and in none of MGAME.BIN / KNPAN.BIN / RFROG.BIN / OBONG.BIN /
   MGFRG.BIN. The engines that DO use the resident codec (KNPAN/RFROG/OBONG, all base 0x0602c018,
   referencing codec tree-base 0x06028800) are exactly the games that use **inline-chunk `.DAT`s**, not
   ST1. (MGSUE/MGFRG are KNPAN-style archives too.)
4. **Games 3/5/6/7 have NO offline engine/asset overlay at all** — no dedicated `.BIN`/`.DAT` like the
   other five games; only their `.STB` (whose sub-blobs are all ST1 *data* resources, not code). Their
   engine + the ST1 decompressor therefore load only from a **coin-gated overlay** when the game is
   launched — exactly the "gated overlays can't be traced live" case, and the overlay file was not
   located on disc offline.
5. ST1 payload entropy ≈ 6.84 bits/byte (compressed, but below the 7.10 of a real KNPAN bitstream) and
   shows no inline-tree structure — consistent with a *different* compression, inconclusive on its own.

**Conclusion:** ST1 is a distinct FRONTIER-library resource format, NOT the KNPAN inline-chunk codec
with cosmetic re-framing; and its decoder is not present in any offline file. A standalone ST1
decoder cannot be written offline. **Unblock = the user's unlock/coins save**: load a 3/5/6/7 game so
the gated overlay (engine + ST1 decompressor) becomes resident, then static-disasm/trace it like the
KNPAN codec was, OR identify the gated overlay file on disc.

### TASK 3 — the 3/5/6/7 "shared runtime menu"
Confirmed (again) there is **no KNPAN-style menu blob** for these games anywhere offline: scanning
MG3/5/6/7_1.STB, MG0_C.STB and MG__S.STB for the exact shared-menu signature `00 01 11 00 ff ff 90 00`
(and a 5-item variant) yields **zero** hits. These four games render their Start/Rank/Quit menu from
the **gated engine overlay** at runtime — same blocker as TASK 1. Resolvable only with the unlock save.

## SWEEP session 4 (2026-06-29) — games 3/5/6/7 SOLVED OFFLINE (resident codec; ST1 verdict overturned)

**The session-3 "ST1 impossible offline / gated" verdict was wrong.** It searched only
`MG3/5/6/7_1.STB` (these are ST1 *sprite-atlas data* archives — not where the title/menu
graphics live) and missed each game's **engine-overlay companion file**, which IS on disc and
IS KNPAN-style. Corrected game → engine → asset map (from `src/iso.py list` + the engine header
refs):

| game | E814 name | engine overlay (base) | **title/menu asset (KNPAN-style)** | ST1 atlas (red herring) |
|---|---|---|---|---|
| 3 | Feena's Panties | FIPAN.BIN (0x0602c018) | **FI_DT.DAT** | MG4_1.STB |
| 5 | Hot-Blooded Showdown! | BY100.BIN (0x0602c018) | **BY100.DAT** | MG6_1.STB |
| 7 | Baal's Revenge | BARLG.BIN (0x0602c018) | **BARLG.DAT** | MG1_1.STB |
| 6 | Big-Eater Grandia Cup | HAYAG.BIN (0x0602c7c0) | **HYABG.BIN** (single-chunk framing) | MG0_C.STB |

### TASK 1 verdict — ALL FOUR games use the SAME resident Huffman+delta codec (NOT a separate ST1 codec, NOT gated)
`FI_DT.DAT`, `BY100.DAT`, `BARLG.DAT` are **KNPAN-style offset-table archives of
(512B BGR555 palette, inline-chunk ST1 stream)** — they decode byte-coherently with the
**existing** `mg_tree.decode_blob` + `mg_codec` (resident codec, tree routines 0x0601401A/
0x060144EE from save-5 HWRAM). Proven by rendering decoded slots offline (`work/mgame/slotdec/`):
- **Game 3 (FI_DT.DAT)**: slot1 = **フィーナぱんつ / "THE PANTSU OF FIENA"** title logo (296×88 8bpp),
  slot3 = the **byte-identical shared 3-item menu** (はじめ/じゅんい/やめる), slot5 = green "Ranking"
  screen (352×224), slot7 = 512×224 playfield. All crisp.
- **Game 5 (BY100.DAT)**: slot1 = **男の熱血 / 100億番勝負** flaming gold logo (288×120), slot3 =
  byte-identical shared menu, plus playfields. All crisp.
- **Game 7 (BARLG.DAT)**: slot1 = **バールノギャクシュウ / "RETURN OF BARL"** star-bordered title
  (352×224, white-on-black, 2-color); no standard 12288B 3-item menu blob (menu likely engine-drawn).
- **Game 6 (HYABG.BIN, base 0x0602c7c0)**: **single-chunk framing** — slots have NO leading BE16
  chunk count; the treedef sits at offset 0 (call `mg_tree.build_chunk(blob, 0)` then decode).
  slot0 = 512×512 flame texture, slot2 = 512×512 banquet-arena bg, both EOS-terminated, decoded
  perfectly with the SAME resident codec. HYABG holds the gameplay backgrounds; the game-6 TITLE
  LOGO is not in HYABG (likely MG0_C.STB / engine) and still needs layout mapping — but that is a
  geometry task, **NOT** a codec barrier.

Five evidence points that previously "proved" ST1 was a different/gated format were all looking at
the wrong file (`MG[n]_1.STB`). The real assets need no unlock save: a save-5 game-room HWRAM dump
(`--dump-wram`, the shared low resident codec) is sufficient, exactly as for deck-swab.

### Menus (offline-validated)
| game | menu | status |
|---|---|---|
| 3 (FI_DT.DAT s3 @0x34d8, end 0x3c44) | shared 3-item, **byte-identical to KNPAN** (1900B) | **START/RANK/QUIT authored, decode-roundtrip EXACT** |
| 5 (BY100.DAT s3 @0x4f68, end 0x56d4) | shared 3-item, **byte-identical to KNPAN** (1900B) | **START/RANK/QUIT authored, decode-roundtrip EXACT** |
| 7 (BARLG.DAT) | no standard 3-item blob found (s3=2560B small sprite) | engine-drawn? — not authored |
| 6 (HYABG) | not located (not in HYABG bg/flames slots) | with title logo, needs more mapping |

### Logos (authored + offline-validated)
| game | slot | geometry | core/outline | English | validation |
|---|---|---|---|---|---|
| 3 | FI_DT.DAT s1 @0x264 end 0x32d8 | 296×88 8bpp, pal@0x64 | 205/171 | **FEENA'S / PANTIES** | slot-fit OK, decoded-render legible |
| 5 | BY100.DAT s1 @0x288 end 0x4d68 | 288×120 8bpp, pal@0x88 | 173/14 | **HOT-BLOODED / SHOWDOWN!** | slot-fit OK, decoded-render legible |
| 7 | BARLG.DAT s1 @0x234 end 0x2a64 | 352×224 8bpp, pal@0x34 | 255/0 | **BAAL'S REVENGE** (replaces katakana line; keeps "RETURN OF BARL" + star border) | size-preserving (scale-1 to fit the sparse 2-color budget); decoded-render legible |

Logo geometry recovered with new `tools/mg_width.py` (max transparency-mask vertical continuity):
FI_DT s1 → W=296 (0.96), BY100 s1 → W=288 (0.98), BARLG s1 → W=352 (0.97). Engine favours 288/296/352-wide title sprites.

### Disc built (validation-only; NOTHING unlock/coin baked in; engine/launch bytecode untouched)
- `output/mg_05` — `FI_DT.DAT` (game-3 logo+menu), `BY100.DAT` (game-5 logo+menu), `BARLG.DAT`
  (game-7 logo) injected **in place, size-preserving** (`tools/mg_inject.py`). On-disc re-extract
  is **byte-identical** to the authored files and decodes to the authored English. Gated games →
  offline-validated only (in-game screenshot still pending a user unlock/coins save).

### New tooling
- `tools/mg_width.py` — linear-bitmap width finder (transparency-mask vertical continuity).
- `tools/mg_inject.py` — size-preserving in-place file injector for the MODE1/2352 track.
- Game-6 single-chunk decode: `mg_tree.build_chunk(blob, 0)` + `mg_codec.decode_end(...)` (no BE16 count).

## SWEEP session 5 (2026-06-29) — the 3 remaining offline items closed: game-7 menu SOLVED, game-6 title+menu = ST1 second-codec (precise blocker)

Offline pipeline re-derived from scratch (gitignored `work/` doesn't persist): rebuilt the harness,
dumped a fresh save-5 HWRAM image (`tools/ymir-harness/build/jinloop-harness --dump-wram` →
`work/mgame/hwram.bin`), and re-validated the resident codec — `mg_tree.decode_blob` reproduces
KNPAN slot-1's 6 chunks byte-exact (modes 1/1/0/0/0, roots 0xfb0/0xf98/0x808…). So decode/encode is
fully reproducible with NO emulator runtime, exactly as before.

### TASK 3 — Game-7 (Baal) MENU = **SOLVED, already English, no authoring needed**
`BARLG.DAT` is a resident-codec KNPAN-style archive. Enumerated + decoded **every** slot (the
session-4 "no menu blob found" was just an unrendered small slot):

| slot | size (cmp→dec) | geometry | what |
|---|---|---|---|
| 1 | 10288→78848 | 352×224 8bpp | **title** (バールノギャクシュウ / RETURN OF BARL, star border) — EN `BAAL'S REVENGE` already authored s4 |
| 3 | 408→2560 | **80×32** 8bpp | **MENU** = `START` / `END` — **ALREADY ENGLISH** (2-item, two stacked rows) ✓ |
| 5 | 10100→78848 | 352×224 8bpp | "Ranking" screen — **already English** |
| 7 | 94368→… | 512×224-ish | playfield bg (8 chunks) |
| 9 | 1020→3840 | **32×120** 8bpp | digit font 0-9 (score display) — no text |

So game 7 has **no Japanese menu text** to translate (renders `docs/mgame-gfx/game7-menu-start-end-english.png`,
`game7-ranking-english.png`). Its menu is a 2-item `START/END` (not the 3-item START/RANK/QUIT) and
ships as-is. **Item resolved: nothing to author.**

### TASKS 1+2 — Game-6 (Big-Eater Grandia Cup) TITLE + MENU = **located, but ST1-compressed (a SECOND codec) → precise blocker**
Game 6 is the **one exception** to session-4's "all four STB games use the resident codec" claim.
Mapping (from `iso.py list` + HAYAG's embedded filename table @0x23740 + pointer table @0x0):
- Game-6 has only two dedicated files: **`HAYAG.BIN`** (engine, base **0x0602c7c0**, 149904 B —
  unusually large) and **`HYABG.BIN`** (231852 B). HAYAG's filename table loads: `MG0_C.STB`,
  `HYABG.BIN`, `P_DAT.BIN`, `M_DAT.BIN`, `PARTY.BIN`, `MGDAT.BIN`, `FIELD.BIN`, `SYS_F.STB` (+ per-player
  `P1..P8_{DEF,A_Q,A_H,WIN,ITM,MG0,MG1,MG2}.BIN` sprite lists). Debug strings include `ST CH0/CH1/CH2 = %d`.
- **`HYABG.BIN` = gameplay bg only** (resident codec, fully decoded): 6 slots — s0 = 512×512 **flame**
  texture, s2 = 512×512 **banquet-arena bg** (`docs/mgame-gfx/game6-hyabg-{flame,banquet-bg}.png`),
  s1/s3 = palettes, s4/s5 = nested offset-table archives of **raw** sprite/animation tiles (8192-B
  blocks, head `0180…`, not chunk-streams). **No title / menu / ranking / digit slots anywhere in HYABG.**
- The title + menu therefore live in **`MG0_C.STB`** (referenced ONLY by HAYAG — game-6-exclusive,
  *not* a shared minigame file; `MG0_C` count: HAYAG=1, MGAME/KNPAN/FIPAN/BY100/BARLG/MGFRG=0). It is
  an `ST1\0`-magic archive (10 sub-blobs, dsts 0xc000/0xe000/0x5c000, word3 = data size).
- **The ST1 resources are NOT the resident Huffman+delta codec.** Exhaustively tested every framing —
  single-chunk at payload start, at `payload+w2`, at `payload+w3`, at blob start; for all 10 slots.
  Every attempt either returns an **invalid filter mode** (5/7/11/15 — the delta op-table has only
  0/1/2/3) or "decodes" by running **far past the slot boundary** into adjacent data (e.g. slot1: 1668-B
  payload, decode consumes 7864 B) and renders to pure noise. So the resident codec genuinely cannot
  read MG0_C — it is the Game-Arts **ST1 (FRONTIER-library) format**, a distinct codec. (Session-3's
  ST1 verdict was right for game 6; session-4 only overturned it for games 3/5/7, whose UI is in
  resident-codec `.DAT`s — game 6 has no such `.DAT`.)
- The ST1 decoder is **not** present as offline code: `ST1\0` magic appears in **zero** bytes of
  HAYAG/MGAME/KNPAN/FIPAN/BY100/BARLG/MGFRG, and HAYAG contains no reference to the resident Huffman
  codec (0x06013F90/0x06015DF0). HAYAG instead calls resident jump-table routines (clusters
  ~0x06010000 / 0x06017000 / 0x06022400, all populated in the save-5 dump) + big work buffers
  (0x0607c000, 0x060a0000). So the ST1 decompressor is a **resident MGAME/system routine** that IS in
  our save-5 `hwram.bin` (→ reversible offline in principle, the same `sh2dis`+`sh2emu` technique that
  cracked the Huffman codec), but its entry point was not statically located this session.

**Precise blocker (game-6 title + menu):** the art is in `MG0_C.STB` in the **ST1 second codec**. It is
NOT decodable with the existing resident-Huffman tooling. Unblocking is a **scoped offline RE follow-up**
— statically locate the resident ST1 decompressor (it's in `work/mgame/hwram.bin`; fastest is to
breakpoint MG0_C's load+decompress with the game-6 overlay resident, which needs the unlock save to
reach the game-6 terminal) and emulate it via `sh2emu`, then map geometry + author like the other logos.
It is **not** blocked by our resident-codec tooling being wrong; it's a genuinely different codec.

### Final per-game OFFLINE status (all 8 minigames)
| # | game (E814 name) | title logo | menu | codec | offline status |
|---|---|---|---|---|---|
| 0 | Deck-Swabbing REMIX | KNPAN.DAT s1 | KNPAN.DAT s3 (3-item) | resident | **DONE + IN-GAME PROVEN** |
| 1 | Leen Hates Frogs! | RFROG.DAT s35 (EN authored) | original art already EN (START/RANKING/EXIT) | resident | logo authored; menu no-op |
| 2 | Sue! Gantz's Bride Plot | MGSUE.BIN s1 (EN authored) | MGSUE.BIN s3 = KNPAN-identical (EN) | resident | DONE offline |
| 3 | Feena's Panties | FI_DT.DAT s1 (EN authored) | FI_DT.DAT s3 = KNPAN-identical (EN) | resident | DONE offline |
| 4 | Bonk-a-Tray! | OBONG.DAT s1 (EN authored) | OBONG.DAT s3 (5-item, EN authored) | resident | DONE offline |
| 5 | Hot-Blooded Showdown! | BY100.DAT s1 (EN authored) | BY100.DAT s3 = KNPAN-identical (EN) | resident | DONE offline |
| 6 | **Big-Eater Grandia Cup** | **MG0_C.STB (ST1)** | **MG0_C.STB (ST1)** | **ST1 second codec** | **BLOCKED — ST1 not reversed** |
| 7 | Baal's Revenge | BARLG.DAT s1 (EN authored) | BARLG.DAT s3 = `START/END` **already EN** | resident | **DONE offline (menu no-op)** |

So **7 of 8 games are fully resolved offline**; the only remaining offline gap is **game-6's ST1 codec**
(a separate second-codec RE task). In-game *screenshot* proof of games 1-7 still needs the user's
unlock/coins save (separate from the ST1 work). No new disc was built this session (game-7 menu needs no
change; game-6 cannot be authored until ST1 is reversed) — `output/mg_05` remains the latest.

## SWEEP session 6 (2026-06-29) — ST1 codec RE: premise corrected (decoder is in HAYAG, NOT resident); precise offline stopping point

Goal this session: reverse the ST1 codec by EXECUTING the resident decompressor (the technique that
cracked the Huffman tree-builder), per the handoff's premise that "the ST1 decoder is a RESIDENT routine
present in the save-5 HWRAM dump … reachable from HAYAG's jump-tables 0x06010000/0x06017000/0x06022400."

**That premise is wrong, and this is the crux finding.** The codec is NOT reversed, but the blocker is now
*precisely* located, and the right next step is different from what was planned.

### Reproducible pipeline (re-derived; `work/` is gitignored)
- Built harness (`tools/ymir-harness/build.sh`), dumped fresh save-5 HWRAM:
  `jinloop-harness --bios <JAP BIOS> --disc <DM cue> --state <D493EA66 slot 5> --dump-wram work/mgame/wram5`
  → `wram-hi.bin` copied to `work/mgame/hwram.bin`. Save registered as `gameroom-save5-wram`.
- Extracted assets: `src/iso.py extract … MG0_C.STB` (83712 B) and `HAYAG.BIN` (/FIELD, 149904 B, base 0x0602c7c0).

### ST1 archive/header format — fully characterized
`MG0_C.STB` = top **u32 BE offset table** (10 entries → each ST1 sub-blob, terminated `ffffffff`) then the blobs.
Each blob: `ST1\0` magic + fixed header (w1.lo = header len **0x30** for blobs 0-7, **0x38** for blobs 8-9):

| blob | hdrlen | payload | item(w4) | w2 | w3 | dst(w10) | entropy | likely role |
|---|---|---|---|---|---|---|---|---|
| 0 | 0x30 | 4 | 1 | 0 | 0x1 | 0xc000 | 0 (all-zero) | sentinel/blank |
| 1,2 | 0x30 | 1668 | 35 | 0x344 | 0x683 | 0x5c000 | 7.08 | menu text? (two-section, w2 split) |
| 3 | 0x30 | 17280 | 91 | 0 | 0x437f | 0xe000 | 6.52 | title logo? |
| 4 | 0x30 | 3944 | 20 | 0 | 0xf67 | 0xe000 | 6.93 | |
| 5 | 0x30 | 2908 | 16 | 0 | 0xb5b | 0xe000 | 6.19 | |
| 6 | 0x30 | 22464 | 121 | 0 | 0x57bf | 0xc000 | 7.23 | largest |
| 7 | 0x30 | 4424 | 23 | 0 | 0x1147 | 0xe000 | 6.49 | |
| 8 | 0x38 | 13822 | 72 | 0x97d | 0x1afe | 0xc000 | 7.82 | |
| 9 | 0x38 | 14522 | 201 | 0x2918 | 0x38b9 | 0xe000 | 7.05 | |

Field semantics confirmed: w1.lo=hdrlen; w4=item count; **w3 = payload_size-1** for single-section blobs
(w2=0); for w2≠0 blobs (1,2,8,9) w2 = an offset that splits the payload into TWO sub-streams; w5.lo =
file offset of the payload (header end), w5.hi = 0x0810/0x0820/0x0830/0x0831 (format/flags); w10 = dst
(VDP2/VDP1 VRAM offset). w7 (e.g. 0x701f3c12, 0x001f3c1f) = clip/dims.

### It is genuinely a compressed second codec (two independent confirmations)
1. **Not raw pixels.** Rendered every payload as raw 4/8bpp at many widths → horizontal-streak NOISE
   (`work/mgame/rawtest/`). (Important: session-3 mistook a real logo for noise via wrong width; this
   time it's actually noise — true compression.) Entropy 6.5–7.8 b/byte corroborates.
2. **Resident Huffman codec cannot decode it (precisely why).** Running the engine tree-builder
   `mg_tree.build_chunk(payload, 0)` on a payload start now returns a *plausible-looking* mode=0,
   root≈0xFF0, consuming a 257-byte "length table" — but `mg_codec.decode_end` then **never reaches the
   EOS leaf (0x800)** and runs off the end (had to SIGALRM-kill). So the 257-byte prefix is NOT a real
   tree-def and the bitstream is NOT this Huffman format. (Off-by-2/4 framings give invalid filter modes
   5/7/15, matching the session-5 report.) ST1 ≠ resident KNPAN codec — confirmed a third time.

### CRUX CORRECTION — the ST1 decoder is in HAYAG.BIN (coin-gated game-6 overlay), NOT resident
The handoff said the decoder is resident in the save-5 dump. **It is not.** Verified directly:
`hwram.bin` at 0x0602c7c0 (HAYAG's load base) matches HAYAG.BIN's first 4 KB in only **103/4096 bytes** —
i.e. in save 5 (deck-swab loaded) the overlay slot 0x0602c018+ holds the **deck-swab/KNPAN** engine, and
HAYAG is absent. MG0_C/ST1 is **game-6-EXCLUSIVE** (no other engine references MG0_C or `ST1\0`), so the
decompressor ships inside HAYAG.BIN and is only resident once game 6 launches (which is coin-gated).
**Consequence:** the planned "disassemble the save-5 resident jump-table routines to find the ST1 decoder"
cannot work — those routines aren't the ST1 decoder. What the jump tables 0x06010000/0x06017000/0x06022400
actually are (disassembled this session): the **resident per-frame ST sprite-DISPLAY library** —
0x06017000 (35-entry vtable) = archive relocate (slot0 0x06017980), sprite-record accessors (0x06017b9c),
VDP1 command-list/coordinate transforms (0x06018928, 0x06018da4 reads a 0x30 header but only for sprite
clip/position geometry). None decompress ST1.

### What was ruled out inside HAYAG.BIN (so the next pass doesn't re-walk it)
HAYAG IS available offline (extracted), so ST1 is reversible offline *in principle* — the only gap is
statically pinning the decode entry in a 150 KB sprite engine without a live anchor. Disassembled and
eliminated: the graphics/transfer module 0x0604bxxx–0x0604cxxx (byte→16bit palette-word expander
0x0604c222; item/quadtree iterators 0x0604bdc0/0x0604be74; VDP2-VRAM transfer 0x0604c1da → dst 0x25e08000
from work buffer **0x06068564**); the RNG/math block 0x0604cf88+ (LCG constant **0x41c64e6d** — this is
what inflated a naive "rotcl-heavy = bit-decoder" scan, a red herring); VDP2 register/plane setup
0x0602da02 / 0x0602dd00. The many `mov.l @(0x28,Rn)` "header-field" hits were **stack-frame locals**
(16.16 fixed-point sprite-vertex math, `shlr16; exts.w`), not blob-header reads. A refined scan for a
routine reading blob-header +0x10/+0x14/+0x28 from one non-stack register found **zero** — i.e. the
decoder does NOT index the header by struct displacement; it either reads it sequentially (`mov.w @r+`,
like resident 0x06018da4) or the caller extracts fields and passes them as args. The offset-table walk
(read u32 entries until `ffffffff`) was not isolated either.

### Precise stopping point + fastest unblock
The decoder bytes are in `work/mgame/HAYAG.BIN`; the entry was **not** pinned statically this session and
the resident-dump route is a dead end (decoder not resident). Two ways forward, in priority order:
1. **Live anchor (fastest, needs the user's unlock/coins save):** reach the game-6 terminal so HAYAG +
   MG0_C become resident, then breakpoint MG0_C's load buffer with the harness (`--bp`/`--watchr` on the
   loaded MG0_C bytes / on writes to the dst VRAM 0x25c0c000/0x25c0e000), capture the decode routine PC,
   then emulate it with `sh2emu` exactly as the Huffman builder was cracked. This also yields ground-truth
   decoded pixels to validate against.
2. **Pure-static (no save, larger effort):** trace HAYAG's MG0_C dataflow — find the filename-table load
   of `MG0_C.STB` (string @0x0604ff00), follow the loaded-buffer pointer to the offset-table walk, to the
   per-blob 0x30-header read (sequential `mov.w @r+`), to the decompress call that fills a HWRAM staging
   buffer (then transferred to VRAM). The decode loop is the target; emulate it on a blob payload.

Net: **game 6 remains BLOCKED — ST1 not reversed.** The session-5 "ST1 second codec, precise blocker" verdict
stands, with the premise corrected: it is NOT a resident routine, so it can only be reversed offline by
working from HAYAG.BIN directly (entry still to be pinned) — the save-5 HWRAM dump does not contain it.

### Session-6 addendum — emulation-search attempted; decoder is GLOBAL-STATE-driven (entry still must be pinned statically)
Continuing offline (no unlock save): built an sh2emu harness that overlays HAYAG.BIN into the resident
image (`work/mgame/emu_fuzz.py`, `emu_flat.py`), maps the MG0_C blob + a dst buffer + VDP1/VDP2 VRAM with
read/write instrumentation, and tried to INVOKE the decoder directly. Enumerated decoder-shaped functions
(bit-extraction `shll/shlr/rotcl` + incrementing store + backward branch), excluding the already-mapped
math/CD/display regions; top hits were in 0x0604exxx–0x0604fxxx and 0x06045xxx. **Result: none decode.**
Under every register-arg convention (blob/payload/dst orderings, dst=VRAM) and even with a flat fully-mapped
address space, the candidates either KeyError on an unmapped global, spin in a loop reading zeroed globals,
or RTS immediately on a zeroed gate flag — **i.e. they read their source/dest from GLOBAL cursor variables
(like the resident KNPAN codec's 0x06014D9C/0x06014DA0/0x06014D4C), not from R4/R5/R6.** So the decoder
cannot be brute-forced blind: its entry must first be located statically to learn which globals hold the
src cursor / dst / mode, after which it can be emulated by SEEDING those globals (exactly how
`tools/mg_tree.py` drives the resident codec via `VAR_CURSOR`). Also disasm-confirmed NOT the codec this
pass: 0x0604c88c = IEEE-754 software-float normalize/round (the whole 0x0604bxxx–0x0604cxxx block is the
float/RNG math lib for the rotating banquet table); 0x0602exxx = CD file-sector streaming (the `ST CH0/1/2`
debug counters = stream channels, not "sprite table"). The pin-the-entry + seed-globals step is what the
live unlock-save breakpoint (capturing the decode PC and its global setup in one shot) short-circuits.

## SWEEP session 7 (2026-06-30) — unlock save in hand: games 3 & 4 PROVEN IN-GAME (English); combined disc; game-6 ST1 still nav-blocked

The user supplied an **all-unlocked savestate** (`gameroom-all-unlocked`, disc D493EA66): every
casino/arcade game unlocked (flags 0x723–0x72a), player in the Game Room **facing Bonk-a-Tray (game 4)**,
the play menu (もどる / ゲームを始める / ゲームの説明を見る) opens from a clean reload. This lifts the
**coin/unlock GATE**. It does **NOT** remove the **headless-navigation wall**, which is the real blocker.

### Navigation reality (mapped this session) — only games 3 & 4 are reachable headless
- New driver **`tools/mg_drive.py`** (boots a registered save vs a patched disc, runs a compact
  `frames:buttons` plan with **diagonal** combos `Up+Left` etc., PNG/bp/dump passthrough).
- The room is **isometric**: clean motion is along the screen **diagonals** (Up+Left/Up+Right/…), and
  movement is **slow** (~0.1 world-unit/frame horizontally; Right-40-frames ≈ +4 units). The player sits
  in a **central pen ringed by inward-facing cabinets**; `Down` walks toward the exit
  (「アレント博物館・ホールへ」). The cabinet name shows in a 『…』 box on C; the play menu follows.
- **Reachable interactions = exactly two**: **game 3 Feena (`フィーナのぱんつ`, walk `Up`)** and
  **game 4 Bonk-a-Tray (`おぼんでゴン`, start-facing)**. ~55 distinct attempts (cardinal/diagonal,
  long/short holds, wall-climb, route-around, coordinate-teleport) **all** resolved to 3/4 or to *no
  cabinet*; the **green turtle follower intercepts C** at every other spot. The breadcrumb-trail head
  `LWRAM 0x0606d700` and the HWRAM coordinate copies (`0x06071dc8/…`) are **non-authoritative** — writing
  them does not teleport the sprite (engine re-derives position), so deterministic teleport-nav is out.
- Net: the other 6 cabinets (0 deck-swab PC at back-centre; 1,2,5,7 around the ring; **6 Big-Eater**) were
  **not reachable** with the harness's blind input. Fastest unblock = **per-cabinet positioned savestates**
  (one facing each cabinet, like save-5 faces deck-swab), which only the user can capture.

### NEW: games 3 & 4 PROVEN IN-GAME in English (were "offline-only / gated")
Authored size-preserving English assets with the existing tools (resident codec), injected in place, and
launched from the unlock save against the patched disc — **English renders from the real on-disc decode**:
- **Game 3 — `FEENA'S / PANTIES` + `START / RANK / QUIT`** (`FI_DT.DAT` s1 logo @0x264, s3 menu @0x34d8):
  `docs/mgame-gfx/game3-feena-english-ingame.png`.
- **Game 4 — `BONK-A / TRAY!` + `START / RANK / QUIT`** (`OBONG.DAT` s1 logo @0x23c, s3 5-item menu @0x41c0):
  `docs/mgame-gfx/game4-bonk-english-ingame.png`.
These are the **first** non-deck-swab in-game English proofs (deck-swab/game 0 was already shipped).

### Combined English disc — `output/mg_06` (validation-only; nothing unlock/coin baked in)
One disc with **6 of 8** games' English assets injected **in place, size-preserving**, each re-extracted
from the built disc and **decode-validated byte-identical to the authored file**:
`FI_DT.DAT`(3), `OBONG.DAT`(4), `RFROG.DAT`(1), `MGSUE.BIN`(2), `BY100.DAT`(5), `BARLG.DAT`(7).
(Game 0 deck-swab = separately shipped `KNPAN.DAT`; **game 6 = ST1, not authorable until reversed**.)
Authoring args = the session-3/4 per-game table; menus 1 & 7 are already-English no-ops.

### Game 6 (Big-Eater Grandia Cup) — ST1 codec STILL BLOCKED, now for a concrete reason
The plan was a **live capture**: reach the Big-Eater cabinet so HAYAG+MG0_C go resident, breakpoint the
MG0_C decode, capture PC + global cursors, emulate via `sh2emu`. **That requires launching game 6, which
requires reaching its cabinet — and headless navigation cannot (see above).** The unlock save removed the
gate but not the nav wall, so the live capture could not be taken. The codec is unchanged from session 6:
ST1 decoder lives in `HAYAG.BIN` (game-6-exclusive overlay), is **global-state-driven** (can't be invoked
blind offline), entry not statically pinned. **Remaining paths:** (a) a user savestate positioned facing
the Big-Eater cabinet (or already inside game 6) → then the documented live capture works; or (b) finish
the pure-static HAYAG RE (pin the MG0_C decode entry + its cursor globals), larger effort.

### Final per-game status (after session 7)
| # | game | offline asset | in-game English proof |
|---|---|---|---|
| 0 | Deck-Swabbing REMIX | DONE (KNPAN) | **PROVEN** (prior, save-5) |
| 1 | Leen Hates Frogs! | DONE (RFROG; menu already EN) | not reached (nav) |
| 2 | Sue! Gantz's Bride Plot | DONE (MGSUE) | not reached (nav) |
| 3 | Feena's Panties | DONE (FI_DT) | **PROVEN this session** |
| 4 | Bonk-a-Tray! | DONE (OBONG) | **PROVEN this session** |
| 5 | Hot-Blooded Showdown! | DONE (BY100) | not reached (nav) |
| 6 | **Big-Eater Grandia Cup** | **BLOCKED (ST1 not reversed)** | n/a |
| 7 | Baal's Revenge | DONE (BARLG; menu already EN) | not reached (nav) |

So **7 of 8 games are English-authored + on-disc validated; 3 of 8 are now proven in-game**
(0, 3, 4). The lone hard gap is **game-6 ST1**, blocked by headless navigation, not by tooling.

## SWEEP session 8 — status: game-6 + non-(0,3,4) in-game proof = NEEDS VERIFICATION

Investigated why the committed `gameroom-all-unlocked` save played as locked. Harness dump: it had
only flags **0x720–0x724** set (games 0–4); games 5/6/7 were still locked (base 0x06021dc0, game N =
flag 0x720+N). Poked byte 0x06021ea4=0xFF (all 8), confirmed the flags PERSIST through the update loop,
emitted `saves/gameroom-fullunlock.savestate.gz`. **But the user's in-game walk-test still could not
play the newly-flagged cabinets** → the 0x72x flag bank is necessary-but-NOT-sufficient; the cabinet
gate has a second component (most likely the Game Coin inventory items, IDs 37–44 — see memory
`casino-unlock-is-game-coins`). Do NOT re-attempt flag-only unlock.

**MARKED NEEDS-VERIFICATION (stopping here):** game-6 ST1 codec (needs a live capture, which needs
game 6 actually launching) and the in-game screenshot proof of games 1,2,5,7 (authored + on-disc
validated already). Both wait on a GENUINELY playable save — either a real playthrough save with the
games unlocked (Game Coins obtained), or a save positioned+able-to-launch each cabinet. Everything
else (7/8 authored + on-disc validated; 3/8 proven in-game) is DONE.

## SWEEP session 9 (2026-07-01/02, lane pD) — NAV WALL BYPASSED (launch-id swap); games 1,2,5,7 proven; GAME-6 TITLE CODEC CRACKED + AUTHORED + PROVEN → **8/8 COMPLETE**

### Navigation wall solved without navigation: the LAUNCH-ID SWAP
The cabinet interaction writes the selected game's **launch id u16 at LWRAM `0x002817A2`**
(1-based: game N → id N+1). From `gameroom-all-unlocked` (facing Bonk-a-Tray), inject the target
id (`--inject work/pD_nav/idK.bin --inject-addr 0x002817A2`, harness `--inject-scn`) and run the
Bonk-a-Tray open plan `20:;8:C;70:;8:Down;16:;8:C;700:` — the engine loads game K−1 instead.
Every cabinet is reachable headlessly; no per-cabinet savestates needed. Games **1, 2, 5, 7**
proven in-game this way on the `output/pD_01` combined disc
(`docs/mgame-gfx/game{1-frogs,2-sue,5-hotblooded,7-baal}-english-ingame.png`), games 0/3/4
re-proven (`*-pD01.png`).

### Game-6 title codec = the resident FIELD-SPRITE codec at 0x0601A716 (a THIRD codec) — CRACKED
Sessions 5–8 assumed the game-6 title lives ST1-compressed in `MG0_C.STB`. **Wrong on both counts:**
- A bp on the resident KNPAN caller `0x06013F90` during a game-6 launch fires **zero** times, and
  write-watchpoints on the title's VDP1 pixels (`0x25C50800`) trace to **resident** code
  `0x0601A8E4` reading LWRAM — the title is decoded by the resident routine at **`0x0601A716`**
  (args R4=dst VDP1 addr, R5=src LWRAM; the same routine the FIELD engine calls per-frame for NPC
  sprites, PR `0x0605186C`). Not ST1, not KNPAN: a third, previously unmapped codec.
- The compressed title is in **`/FIELD/HYABG.BIN` slot 4** (slot hdr @`0x29C3C`: nested table +
  BGR555 palette; compressed stream @file `0x29E9C`, slot budget `0x25FC` B), loaded wholesale at
  LWRAM `0x2C0000`. Sessions' "HYABG has no title slot / s4 = raw tiles" was a misread.
  Decoded output = the full **256×104 8bpp** title sprite (kanji + subtitle), VDP1 cmd @`0x20`
  (CMDSRCA 0xA000 → VRAM `0x50000`, pmod CM=4 8bpp bank, colr bank 0).

**Format** (lifted from SH-2 disasm; oracle = emulating the real decoder via `tools/sh2emu.py`
on the mid-launch memory dump `work/pD_nav/g6re/dump471/`, byte-exact vs real VRAM):
`[u16BE hdr][stream A (L bytes)][9B code-length nibbles][stream B bitstream]` — hdr bits15-14 =
per-nibble delta filter (mov/xor/sub/nop), bit13 = start literal(1)/run(0), bits12-0 = L.
Output = 4-bit nibbles packed 2/pixel-byte. Stream B = MSB-first Huffman (17 syms, max len 8,
256-entry LUT, canonical fill by len desc/index asc, Kraft must equal 256 exactly): syms 0-15 =
literal nibble (through the filter), 16 = escape → one zero-run event from stream A (nibble
groups: 0-12 = prev±6 delta, 13+n = prev±7..14, 14+byte = absolute 8-bit (byte 0 = EOS),
15+4 nibbles = absolute 16-bit). Runs count zero NIBBLES.

**Encoder: `tools/mg_field_codec.py`** — fixed complete code (nibble n → 5 bits `0nnnn`,
escape → `1`), absolute runs only, mode 0. Round-trip on the original JP logo through the
emulated REAL decoder = **byte-exact**. English logo (`BIG-EATER` / `~GRANDIA CUP~`, gold 0x39/
highlight 0x27 + white 0x01 on black 0xFF outline, mg_text house font + new `~` glyph) encodes to
7325 B < 9724 B slot; spliced size-preserving into HYABG.BIN, disc `output/pD_02` (= pD_01 + HYABG).

### PROOF (8/8)
- `docs/mgame-gfx/game6-bigeater-english-ingame.png` — English title over the flame background,
  START/EXIT menu (menu art was already English).
- START proceeds to the (already-English) CHARACTER SELECT — gameplay path intact
  (`docs/mgame-gfx/game6-charselect-after-english-title.png`); game 4 re-verified clean on pD_02.
- Savestates: `mgame-game6-title` (JP baseline), `mgame-game6-title-english` (pD_02 proof state).

**Final status: all 8 minigame title screens are English-authored AND in-game proven.**
Latest combined disc: `output/pD_02` (games 0-5,7 via mg_splice assets + game 6 via HYABG).
