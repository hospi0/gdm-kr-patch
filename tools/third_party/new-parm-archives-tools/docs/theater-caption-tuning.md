# Theater caption tuning — how to change caption SPEED / timing yourself

A self-serve guide for adjusting how the 5 theater dramas' captions appear. Written for the rc_27
round after the note "the theater talking is moving a bit too quickly." You can do all of this
without an agent; it's plain data edits + a rebuild.

## How captions work (the 30-second version)

Each drama has a JSON file `src/theater/captions/drama{1..5}.json`. Its `lines` array holds one
record per caption:

```json
{ "start": 44.5, "end": 49.36, "spk": "Gadwin", "jp": "…", "en": "Mmm... Ahh, I've eaten my fill…" }
```

`start`/`end` are **seconds from the start of that drama's audio**. The build converts each line to a
CD-position interval `[start_fad, end_fad)` (`fad = drama_start + round(sec × 12.116)`). At runtime a
tiny hook watches the live CD position and draws **whichever line's interval contains "now"** — and
draws **nothing** when "now" is in a gap between intervals. So:

- A caption **appears** at its `start` and **disappears** at its `end` (or when the next line starts).
- If `end` is small and the next `start` is far away → the text vanishes and the screen is blank until
  the next line = it feels **fast / flickery**.
- Lines never overlap; the table is sorted by `start`.

**There is no single "speed" slider** — speed is the set of `start`/`end` values. `SECTORS_PER_SEC =
12.116` in `src/theater/hook_caption_table.py` is a physical CD constant; **do not change it**.
`SYNC_DELAY_SECTORS = 19` shifts *every* line by a fixed amount (use it only if captions are
uniformly early/late — it does NOT change how long each line stays up).

## To make captions MOVE SLOWER — the built-in knob (rc_27)

The lines are back-to-back (each `end` == the next `start`), so there are no blank gaps to fill —
the "too fast" is **short lines flashing by**. rc_27 added a **minimum on-screen dwell** that fixes
this automatically at build time. Two constants in `src/theater/hook_caption_table.py`:

```python
MIN_CAPTION_DWELL_SEC = 2.5   # every caption stays at least this long (raise = slower)
MAX_CAPTION_SHIFT_SEC = 1.0   # ...but a line may delay its neighbour's appearance by at most this
```

How it works: a line shorter than `MIN_CAPTION_DWELL_SEC` borrows time by moving its shared boundary
with the next line later — but only as much as the neighbour can spare while itself staying ≥ the
minimum, and never more than `MAX_CAPTION_SHIFT_SEC`. No overlaps, no cascade past the neighbour, no
desync from the voice beyond the small bounded shift.

**To slow captions down more:** raise `MIN_CAPTION_DWELL_SEC` (e.g. 3.0) and/or `MAX_CAPTION_SHIFT_SEC`
(e.g. 1.5). To turn it off entirely, set `MIN_CAPTION_DWELL_SEC = 0`. Then rebuild (below).
(rc_27 defaults 2.5 / 1.0 fixed drama-1's 4 sub-2s flashes → 0, drama-2/5's 9 → 2, etc.)

### If you'd rather hand-edit individual lines
Raise a specific line's `end` in `src/theater/captions/drama{1..5}.json` (up to the next line's
`start`, or a bit past it to linger). Or bulk "hold each line until the next begins":

```python
import json
for n in range(1, 6):
    p = f"src/theater/captions/drama{n}.json"
    d = json.load(open(p)); L = d["lines"]
    for i in range(len(L) - 1):
        L[i]["end"] = round(min(L[i+1]["start"], L[i]["end"] + 4.0), 2)  # cap extra dwell at +4s
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
```

Other knobs:
- **A specific line flashes by too fast:** just raise that one line's `end` (up to the next `start`).
- **A caption appears BEFORE the voice** (like rc_26's Gadwin bug): its `start` is wrong — set `start`
  to the real voice onset (measure with `work/pCAP_analysis/word_asr.py` if you want exact numbers).
- **Everything is uniformly a bit early/late:** nudge `SYNC_DELAY_SECTORS` in
  `src/theater/hook_caption_table.py` (each +12 ≈ +1 s later). Rerun the selftest after.

## Rebuild + verify

1. **Rebuild the disc** (folds the new timings via the theater step):
   ```
   python3 tools/build_rc.py 27
   ```
   (or, to iterate only the theater step on an existing track:
   `python3 tools/build_rc.py <tag> --theater-only output/rc_26/Track1.bin`)
2. **Gate:** `python3 src/theater/hook_loader.py --selftest` → expect `37 passed`.
3. **Watch it:** load `output/rc_27/Grandia-DM-patched.cue` in YMIR, play a drama in the theater.
   (Only drama 1 is reachable headlessly; dramas 2-5 need a ticket in the machine, so verify those in
   the GUI.)

## Files
- Timings you edit: `src/theater/captions/drama{1..5}.json` (`lines[].start` / `lines[].end`).
- Engine constants (rarely touch): `src/theater/hook_caption_table.py`
  (`SECTORS_PER_SEC` = physical, leave; `SYNC_DELAY_SECTORS` = global shift).
- Measurement helper (optional, for exact voice onsets): `tools/ymir-audio-harness/` +
  `work/pCAP_analysis/word_asr.py` (word-level ASR + audio energy envelope).
- Background: `docs/theater-hook.md`, `docs/lanes/laneL-sync.md`, `docs/lanes/laneCAP-headtiming.md`.
