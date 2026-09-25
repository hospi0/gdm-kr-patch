# Theater closed-captioning — findings & running log

Lane coordination doc (see `plan.md`). Status: **investigation done, implementation not started.**

## What the theater actually is (verified live, 2026-06-28)

Captured headlessly from the user's savestates (folder
`…/Ymir/savestates/<minigame-disc-hash>/`) on the vanilla JP disc. Evidence frames in
`docs/theater/frames/`.

The theater is the **E804.MDT** room ("Alent Museum · Theater", attendant = **Pakon**). It is a
**ticket-gated Japanese voice-DRAMA exhibit**, NOT a video venue and **NOT a Grandia-1 FMV throwback**:

- **`05-entrance.png`** — approach from the Cloud-Bridge area (SS-1 / state 6).
- **`03-clip-menu.png`** — the in-room menu (SS-2 / state 7), a standard **dialogue/MDT box**
  (blue title bar + brown box), *not* a system `.BIN` menu. Options (E804 piece `600a`):
  - `もどる` = **Back**
  - `[ドラマ]を 聞く` = **Listen to [Drama]** (the `[ドラマ]` slot shows the loaded show's title)
  - `シアターの説明を 見る` = **View theater description**
- **`04-ticket-desc.png`** — the description: *"To listen to the drama you need a TICKET. Tickets
  are sold at Gid's item shop."* (`ドラマを聞くには チケットが必要です / チケットは ギドのアイテムショップで 売っています`).
  Line 30-32 of `script/E804/ja.txt`: *"buy the ticket for the show you want performed"* →
  **there are multiple dramas, one per ticket.**
- **`01-curtains.png` → `02-sound-only.png`** — selecting the drama: curtains open onto a black
  screen reading **"SOUND ONLY"** (a built-in English label) while **audio-only** content plays
  (CD-streamed ADX — the harness CDBlock log shows FAD-range streaming, "Playback ended" loops).
  There is **no video** — the drama is spoken Japanese over a black screen.

## Consequence for captioning
- **Source CANNOT be ported from Grandia-1** (this is DM-original audio drama, not a game FMV). And
  neither agent can *hear* audio (the harness only captures PNG frames). So the **drama transcript is
  an external dependency** — see "Open dependencies".
- **There is no video to burn subtitles into.** Captioning = drawing **timed English subtitle text
  over the black "SOUND ONLY" screen**, synced to the spoken audio.

## What's already done vs. new
- **E804 room TEXT (attendant Pakon dialogue, the menu, the ticket description, banners)** is
  ordinary dialogue and was **already translated in Step 2** (`script/E804_en.py`). It is NOT new
  work — just **verify it renders** and defer any box-fit to after the font fix (it goes through the
  gated dialogue/box renderer). Pieces: `5006` (greeting), `5007` (Pakon comedy, 26 runs), `600a`
  (menu), `c000`/`d000`/`e001` (banners).
- **NEW work = caption the audio drama(s):** locate the drama audio, obtain a JP transcript,
  translate (dictionary-guided), time it, and display synced subtitles over the SOUND-ONLY screen.

## Audio capture — SOLVED (new audio harness, validated 2026-06-28)
`tools/ymir-audio-harness/` (separate from the dialogue `jinloop-harness`; see its README) captures
emulator audio to a WAV via the SCSP sample callback. Validated on SS-3: 25 s, 44100 Hz stereo, clear
speech envelope, plays back via `afplay`. So we **can** produce a recording of each drama for
transcription even though no transcript exists online. Recipe:
```
tools/ymir-audio-harness/build/audio-harness --bios "$GDM_BIOS" \
  --disc input/Grandia*Digital*10M).cue \
  --state .../<minigame-disc-hash>/8.savestate \
  --wav work/theater/drama_ss8.wav --frames 1500     # ~25s
```

## Open dependencies / questions for the user
1. **JP transcript of each drama.** No online transcript is expected to exist (user's read). Path:
   (a) capture each drama's audio with the **audio harness** above (one WAV per ticket/show);
   (b) the **user transcribes** the spoken JP from the WAV (or has it transcribed) — the agent cannot
   hear audio;
   (c) the agent then translates (dictionary-guided) + times the lines.
2. **How many dramas / ticket items, and their titles?** Cross-ref the "ticket" items in the
   decoded item list (`WDATA` / menus team) and the `[ドラマ]` title slot in piece `600a`.
3. **Display mechanism** (agent decides by feasibility): timed in-engine text over the black screen
   (extend the playback piece with print+wait ops) is the likely path since there's no video to
   burn into. This touches the dialogue/box renderer → coordinate with the SCNRL/font agent; a full
   black screen gives generous room so it is only lightly gated.

## Savestates (provided)
`6`=outside door, `7`=clip menu (press C to open), `8`=mid-drama "SOUND ONLY", `9`=about to exit.
All in `…/savestates/<minigame-disc-hash>/`. Harness mounts the disc separately, so they
work on vanilla (discovery) and on a built disc (verification).

## Harness recipe used (reuse this)
```
tools/ymir-harness/build/jinloop-harness \
  --bios "$GDM_BIOS" --disc input/Grandia*Digital*10M).cue \
  --state .../<minigame-disc-hash>/8.savestate \
  --out report.json --script idle.json --png-dir frames/ --png-every 60
# idle.json = [{"frames":30,"buttons":""}]*N ; press "C"/"Down"/etc. to navigate.
```

> NOTE: the **audio-harness** also accepts `--png-dir/--png-every` and `--script`, so a single
> audio-harness run captures **both** WAV and filmstrip PNGs. I used it for all visual checks below
> (no need to build the separate `jinloop-harness` for the theater lane). The `jinloop-harness`
> binary is **not built** in the theater worktree; the audio-harness IS (`build/audio-harness`).

---

# Session 2 (2026-06-28, takeover agent) — Phases A, B1, C

## Environment notes (theater worktree)
- `input/` is gitignored and NOT present in the worktree; symlink it to your shared disc dump:
  `ln -s /path/to/gdm/input input` (untracked — never `git add -A`).
- The Java MDT toolchain (`tools/vendor/.../target/classes`) wasn't built here; copy the compiled
  `target/` from the main worktree (gitignored, identical source) so `build_mdt.py` works.
- BIOS: `/path/to/Ymir/build/apps/ymir-sdl3/ymir-sdl3.app/Contents/MacOS/roms/ipl/Sega Saturn BIOS v1.01 (JAP).bin`
- Disc cue: `input/Grandia - Digital Museum (Japan) (Rev A) (10M).cue`

## A1 — Drama audio located: **GM3.STZ** (streaming container)
- FAD `0x1C0BF` (≈ LBA 114729) falls inside **`/FIELD/GM3.STZ`** (LBA 39128‑160312, **248 MB**),
  indexed by **`/FIELD/GM3.IDX`** (4096 B). NOT Track‑2 CDDA, NOT MDAT2.BIN.
- GM3.IDX entries look 4‑byte: `[tag16][offset]` with a monotonically growing offset column. Did not
  fully decode (not required — see A3; the audio is streamed by E804's event code, we don't repack it).
- The data at the FAD offset is high‑entropy (no ADX header / `(c)CRI` there — we sampled mid‑stream).
  We do **not** need to decode/extract the audio: the **audio-harness records it live** for transcription.

## A2 — **5 dramas**, gated by **Ticket 1–5** (item idx 32–36)
- Item list (`docs/menus/item-list-names-review.tsv`): `チケット１…５` = items **32‑36** ("Ticket 1‑5").
- The **8 Films** (`フィルム１…８`, items 10‑17) are a **separate exhibit** (the clip/demo viewer) — NOT
  this lane.
- Drama **titles**: the menu's `[ドラマ]` (piece 600a) is a runtime‑filled slot; on the captured state it
  renders the literal placeholder "[ドラマ]". The per‑ticket titles are not in E804 text (see A3).

## A3 (partial) — display mechanism: the playback logic is in E804 **event bytecode**, not text
- E804.MDT has only **7 text pieces**: 3000 (map‑setup), 5006 (greeting), 5007 (Pakon comedy),
  600a (menu), c000 (location), d000 (door), e001 (save‑location). **There is NO "description" piece
  and NO "playback" piece.**
- Therefore the **ticket description** ("To listen to the drama you need a TICKET…", frame
  `04-ticket-desc.png`) and the whole **drama playback** (curtains → "SOUND ONLY" → stream ADX from
  GM3.STZ → wait‑loop) are driven by **E804's event script (bytecode)**, which the text extraction
  doesn't expose. **"SOUND ONLY" is a built‑in label.**
- **Consequence:** in‑engine captioning needs reverse‑engineering E804's event bytecode to find the
  playback wait‑loop and interleave print+wait ops. This RE is the **core open task** and the hard
  part. (Fallback per plan: a dedicated caption overlay driven from the same loop.) **Still open.**

## B1 — Audio capture: **drama #1 recorded from the top; it LOOPS (~99 s period)**
- **Breakthrough:** I can start a drama from the top headlessly from **SS‑2** (7.savestate):
  `C` (open menu) → `Down` (cursor to "[ドラマ]を聞く") → `C` (select). Then a **~10 s CD load**, curtains
  close (luma→0 at t≈16 s), then the **"SOUND ONLY" screen** (luma≈44) and **drama audio start at
  t≈18‑20 s**. (My first attempt failed only because the 4 s tail was too short for the load.)
  - Selecting "Listen" with **no drama loaded** just closes the menu (the loaded drama is set by the
    ticket inserted at the machine). So from these states I can only record the **currently‑loaded
    drama (#1)**; dramas 2‑5 need their tickets (user dependency — see questions).
- **Drama #1 loops:** envelope autocorrelation of a 364 s capture → **r=0.994 at lag 99.0 s**
  (harmonics 49.5 s, 148.5 s). So unique content ≈ **99 s**, then repeats. Each drama is likely
  ~1.5‑2.5 min, not 6 min — transcription is manageable.
- **Clean WAV ready for transcription:** `work/theater/drama1_loop_18-125s.wav`
  (107 s, one full loop from the SOUND‑ONLY start, 44100 Hz stereo; menu/curtain preamble trimmed off).
  Validate/play: `afinfo`/`afplay`. (work/ is gitignored — never commit game audio.)
- Capture recipe (start from top + record): SS‑2 script
  `[idle30, C, idle45, Down, idle45, C, idle N]` with `--png-dir` to confirm SOUND‑ONLY (luma≈44).

## C — E804 room text **renders English on fresh load** (box‑fit gated)
- Built `output/t001/` via `build_mdt.py --attempt t001 --names-only E804` — **equal‑length, injected
  in place** (no growth): 600a/c000/d000/e001 all `+0 B`.
- **WRAM gotcha confirmed:** from **SS‑2** the menu still shows **Japanese** (the 600a strings are
  already resident in WRAM at that state). Must verify from **SS‑1** (walk in → E804 loads fresh).
- **SS‑1 walk‑in (Up) on the patched disc:** location banner renders **English "THEATER"**; the
  **vanilla** disc through the identical walk shows **"アレント博物館・シアター"**. → my E804 patch **does**
  render on fresh load (no garbage/freeze). ✅
- **Gated:** the banner shows terse **"THEATER"**, not the full **"Alent Museum: Theater"** from
  `E804_en.py` — this is the **box‑measure/font fit** issue owned by the **other agent**; leave as
  `apply-after-font-fix`. Do not edit `subst.py`/SCNRL to force the full name.
- The **menu (600a)** uses the same text‑injection + renderer as the banner (proven), so it should
  render English on fresh load; an exact on‑screen menu shot needs precise navigation to the
  ticket‑machine tile (blind walking from SS‑1 didn't land it). **Recommend the user confirm the menu
  via GUI**, or a later nav‑tuning pass.

## ⚡ BREAKTHROUGH (user said "find a tool / get them off disk") — fully autonomous now
The whole gating dependency (transcripts) and the dramas-2‑5 sourcing are **solved without the user**:

### All 5 dramas extracted + decoded straight off disk
- **GM3.IDX decoded:** 1024 4‑byte BE entries `[tag16][start_sector16]`; the low16 = start sector in
  GM3.STZ (wraps past 65535 — carry it). ~124 entries are ADX streams.
- **The 5 dramas = consecutive ADX idx 295‑299** (clean boundary: idx 294=46 s, 300=16 s; the five are
  the only long block). Durations **252.8 / 345.6 / 375.7 / 278.5 / 308.7 s**, all 22050 Hz stereo,
  ADX type 3. So each drama is **~4‑6 min of unique content** — my earlier "99 s loop" was an *internal
  musical repeat*, NOT the drama looping. Transcribe the whole asset.
- **idx 295 = drama #1** confirmed two ways: the SS‑3 streamed FAD (LBA 114879) lands inside it, and my
  decoded WAV cross‑correlates with the SS‑3 emulator capture at **r=1.000**.
- **Decoder written + validated:** `src/theater/adx.py` (CRI ADX type‑3 ADPCM; ~17 s to decode all 5).
  `python3 src/theater/adx.py extract <track1.bin> --out work/theater` → `work/theater/drama{1..5}_idx*.wav`
  (gitignored). r=1.000 vs the game's own decode proves it's bit‑faithful.

### ASR transcription works (no human in the loop)
- Tool: **faster‑whisper `large-v3`** (CPU int8), in `src/theater/transcribe.py`. Key settings
  (validated): **VAD off**, `no_speech_threshold=0.3`, `compression_ratio_threshold=2.0`,
  `condition_on_previous_text=False`, and a Japanese **initial_prompt** priming the cast names.
- First attempts hallucinated ("ご視聴ありがとうございました"×4) because (a) I fed a 107 s trim that was the
  **instrumental intro** (drama #1's first speech is at **t≈30 s**), and (b) no prompt. On the **full
  clean decode** with the tuned params it produces **coherent Grandia dialogue**.
- **Drama #1 title (spoken at t=0): 「ガンボ、宴会の後で」 ≈ "Gumbo: After the Banquet"** — Sue & Gadan
  after a feast; Gadan asks Sue how to handle women. (ASR output needs human/curation review — 1996 VO
  over music isn't perfect — but it's a solid base + per‑segment timestamps for caption timing.)
- Batch: transcribe all 5 → `work/theater/drama{n}_idx*.asr.{json,txt}` (segments with start/end).

### Remaining (my lane, autonomous)
1. **Curate the 5 ASR transcripts** (fix obvious ASR errors; identify speakers), then **translate
   dictionary‑guided** (`src/dict_cli.py`) + keep names canonical. Output per‑drama caption tables
   `[start,end, JP, EN]` under `src/theater/`.
2. **A3 — caption display mechanism (the hard open task):** RE E804's **event bytecode** to find the
   playback wait‑loop (curtains→SOUND ONLY→stream→wait) and interleave print+wait ops, OR a dedicated
   overlay. The drama **titles** ("Gumbo, After the Banquet"…) also live there / are spoken — capture
   each from the ASR t=0 line.

## A3 — caption DISPLAY mechanism: engine-side playback is the wall (key finding)
Disassembled E804's script (`work/theater/e804parse/`, via `parse-mdt`→`parse-script` + the project's
`subst.parse_box_commands`). Findings:
- **The whole SCN is 884 B = only the 7 text pieces.** No playback piece. The menu piece **600a** is
  three conditional blocks selected by `op4c 4000 000X`: **X=0 → Back** (just `f000`), **X=1 → "Listen"**
  (a table of `7000 / 801a / 80XX / 8011 <arg>` ops, idx args 01‑0d), **X=2 → "Description"** (a 50 B
  text box — this is where the ticket‑description text actually lives, inline, with an embedded `0x5010`
  op; it is NOT a separate piece, which is why `E804_en.py` has no description entry).
- **There is NO audio/stream/curtain/SOUND‑ONLY/wait op anywhere in the editable script.** So the drama
  playback (curtains → SOUND ONLY → stream ADX idx 295‑299 by ticket → wait‑until‑done) is **engine‑side
  code** (SCNRL.BIN / main SH‑2 executable), triggered by the menu result + the inserted ticket — not a
  scriptable MDT sequence.
- **Consequence:** the *preferred* in‑engine "interleave print+wait in the playback loop" is **blocked
  within this lane** — there is no MDT loop to interleave, and the engine routine lives in **SCNRL.BIN
  (the other agent's exclusive file)** or the main EXE. Drawing timed subtitles during playback requires
  an **engine‑side hook** (draw text on a frame timer while the SOUND‑ONLY screen is up). That's a
  cross‑lane + deep‑RE dependency (SH‑2 trace of the playback/wait routine; op80/op70/op4c semantics
  still need tracing). **This is the real open problem; it is NOT solvable by editing E804.MDT text.**
- **Options to put to the user** (display only — the *content* is being produced regardless):
  1. **Engine hook** — patch the playback/wait routine (SCNRL.BIN or EXE) to blit subtitle text on a
     timer. Highest fidelity; needs coordinating SCNRL with the font agent (or an EXE patch) + real RE.
  2. **Companion subtitle track** — ship per‑drama `.srt/.lrc` (+ a tiny synced player or instructions)
     that the player runs alongside the game. No engine risk; not "in‑game", but fully deliverable now.
  3. **Defer display, ship the content** — land the timed EN caption tables for a later engine pass.
- The caption **content** (transcript → translation → `[start,end]` timing) is identical work for all
  three and is being completed now (B2/B3), so this decision does not block progress.

## B2/B3 — DONE: all 5 dramas translated (caption tables + review pages)
All five ASR transcripts curated + translated dictionary-guided → `src/theater/captions/drama{1..5}.json`
(`[start,end,spk,jp,en,note]` per line; ASR errors fixed inline, screams/non-verbal collapsed):
| # | Ticket / ADX | Title (EN) | Cast | lines |
|---|---|---|---|---|
| 1 | idx 295 | Gumbo: After the Banquet | Sue, Gadwin | 53 |
| 2 | idx 296 | This Is the Way of a Man | Justin, Gadwin (voice) | 64 |
| 3 | idx 297 | Where They Fall | Garlyle trio (Saki/Nana/Mio), Mullen, Leen | 72 |
| 4 | idx 298 | Beyond the End of the World | Mullen, Leen, Baal (diary) | 63 |
| 5 | idx 299 | Cooking Showdown! | Sue, Puffy, Nana, Gadwin, Feena | 47 |

**Review (audio synced to captions; edit EN / flag / export):**
`python3 -m http.server 8765` from repo root → **http://localhost:8765/work/theater/index.html**
Names dictionary-guided; added `ガドイン→Gadwin, ガンボ→Gumbo, ルク→Luc` (others already present:
Mullen/Leen/Baal/Gaia/Saki/Nana/Mio/Angelou, **プーイ→Puffy**, **ガーライル→Garlyle Base**, New Parm).
Status = DRAFT (ASR not perfect; a few lines flagged with `note`). User said pilot looks good → keep going.

## USER DECISION (2026-06-28): display = **engine hook (true in-game)**
The user chose in-game subtitles over a companion track. This is **Phase D**, a deep-RE effort:

### Phase D plan — engine-side caption hook
- **Why it's engine-side:** E804's whole SCN is 884 B of text pieces; the playback (curtains→SOUND
  ONLY→ADX stream idx 295‑299→wait) is engine code triggered by the 600a "Listen" handler (the
  `7000/801a/80XX` table). **"SOUND ONLY" is a GRAPHIC** — there is **no "SOUND ONLY" ASCII anywhere on
  the disc**, so the routine can't be string-anchored; it must be found by **SH‑2 tracing**.
- **Find the routine:** set SH‑2 watchpoints starting from the menu op dispatch the dialogue lane
  already mapped (dispatch `0x0601E5C4`, op handler `0x0601E9F2`; trace tooling + dumps in
  `work/scnrl/full_dump_*`). Trace the "Listen" selection → the ADX-stream start (CDBlock play of FAD
  inside GM3.STZ) and the wait-loop / SOUND-ONLY blit. Determine whether that code lives in
  **`SCNRL.BIN`** or the **main executable** (the field interpreter that SCNRL extends).
- **Hook:** during the wait-loop, blit subtitle text on a timer keyed to the **CD stream position**
  (the engine tracks the streamed FAD — use it as the audio clock so captions stay synced). Draw via
  the engine's existing 8x16 text path (control `0x03`) or a direct VDP write over the black screen.
- **Caption clock:** the per-line `[start,end]` in `src/theater/captions/*.json` map to stream offset
  from drama start (the SOUND-ONLY screen begins ~t=0 of the ADX; the emulator menu→curtain preamble
  (~18 s) is NOT part of the asset, so use the ADX-relative times already in the JSON).
- **⚠️ SCNRL coordination:** if the hook lands in `SCNRL.BIN`, that is the **font agent's exclusive
  file** (plan §2.3). The user authorized the engine-hook path (which "needs coordinating SCNRL with
  the font agent"), so this is a sanctioned **compose-not-overwrite** on SCNRL (like the E804 share) —
  coordinate before patching. If the hook is in the **main EXE** instead, no SCNRL conflict.
- **Tooling gap:** the theater lane's audio/jin harnesses don't do SH‑2 watchpoint tracing; reuse/extend
  the dialogue lane's trace setup (`work/scnrl/`). This is the first concrete Phase-D task.
- **NOT YET IMPLEMENTED** — scoped, not built. The caption *content* (above) is complete and feeds it.

## (a) DONE — testable English theater menu disc: `output/t002`
`src/theater/build_e804_menu.py` builds E804 **in place (equal-length, no growth)** so it's testable
from the vanilla savestates (relocated/grown builds like rc_12 read vanilla bytes at the old LBA — the
`t001` vs `rc_12` lesson). It translates the banners normally and rebuilds the **600a menu box
byte-exact**: each line = one `0x03`(8x16)+ASCII run padded to the JP line length, so the ※※ 16x16
decorations (which garble in 8x16) are gone and the op tables after the box are untouched. Fixes the
`t001` garble (the generic `substitute_piece_runs` mangled this menu piece).
- **Verified headlessly:** menu BYTES are correct English (byte-inspected); English **renders** on this
  disc (the "THEATER" banner, fresh-load from SS-1). **GUI gate:** the menu-*open* render — the harness
  can't reliably blind-navigate to the ticket-machine tile (known project limitation; the whole menu
  validation set is GUI-gated). User: walk into the theater on `output/t002` and press C at the machine
  → expect "** Back ** / ** Listen to drama ** / ** View the guide **".
- Also translated the **guide-description box** (the 2nd box in 600a, 50B): JP "ドラマを聞くには
  チケットが必要です / チケットは ギドのアイテムショップで / 売っています" → "Tickets to hear a drama /
  are sold at Gid's shop" (equal-length, byte-verified).
- **KNOWN COSMETIC — the "R" glyph** (deferred, low priority): on `output/t002` each menu line shows a
  stray glyph at the box's far right (looks like "R"). My 74B box content is correct (`0x05` + three
  `0x03`+ASCII lines + `0x07 0x00`), so the artifact is the menu renderer drawing past my line content
  at a fixed right-column (likely the box's original right-edge ※※ decoration position, or an over-read
  of the bytes after `0x07` — the conditional block `1001 4c40…` rendered as a glyph). To fix: compare
  the renderer's per-line column count to the box width; either restore a right-edge decoration glyph at
  that column or ensure the renderer stops at `0x07`. Not worth blocking on; note for a later polish pass.

## (b) STARTED — in-game caption engine hook (the chosen display; multi-session RE)
- **Trace harness built** here: `tools/ymir-harness/build/jinloop-harness` (SH-2
  `--bp`/`--watch`/`--watchr`/`--trace-pc`, `--dump-wram`, `--inject-scn/-addr`). Same YMIR core.
  (`--dump-wram` didn't emit a file in a quick test — verify that flag/codepath first.)
- **Audio clock identified (the caption sync signal):** the CDBlock log during SS-3 playback streams
  **sequential FAD chunks** — `Filter 17 FAD range start=01BFFF count=0x18`, `Play parameters
  start=81BFFF end=800018`, then `Playback ended` → next chunk. So the **current CD playback FAD is the
  audio position**: caption time = `(current_FAD − drama_start_FAD)/75` s → index into
  `src/theater/captions/dramaN.json`. drama_start_FAD = idx 295‑299 LBA+150 (drama1 idx295 → FAD 114606).
- **Remaining RE (next session):** (1) locate the playback **wait-loop** PC (trace PC during SS-3
  SOUND-ONLY) + where current-FAD lives (WRAM var or CDBlock reg, via `--watchr`/`--trace-pc`);
  (2) decide **SCNRL vs main EXE** — ⚠️ if SCNRL, **compose** with the font agent (user-authorized),
  never overwrite; (3) write the hook: per frame compute caption time from FAD, look up the active line,
  **blit 8x16 text** over the black screen; (4) build + verify from SS-3.
- **No shortcut:** harness `--inject` is runtime-WRAM only (not shippable); the real hook patches the
  disc. The caption *content* is done and feeds step 3.
</content>

---

# Parallel-agent round (2026-06-28) — outcomes + user decisions

Two agents ran in parallel (`docs/theater-parallel-agents.md`); both fully MAPPED their target, each
blocked on one thing. Both integrated to `main` (disjoint, linear).

## (b) HOOK — in progress, ~1 session from on-screen captions
- Caption clock SOLVED (live CD FAD @ HWRAM `0x06002008`, writer PC `0x0600427E`, ~12.12 sectors/s,
  per-drama disjoint FAD ranges). FAD-keyed table baker built+tested (`src/theater/hook_caption_table.py`).
- Draw path fully characterized: "SOUND ONLY" is in the **VDP1 sprite framebuffer** (persists) →
  write caption pixels into FB `0x25C80000` (512w, 16bpp), text value `0x050F`, caption region y≈150–210.
  IP.BIN hook site (free gap @ file `0x4DC0`, detour @ `0x227E`); table ships as a loaded disc file.
- See `docs/theater-hook.md`. **USER DECISION:** finish via an **in-repo Python SH-2 mini-assembler**
  (fall back to `sh-elf` only if that fails). Agent (b) resumed to implement + verify.

## (a) GFX — selection-screen plates DECODED, shipping DEFERRED
- The 上映メニュー header + drama-title plates are **pre-rendered 8bpp VDP1 sprites**, reproduced exactly
  from savestate 0 (`docs/theater-gfx/*.png`, `src/theater/gfx_explore.py`). But they're **decompressed
  to VRAM by a custom codec** and not stored raw on disc — the **same codec the minigame lane hit**
  (`docs/mgame-format.md`).
- **USER DECISION:** **DEFER** — leave the title-plate graphics in Japanese for now; revisit after the
  **minigame lane cracks the shared codec** (cracking it unblocks both). Not blocking captions/menu/audio.

---

## SHIPPED (2026-07-02, lane B): captions + English menu + plates in the RC chain
The in-game caption hook, the English 600a menu, and the English title plates now ship together
via `tools/build_rc.py` step 4 (`src/theater/rc_integrate.py`). Full ship-state, the BGM exit-race
root cause + 3-zone bootstrap fix, and the validation evidence: `docs/theater-hook.md` (s14) and
`docs/lanes/laneB-theater.md`. Known limits: drama-1-only, first ~90 s, wrap-16 row truncation
(space-bound: 1516 B free tail; growth paths mapped in the s14 notes). The stray right-edge menu
glyph remains (cosmetic, deferred).

---

## SHIPPED (2026-07-02, lane E): FULL captions — all 5 dramas, full length, no truncation
The s14 space limit is gone: `rc_integrate` now GROWS E804's CPU-load window (header-driven
sector insert, proven live) and ships a 16 KB blob carrying **all 299 translated lines of all 5
dramas** (366 FAD-keyed records; 4-row pages; long lines time-split across pages instead of
truncated — no text dropped or shortened). The vhook also gained clear-on-change (stale-caption
remnants were a latent bug). Full design + the headless ship gates (33/33 sh2emu, per-drama
in-game renders, full-drama run, exit, cold boot): `docs/theater-hook.md` (s15) and
`docs/lanes/laneE-captions.md`. Caption CONTENT (`src/theater/captions/drama{1..5}.json`) is used
verbatim; the JSONs' `review_status: DRAFT` user pass is still the open item for wording.
