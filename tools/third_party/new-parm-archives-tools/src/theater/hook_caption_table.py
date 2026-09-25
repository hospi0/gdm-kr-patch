#!/usr/bin/env python3
"""Bake the 5 theater drama caption JSONs into a compact, FAD-keyed binary table
for the in-game caption engine hook (theater lane (b)).

WHY FAD-keyed: the drama audio is ADX streamed from /FIELD/GM3.STZ. During playback the
engine writes the live CD playback FAD to a runtime variable (HWRAM 0x06002008, in the
IP.BIN data area). The 5 dramas occupy *disjoint, contiguous* FAD ranges on disc, so a
single read of that variable tells the hook BOTH which drama is playing AND the position.

So we bake every caption line as an absolute [start_fad, end_fad) interval. At runtime the
hook does only integer compares (NO division, NO float) — it scans the (start-sorted) table
for the record whose interval contains the live FAD and draws that record's text. Drama
boundaries are implicit (gaps between dramas simply have no records).

CLOCK CALIBRATION (measured, see docs/theater-hook.md):
  caption audio streams at ~12.116 CD sectors / second (ADX 22050 Hz stereo, type 3),
  NOT the Red-Book 75 sectors/s. drama_start_FAD = (GM3_LBA + idx_start_sector) + 150.
    seconds -> FAD:  fad = drama_start_fad + round(sec * SECTORS_PER_SEC)

Usage:
  python3 src/theater/hook_caption_table.py            # -> work/theater/hook/caption_table.{bin,json,inc}
  python3 src/theater/hook_caption_table.py --track1 <Track1.bin>   # recompute FADs from disc IDX
  python3 src/theater/hook_caption_table.py --out DIR --wrap 40

The .bin is a build input for the engine hook (placed on-disc by the hook's disc builder);
the .json/.inc are human-readable (review + asm constants). Outputs go under work/ (gitignored)
unless --out points elsewhere; the .inc/.json may be committed for reference.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

# --- clock + geometry constants (the enabling RE result) -------------------------------
SECTORS_PER_SEC = 12.116          # measured, consistent across all 5 dramas (see docs)
FAD_OFFSET = 150                  # LBA -> FAD
GM3_LBA = 39128                   # /FIELD/GM3.STZ start LBA
DRAMA_IDX = list(range(295, 300)) # ADX indices of the 5 dramas inside GM3.STZ

# Per-drama start sector inside GM3.STZ + duration (s), from src/theater/adx.py IDX decode.
# These are the disc-faithful defaults; pass --track1 to recompute from the live IDX.
DRAMA_START_SEC = {295: 75328, 296: 78391, 297: 82578, 298: 87129, 299: 90504}
DRAMA_END_SEC   = {295: 78391, 296: 82578, 297: 87129, 298: 90504, 299: 94245}

MAGIC = b"GDMC"
VERSION = 1

# --- caption pacing (user rc_27 feedback: "captions moving too quickly") ----------------
# The ASR lines are back-to-back (each line's end == the next line's start), so some short
# lines flash by in under a second and read as "too fast". We enforce a minimum on-screen
# time: for a line shorter than MIN_CAPTION_DWELL_SEC, push the boundary with the NEXT line
# later (this line grows, the neighbour starts a touch later — never OVERLAP, never cascade,
# and the neighbour is never pushed below MIN_CAPTION_DWELL_SEC). MAX_CAPTION_SHIFT_SEC caps
# how far the neighbour's appearance may be delayed from its voice. Set MIN=0 to disable.
# See docs/theater-caption-tuning.md — these are the self-serve "slow it down" knobs.
MIN_CAPTION_DWELL_SEC = 2.5
MAX_CAPTION_SHIFT_SEC = 1.0


def enforce_min_dwell(lines: list[dict],
                      min_dwell: float = MIN_CAPTION_DWELL_SEC,
                      max_shift: float = MAX_CAPTION_SHIFT_SEC) -> list[tuple[float, float]]:
    """Return [(start,end)] per line with a minimum on-screen dwell.

    Back-to-back lines only: a short line borrows time by moving its shared boundary with the
    next line later, but only as much as the next line can spare while staying >= min_dwell,
    and never more than max_shift. No overlaps are created (so no draw-order ambiguity), and a
    line's END is never moved, so effects never cascade past the immediate neighbour.
    """
    se = [(float(l["start"]), float(l["end"])) for l in lines]
    if min_dwell <= 0:
        return se
    for i in range(len(se) - 1):
        s, e = se[i]
        dwell = e - s
        if dwell >= min_dwell:
            continue
        ns, ne = se[i + 1]
        # only borrow if the lines are actually contiguous (no real blank gap to fill first)
        if abs(ns - e) > 0.05:
            continue
        spare = (ne - ns) - min_dwell          # time the neighbour can give up
        delta = min(min_dwell - dwell, max_shift, max(0.0, spare))
        if delta > 0:
            se[i] = (s, round(e + delta, 3))
            se[i + 1] = (round(ns + delta, 3), ne)
    return se


def transliterate(s: str) -> str:
    """Map the few non-ASCII glyphs to the engine's 8x16 single-byte ASCII font."""
    return (s.replace("—", "--")   # em dash
             .replace("–", "-")    # en dash
             .replace("…", "...")  # ellipsis
             .replace("‘", "'").replace("’", "'")
             .replace("“", '"').replace("”", '"')
             .encode("ascii", "replace").decode("ascii"))


def wrap(text: str, width: int) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            out.append(cur)
            cur = word
        # hard-split a single over-long word
        while len(cur) > width:
            out.append(cur[:width])
            cur = cur[width:]
    if cur:
        out.append(cur)
    return out


def drama_start_fad(idx: int) -> int:
    return GM3_LBA + DRAMA_START_SEC[idx] + FAD_OFFSET


def sec_to_fad(idx: int, sec: float) -> int:
    return drama_start_fad(idx) + round(sec * SECTORS_PER_SEC)


def load_idx_from_disc(track1: str) -> None:
    """Recompute DRAMA_START_SEC/END_SEC from the live GM3.IDX (keeps the table disc-faithful)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import adx  # type: ignore
    with open(track1, "rb") as f:
        idx = adx.read_logical(f, adx.GM3_LBA - 2, 4096)
    abs_sec = adx.parse_idx(idx)
    for k in DRAMA_IDX:
        DRAMA_START_SEC[k] = abs_sec[k]
        DRAMA_END_SEC[k] = abs_sec[k + 1]


def build(out_dir: Path, wrap_w: int, with_speaker: bool):
    cap_dir = Path(__file__).resolve().parent / "captions"
    records = []   # (start_fad, end_fad, [display_lines], meta)
    review = []
    for n, idx in enumerate(DRAMA_IDX, 1):
        d = json.loads((cap_dir / f"drama{n}.json").read_text())
        sfad = drama_start_fad(idx)
        # drama-range end = next drama's start sector mapped through FAD
        drange_end = GM3_LBA + DRAMA_END_SEC[idx] + FAD_OFFSET
        # pace: enforce a minimum on-screen dwell (rc_27 "too fast" fix) in seconds space,
        # before the FAD conversion + the global SYNC_DELAY shift (which are orthogonal).
        dwell_se = enforce_min_dwell(d["lines"])
        for ln, (s_sec, e_sec) in zip(d["lines"], dwell_se):
            start = sec_to_fad(idx, s_sec)
            end = sec_to_fad(idx, e_sec)
            if end <= start:
                end = start + 1
            text = transliterate(ln["en"])
            spk = (ln.get("spk") or "").strip()
            if with_speaker and spk and spk.lower() != "title":
                text = f"{transliterate(spk)}: {text}"
            disp = wrap(text, wrap_w)
            records.append((start, end, disp))
            review.append({"drama": n, "idx": idx, "spk": spk,
                           "start_fad": start, "end_fad": end,
                           "start_s": ln["start"], "end_s": ln["end"],
                           "lines": disp})
        # sanity: every line FAD must fall inside this drama's disc range
        assert sfad <= records[-1][0] < drange_end, (n, sfad, records[-1][0], drange_end)

    records.sort(key=lambda r: r[0])

    # --- serialize: header + record array + string pool ---------------------------------
    # header: magic(4) ver(u16) nrec(u16) rate_milli(u32) reserved(u16)
    # record: start_fad(u32) end_fad(u32) str_off(u16)  [12 bytes]
    # string: u8 nlines, then per line: u8 len + bytes  (lines are display rows)
    pool = bytearray()
    pool_index = {}
    def intern(disp_lines):
        key = tuple(disp_lines)
        if key in pool_index:
            return pool_index[key]
        off = len(pool)
        pool.append(len(disp_lines) & 0xFF)
        for row in disp_lines:
            b = row.encode("ascii")[:255]
            pool.append(len(b))
            pool.extend(b)
        pool_index[key] = off
        return off

    rec_bytes = bytearray()
    for start, end, disp in records:
        off = intern(disp)
        rec_bytes += struct.pack(">IIH", start, end, off)

    header = MAGIC + struct.pack(">HHIH", VERSION, len(records),
                                 round(SECTORS_PER_SEC * 1000), 0)
    blob = header + rec_bytes + bytes(pool)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "caption_table.bin").write_bytes(blob)
    (out_dir / "caption_table.json").write_text(json.dumps(review, indent=1, ensure_ascii=False))

    # asm/C constants header for the engine hook
    inc = []
    inc.append("; theater caption-engine constants (generated by hook_caption_table.py)")
    inc.append(f"; SECTORS_PER_SEC = {SECTORS_PER_SEC}  (ADX 22050Hz stereo; NOT 75/s)")
    inc.append("; FAD variable (live CD playback pos, IP.BIN data area) = 0x06002008")
    inc.append(f".equ CAP_FAD_VAR,      0x06002008")
    inc.append(f".equ CAP_RECORD_SIZE,  12          ; start_fad(4) end_fad(4) str_off(2) +pad")
    inc.append(f".equ CAP_NUM_RECORDS,  {len(records)}")
    inc.append(f".equ CAP_HEADER_SIZE,  14")
    for n, idx in enumerate(DRAMA_IDX, 1):
        s = drama_start_fad(idx)
        e = GM3_LBA + DRAMA_END_SEC[idx] + FAD_OFFSET
        inc.append(f".equ DRAMA{n}_FAD_LO, 0x{s:06X}   ; idx {idx}")
        inc.append(f".equ DRAMA{n}_FAD_HI, 0x{e:06X}")
    (out_dir / "caption_table.inc").write_text("\n".join(inc) + "\n")

    print(f"baked {len(records)} caption records, {len(pool)} B string pool, blob {len(blob)} B")
    print(f"  -> {out_dir/'caption_table.bin'}")
    print(f"  -> {out_dir/'caption_table.json'}  (review)")
    print(f"  -> {out_dir/'caption_table.inc'}   (asm consts)")
    print("drama FAD ranges:")
    for n, idx in enumerate(DRAMA_IDX, 1):
        s = drama_start_fad(idx); e = GM3_LBA + DRAMA_END_SEC[idx] + FAD_OFFSET
        print(f"  drama{n} idx{idx}: 0x{s:06X}..0x{e:06X}  ({e-s} sectors, "
              f"{(e-s)/SECTORS_PER_SEC:.1f}s)")


# --------------------------------------------------------------------------------------------
# Lane E: the FULL 5-drama table in the *vhook* record format (hook_loader VHOOK16_SRC scanner).
#
# Record format (== hook_build.bake_drama1_table, unchanged asm): start_rel(u16) end_rel(u16)
# body_len(u16) body(ASCII rows joined by \n, space-padded to even). Terminator start_rel=0xFFFF.
# rel FADs are relative to VHOOK_FAD_LO (= drama 1's start FAD): the 5 dramas span 0x1BFAE..0x20993
# absolute -> max rel 0x49E5, safely u16. Gaps between dramas simply have no records.
#
# PAGINATION (the fix for the wrap-16 3-row truncation): a caption whose wrapped text exceeds
# `max_rows` display rows is TIME-SPLIT into sequential page records over the line's interval,
# proportionally to each page's character count. Pages may extend into the trailing gap before the
# next line (up to PAGE_GAP_EXT sectors) so short-duration long lines still get readable pages; if
# the whole window is narrower than n_pages*PAGE_MIN_SECT the pages get equal shares (best effort —
# the FAD clock advances in ~24-sector chunk steps, so sub-24-sector pages can display late/skip).
PAGE_MIN_SECT = 24     # one CD chunk = the FAD-clock staircase step (~2 s)
PAGE_GAP_EXT = 48      # how far a line's pages may run into the gap before the next line

# Lane I/L (user rc_23 + rc_24 feedback): captions ran AHEAD of the voice. Global constant delay
# added to EVERY record's start/end (individual line timings untouched).
#
# Lane L MEASURED the true offset (2026-07: audio-harness --fad-log run of drama 1 on rc_24 from
# saves/user-theater-menu-rc23; per-frame live FAD @0x06002008 + captured WAV cross-correlated
# against the decoded ADX = the ASR timebase; xcorr peak 0.949. See
# tools/ymir-audio-harness/analyze_sync.py + docs/lanes/laneL-sync.md):
#   raw clock lead vs audible audio = min -0.1 / MEAN +1.0 / max +2.1 s — a 24-sector (~2 s)
#   staircase (the FAD var jumps once per 24-sector CD chunk). So with the old total shift of
#   13 sectors (FAD_LEAD 5 + delay 8), appearances were CENTERED on the voice (median +0.03 s)
#   but 17/53 drama-1 lines still popped up to 0.97 s BEFORE their voice — the "too fast".
# Fix: total shift = 24 sectors (= one FAD staircase step; FAD_LEAD_SECTORS 5 + THIS 19):
#   measured per-line appearance deltas become min +0.03 / mean +0.93 / max +1.95 s —
#   NO caption ever precedes its voice, none is ever >2 s late (the staircase floor).
# Tuning: sectors = seconds * 12.116; display quantizes to the ~24-sector chunk steps.
SYNC_DELAY_SECTORS = 19

# Lane I: per-ROW horizontal centering, baked as LEADING SPACES (the vhook's space glyph blits
# nothing and advances the pen 16 px, so padding needs ZERO asm change and the selftest's
# independent reference blit stays byte-exact). Rows are centered within the wrap_w-column field;
# the field itself is placed over the stage center by hook_loader.CAP_X16 (see there). Integer
# glyph padding centers each row to within half a glyph (8 px).

def _wrap_rows(text: str, width: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            out.append(cur)
            cur = w
        while len(cur) > width:      # hard-split an over-long word
            out.append(cur[:width])
            cur = cur[width:]
    if cur:
        out.append(cur)
    return out


def vhook_fad_range() -> tuple[int, int]:
    """Absolute [lo, hi) FAD gate for the 5-drama vhook: drama-1 start .. drama-5 end."""
    lo = min(drama_start_fad(i) for i in DRAMA_IDX)
    hi = max(GM3_LBA + DRAMA_END_SEC[i] + FAD_OFFSET for i in DRAMA_IDX)
    return lo, hi


def bake_vhook_table(wrap_w: int = 16, max_rows: int = 4, fad_offset: int = 0,
                     sync_delay: int = SYNC_DELAY_SECTORS, center: bool = True):
    """Bake ALL 5 drama caption JSONs into one vhook-format table. Returns (bytes, meta).

    `fad_offset` (sectors) shifts every interval later to compensate the CD clock's read-ahead
    lead (see hook_build.bake_drama1_table / FAD_LEAD_SECTORS). `sync_delay` (sectors) is the
    additional GLOBAL lag (SYNC_DELAY_SECTORS; user rc_23 feedback — captions ran ahead of the
    voice). `center=True` bakes per-row leading-space centering within the wrap_w-column field
    (see the lane-I note above). Text is uppercased (the blob ships the 0x20..0x5F font) with
    'SPEAKER: ' prefixes except title cards."""
    cap_dir = Path(__file__).resolve().parent / "captions"
    lo, hi = vhook_fad_range()
    off = fad_offset + sync_delay
    recs = []                      # (start_rel, end_rel, body_bytes)
    stats = {"lines": 0, "records": 0, "split_lines": 0, "squeezed_pages": 0}
    per_drama = {}
    for n, idx in enumerate(DRAMA_IDX, 1):
        d = json.loads((cap_dir / f"drama{n}.json").read_text())
        lines = d["lines"]
        # pace (rc_27 "captions too fast"): enforce a minimum on-screen dwell in seconds space,
        # before the FAD conversion / SYNC_DELAY shift / pagination. See enforce_min_dwell +
        # docs/theater-caption-tuning.md (MIN_CAPTION_DWELL_SEC / MAX_CAPTION_SHIFT_SEC knobs).
        dwell_se = enforce_min_dwell(lines)
        base = drama_start_fad(idx)
        drama_hi = GM3_LBA + DRAMA_END_SEC[idx] + FAD_OFFSET
        n0 = len(recs)
        for i, ln in enumerate(lines):
            stats["lines"] += 1
            s = base + round(dwell_se[i][0] * SECTORS_PER_SEC) + off
            e = base + round(dwell_se[i][1] * SECTORS_PER_SEC) + off
            if e <= s:
                e = s + 1
            txt = transliterate(ln["en"]).upper()
            spk = (ln.get("spk") or "").strip()
            if spk and spk.lower() != "title":
                txt = transliterate(spk).upper() + ": " + txt
            rows = _wrap_rows(txt, wrap_w)
            pages = [rows[j:j + max_rows] for j in range(0, len(rows), max_rows)]
            # page window: the line's own interval, extendable into the gap before the next line
            if i + 1 < len(lines):
                nxt = base + round(dwell_se[i + 1][0] * SECTORS_PER_SEC) + off
            else:
                nxt = drama_hi
            wend = max(e, min(nxt, e + PAGE_GAP_EXT))
            npg = len(pages)
            if npg > 1:
                stats["split_lines"] += 1
            weights = [sum(len(r) for r in p) or 1 for p in pages]
            total_w = sum(weights)
            span = wend - s
            if span < npg * PAGE_MIN_SECT:
                if npg > 1:
                    stats["squeezed_pages"] += npg
                bounds = [s + round(span * k / npg) for k in range(npg + 1)]
            else:
                # proportional shares, each clamped to >= PAGE_MIN_SECT
                shares = [max(PAGE_MIN_SECT, round(span * w / total_w)) for w in weights]
                over = sum(shares) - span
                k = 0
                while over > 0:      # trim the largest shares back down to fit
                    j = max(range(npg), key=lambda x: shares[x])
                    cut = min(over, shares[j] - PAGE_MIN_SECT)
                    shares[j] -= cut
                    over -= cut
                    k += 1
                    if k > 2 * npg:
                        break
                bounds = [s]
                for sh in shares:
                    bounds.append(bounds[-1] + sh)
                bounds[-1] = wend
            for p, (ps, pe) in zip(pages, zip(bounds, bounds[1:])):
                if pe <= ps:
                    pe = ps + 1
                if center:   # lane I: leading-space centering (see module note above)
                    p = [" " * ((wrap_w - len(r)) // 2) + r for r in p]
                body = "\n".join(p).encode("ascii")
                if len(body) & 1:
                    body += b"\x20"
                recs.append((ps - lo, pe - lo, body))
                stats["records"] += 1
        per_drama[n] = len(recs) - n0
    recs.sort(key=lambda r: r[0])
    out = bytearray()
    for ps, pe, body in recs:
        assert 0 <= ps < pe <= 0xFFFE, (ps, pe)
        out += struct.pack(">HHH", ps, pe, len(body)) + body
    out += struct.pack(">H", 0xFFFF)
    # sync_delay can push the final record(s) past the nominal drama-5 end; widen the vhook FAD
    # gate so those still draw (harmless: past the gate the table simply has no records).
    hi = max(hi, lo + max(pe for _, pe, _ in recs))
    meta = {"fad_lo": lo, "fad_hi": hi, "table_len": len(out), "per_drama": per_drama,
            "sync_delay": sync_delay, "centered": center, **stats}
    return bytes(out), meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="work/theater/hook")
    ap.add_argument("--track1", help="recompute drama FADs from this Track1.bin's GM3.IDX")
    ap.add_argument("--wrap", type=int, default=40, help="max chars per on-screen 8x16 line")
    ap.add_argument("--no-speaker", action="store_true", help="omit 'Name:' prefix")
    a = ap.parse_args()
    if a.track1:
        load_idx_from_disc(a.track1)
    build(Path(a.out), a.wrap, not a.no_speaker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
