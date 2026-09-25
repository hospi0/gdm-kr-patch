#!/usr/bin/env python3
"""Structure-preserving English substitution in Grandia dialogue (Step 2 method).

Correct encoding model (see docs/script-format.md), default 16x16 font:
  0x00-0x0F  control codes   (0x01 newline, 0x02 new-box, 0x03 8x16 font, 0x04 16x16 font,
                              0x07 end, 0x0E pause, 0x0F = 6-byte box header `0F xx 0A 0C 00 NN`)
  0x10-0x1F  page selector -> TWO-byte character (this byte + next)
  0x20-0xFF  single-byte page-0 character

We keep all control codes in place (preserving line/box structure and byte budget) and refill
each maximal TEXT run (1- and 2-byte chars between controls) with English in the 8x16 font:
`0x03` + ASCII, flowing whole words across runs so words are never split, padding with spaces.
Equal length is preserved (English in 8x16/8px is never wider than the JP it replaces), so the
result is safe to inject in place.
"""
from __future__ import annotations

END = 0x07
FONT_8X16 = 0x03
FONT_16X16 = 0x04

# Portrait/speaker code (from ScriptPortraitCorrector.java): 0F [pos] [vAlign] + 3 = 6 bytes.
# pos in {03=left, 12=middle, 21=right}, vAlign = 0A.
PORTRAIT_POS = (0x03, 0x12, 0x21)


def _is_portrait(data: bytes, i: int) -> bool:
    return (i + 5 < len(data) and data[i] == 0x0F
            and data[i + 1] in PORTRAIT_POS and data[i + 2] == 0x0A)


def _is_control(b: int) -> bool:
    return b <= 0x0F


def _tokenize_box(box: bytes):
    """Yield ('ctrl', bytes) or ('text', length) tokens for box content (after the 6-byte
    starting portrait code)."""
    i, n = 6, len(box)
    while i < n:
        c = box[i]
        if c == END:
            yield ("ctrl", box[i:i + 1]); i += 1; break
        if _is_portrait(box, i):
            yield ("ctrl", box[i:i + 6]); i += 6
        elif _is_control(c):
            yield ("ctrl", box[i:i + 1]); i += 1
        else:
            j = i
            glyphs = 0
            while j < n and not _is_control(box[j]):
                j += 2 if 0x10 <= box[j] <= 0x1F else 1
                glyphs += 1
            yield ("text", box[i:j], glyphs); i = j


class WordFlow:
    """Hands out whole words to fill fixed byte budgets; never splits a word."""
    def __init__(self, text: str):
        self.words = text.split()
        self.k = 0

    def fill(self, budget: int, glyph_cap: int | None = None) -> bytes:
        """Exactly `budget` bytes: 0x03 + English + non-printing 0x03 padding.

        To keep the game's (16x16-based) box-size calc correct, cap the visible English to
        `glyph_cap` characters (≈ the original glyph count) and pad the rest with 0x03, which is a
        non-printing font-switch — so the box stays its original on-screen size.
        """
        if budget <= 1:
            return bytes([FONT_8X16]) * budget
        cap = budget - 1
        if glyph_cap is not None:
            cap = min(cap, glyph_cap)
        line = ""
        while self.k < len(self.words):
            w = self.words[self.k]
            add = w if not line else " " + w
            if len(line) + len(add) <= cap:
                line += add; self.k += 1
            else:
                if not line:
                    line = w[:cap]; self.words[self.k] = w[cap:]
                break
        body = line.encode("ascii", "replace")
        pad = budget - 1 - len(body)
        return bytes([FONT_8X16]) + body + bytes([FONT_8X16]) * pad


def iter_segments(data: bytes, start_variants=PORTRAIT_POS):
    """Yield (idx, pos_byte, seg_start, seg_end) per portrait-delimited SEGMENT inside dialogue
    boxes. A segment runs from one portrait code to the next portrait code or the box's 0x07.
    seg_start points at the portrait code (6 bytes); text runs are after it."""
    i = 0
    idx = 0
    while i < len(data):
        if _is_portrait(data, i) and data[i + 1] in start_variants:
            try:
                end = data.index(END, i + 6)
            except ValueError:
                break
            cuts = []
            j = i
            while j <= end:
                if _is_portrait(data, j):
                    cuts.append(j); j += 6
                else:
                    j += 1
            cuts.append(end + 1)
            for s in range(len(cuts) - 1):
                yield idx, data[cuts[s] + 1], cuts[s], cuts[s + 1]
                idx += 1
            i = end + 1
        else:
            i += 1


_FOLD = {"—": "-", "–": "-", "…": "...", "‘": "'", "’": "'", "“": '"', "”": '"',
         "～": "~", "♪": "~", "★": "*", "※": "*", "　": " "}


def _enc(s: str) -> bytes:
    """ASCII-fold common typographic glyphs (em dash, ellipsis, curly quotes) then encode 8x16
    ASCII, so they render instead of becoming '?'."""
    for k, v in _FOLD.items():
        s = s.replace(k, v)
    return s.encode("ascii", "replace")


def _wrap(text: str, width: int):
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def _grow_segment(seg: bytes, english: str | None, wrap: int, min_glyphs: int) -> bytes:
    """Rebuild one segment, replacing its fillable text runs with the FULL English (wrapped),
    allowing the segment to grow. Preserves the portrait code, controls, and short runs."""
    if not english:
        return seg
    out = bytearray(seg[:6])
    toks = list(_tokenize_box(seg))
    fill_idxs = [i for i, t in enumerate(toks) if t[0] == "text" and t[2] >= min_glyphs]
    lines = _wrap(english, wrap)
    li = 0
    for i, t in enumerate(toks):
        if t[0] == "ctrl":
            out += t[1]
        elif i in fill_idxs:
            if i == fill_idxs[-1]:  # last run gets all remaining lines (joined by newline 0x01)
                rem = lines[li:] or [""]
                li = len(lines)
                out += b"\x01".join(bytes([FONT_8X16]) + l.encode("ascii", "replace") for l in rem)
            else:
                l = lines[li] if li < len(lines) else ""
                li += 1
                out += bytes([FONT_8X16]) + l.encode("ascii", "replace")
        else:  # short text run, keep original
            out += t[1]
    return bytes(out)


def iter_text_runs(data: bytes):
    """Yield (run_idx, start, end) for every maximal TEXT run in a piece, in order, skipping
    control codes and 6-byte portrait codes. Indexing matches validate_en._piece_text_runs and
    the RUN_TEXTS keys in script/<MDT>_en.py (run-name pieces c000/d0xx/e001)."""
    i, n, ri = 0, len(data), 0
    while i < n:
        if _is_portrait(data, i):
            i += 6
        elif data[i] <= 0x0F:
            i += 1
        else:
            j = i
            while j < n and not (data[j] <= 0x0F or _is_portrait(data, j)):
                j += 2 if 0x10 <= data[j] <= 0x1F else 1
            yield ri, i, j
            ri += 1
            i = j


def _run_glyphs(run: bytes) -> int:
    i, g = 0, 0
    while i < len(run):
        i += 2 if 0x10 <= run[i] <= 0x1F else 1
        g += 1
    return g


def best_fit_name(text: str, glyph_budget: int) -> str:
    """Choose the most informative form of a location/door/save name that fits glyph_budget.

    Step-2 names are written "Area: Sublocation" (e.g. "Alent Museum: Library") for clarity, but
    the original JP banner box only had room for the sublocation ("図書室"). When the full English
    overflows the box budget, drop the area prefix(es) and keep the distinctive tail — which both
    fits and is more faithful to what the JP actually showed. Returns the longest candidate that
    fits; if none fit, the shortest at a WORD boundary (so an over-budget sublocation cuts between
    words, e.g. "Screening Room"->"Screening", not mid-word "Screening Ro"; the caller still
    glyph-caps)."""
    cands = [text]
    # The sublocation(s) to word-truncate: the part(s) after "Area: " when present, else the whole
    # name. We never word-truncate the area-prefixed full string, or we'd surface a useless
    # "Alent Museum:" fragment over the meaningful sublocation (the JP banner showed only the sub).
    if ": " in text:
        tails = [text.split(": ", 1)[1], text.rsplit(": ", 1)[1]]
    else:
        tails = [text]
    short = []
    for t in tails:
        w = t.split()
        for k in range(len(w) - 1, 0, -1):
            short.append(" ".join(w[:k]))
    seen, uniq = set(), []
    for c in cands + tails + short:
        if c not in seen:
            seen.add(c); uniq.append(c)
    fitting = [c for c in uniq if len(c) <= glyph_budget]
    if fitting:
        return max(fitting, key=len)
    return min(uniq, key=len)


def encode_16x16_page0(s: str) -> bytes:
    """Encode ASCII into the 16x16 default font's page-0 codes (space=0x20, 0-9=0x21-0x2A,
    A-Z=0x2B-0x44). Uppercases letters (16x16 page-0 has no lowercase); unsupported chars -> space.
    Use this for pieces whose renderer IGNORES the 0x03 8x16 font switch (door-target / save-name
    banners) — page-0 text renders correctly in the default font with no switch needed."""
    out = bytearray()
    for ch in s.upper():
        if ch == " ":
            out.append(0x20)
        elif "0" <= ch <= "9":
            out.append(0x21 + (ord(ch) - ord("0")))
        elif "A" <= ch <= "Z":
            out.append(0x2B + (ord(ch) - ord("A")))
        else:
            out.append(0x20)
    return bytes(out)


# Banner box geometry (measured from the rendered 352x224 frame, the fixed location banner, rc_17
# state 3): the box is screen-centred; with `lead` leading 8x16 spaces the name's left edge sits at
# ~(BANNER_ORIGIN_PX + lead*8), and the box centre is BANNER_CENTER_PX. To centre a `body`-char name
# (8px/char): lead = (CENTER - ORIGIN - body*8/2)/8 = BANNER_CENTER_CELLS - body/2.
BANNER_CENTER_PX = 176
BANNER_ORIGIN_PX = 56
BANNER_CENTER_CELLS = (BANNER_CENTER_PX - BANNER_ORIGIN_PX) // 8   # = 15
BANNER_MAX_CELLS = 30                                             # box text area width (clip overflow)


def substitute_piece_banner_center(data: bytes, run_map: dict) -> bytes | None:
    """GROW-to-CENTRE an 8x16 ROOM-ENTRY banner (c000/e001: `0x2NNN name 0x07`, nothing after the
    name) in its fixed box. The English name is half-width, so left-aligned it sits in the left of
    the wide JP-sized box; the equal-length path can only add `pad_budget` (~7) leading spaces — not
    enough to reach centre. Here we GROW the `0x2NNN` box content: front-pad with
    `BANNER_CENTER_CELLS - body/2` 8x16 spaces, then body + a 0x04+space COMMIT (so the 0x07
    terminator renders clean), and bump NNN by the growth.

    ROOM-ENTRY BANNERS ONLY (rc_18 lesson): door-preview (d0xx) banners carry a trailing
    window-setup/arrow element `0a 00 d0 7c` between the name and the piece end; growing the box
    pushes it past the box terminator (stray "∧" + flickering wrong door names). Callers must route
    only c000/e001 here; as a belt-and-braces guard this returns None (caller falls back to the
    equal-length path) if the bytes after the replaced run are anything but the 0x07 terminator
    (+ optional trailing 0x00 pad / piece end). GDM_8X16 only. Returns None if `data` isn't a
    0x2NNN box."""
    if len(data) < 2 or (data[0] >> 4) != 2:
        return None
    nnn = ((data[0] << 8) | data[1]) & 0x0FFF
    runs = {ri: (a, b) for ri, a, b in iter_text_runs(data)}
    key = next((ri for ri in run_map if ri in runs), None)
    if key is None:
        return data
    a, b = runs[key]
    if a != 0:
        return None          # name run must start at the box command itself (c000/e001 shape)
    tail = data[b:]
    if not tail or tail[0] != END or any(x not in (0x00, END, 0xF0) for x in tail[1:]):
        return None          # trailing structure after the name (d0xx arrow element) -> not safe
                             # (only the 0x07 terminator + 0xf0 0x00 piece-end bytes may follow)
    name_start = 2
    full = run_map[key]
    sub = full.split(": ", 1)[1] if ": " in full else full
    body = _enc(sub)[:BANNER_MAX_CELLS - 2]
    # Measured geometry (pA_widen/pA_widen2/pA_widen3 A/B walks, Library banner, 352px frame):
    #   * The banner box is screen-centred and SIZED TO CONTENT by a width calculator that tracks
    #     the 0x04/0x03 font switches (16px vs 8px per glyph byte) but counts DEFAULT-font bytes as
    #     16px — while the patched (default-8x16) renderer draws them 8px. That mismatch is the
    #     whole "text sits left" bug: the eqlen box is sized for 16px glyphs, the text renders 8px.
    #   * Rendered text starts at box_left + 12; box width = rendered-glyph pixels + 22.
    #   With every glyph behind an EXPLICIT font switch, calculator and renderer agree, and the
    #   text-centre offset from box centre is  8*lead16 - 4*trail8 - 7  px (independent of body):
    #     content = 0x04 + lead16*space(16px) + 0x03 + body(8px) + trail8*space(8px) + 0x04 0x20.
    #   Pick trail8 = 2*lead16 - 2 (=> offset +1px), and lead16 to reproduce the ORIGINAL JP box
    #   width (16px per original content glyph-byte): lead16 = (2*(NNN_jp - 2) - body) / 4.
    lead16 = max(0, (2 * (nnn - 2) - len(body)) // 4)
    trail8 = max(0, 2 * lead16 - 2)
    new_seg = (bytes([FONT_16X16]) + bytes([0x20]) * lead16 + bytes([FONT_8X16]) + body
               + bytes([0x20]) * trail8 + bytes([FONT_16X16, 0x20]))
    if (len(new_seg) - (b - name_start)) & 1:
        # Keep the growth DELTA even. Piece length, NNN parity and the post-box command's word
        # alignment (at 2 + NNN) all shift by delta, and the vanilla tail conventions differ per
        # MDT (E80C `07 07 f0 00`, E800 `07 00 f0 00`, ...), so the only universally safe rule is
        # to preserve whatever parity the original piece had. An odd delta makes odd-length pieces
        # (room-load crash under the halved --widen OFS: pA_ban1 23B c000 -> black screen) or lands
        # the post-box byte at an ODD offset (audit: 30/45 banners under the earlier NNN-even rule).
        new_seg += bytes([FONT_16X16])   # zero-width filler (repeated font switch, renders nothing)
    delta = len(new_seg) - (b - name_start)
    nnn2 = nnn + delta
    if nnn2 > 0x0FFF:
        return data
    out = bytearray(data[:name_start] + new_seg + data[b:])
    out[0] = 0x20 | (nnn2 >> 8)
    out[1] = nnn2 & 0xFF
    return bytes(out)


def substitute_piece_runs(data: bytes, run_map: dict, font: str = "16x16") -> bytes:
    """Replace named text runs (RUN_TEXTS) EQUAL-LENGTH (preserves total length + box size -> safe
    in place, the proven 010 recipe). English longer than the box budget is truncated to fit.

    font="16x16" (default for NAME banners): encode in the DEFAULT font's page-0 uppercase Latin
    (no 0x03 switch), padded with spaces. Required because the location/door/save name banners
    render in the 16x16 font and IGNORE the 0x03 8x16 switch — 8x16 ASCII there shows as kana
    garbage (e.g. "Hall" -> "いそとと"). font="8x16" keeps the 0x03 + ASCII (mixed-case) form for
    contexts that honor the switch (in-dialogue text)."""
    out = bytearray(data)
    for ri, a, b in list(iter_text_runs(data)):
        if ri not in run_map:
            continue
        orig = data[a:b]
        # BANNER name pieces (location c000/e001 + door d0xx) are `0x2NNN` box-render commands. Two
        # things must be PRESERVED or the box draws a PINK/uninitialized background, and we must emit NO
        # 0x03 (it flips the box palette -> pink, and its padding draws a stray glyph after the name):
        #   * c000/e001: the box command sits at the very start of the run (box cmd directly + name) ->
        #     keep the 2-byte `0x2NNN`.
        #   * d0xx: a `0a 00 c0` window-setup precedes the name; the name run starts with the `0xc0`
        #     WINDOW-COLOR byte (the box command is its own earlier run, already preserved) -> keep 0xc0.
        # Then render page-0 English terminated by 0x07, zero-padded to the run length. Verified by
        # WRAM-injecting E800 d001 (ARCHIVES): keep-0xc0 + no-0x03 = clean; dropping 0xc0 = pink again
        # (work/jinloop/arch candA vs candB).
        prefix = b""
        if font == "16x16":
            if a == 0 and (data[0] >> 4) == 2:
                prefix = orig[:2]               # 0x2NNN box command (c000/e001)
            elif orig[:1] == b"\xc0":
                prefix = orig[:1]               # 0xc0 window-color setup (d0xx)
        if prefix:
            import os
            name = orig[len(prefix):]
            avail = max(0, len(name) - 1)   # bytes for the name (reserve 1 for the 0x07 terminator)
            if os.environ.get("GDM_8X16"):
                # 8x16-default disc (SCNRL font patch): the banner reads bytes as ASCII, so render the
                # full sublocation MIXED-CASE directly (8x16 has lowercase + apostrophe). Full-length fits
                # because 8x16 is half-width. See docs/grandia1-scnrl-fontbox-patches.md.
                full_name = run_map[ri]
                sub = full_name.split(": ", 1)[1] if ": " in full_name else full_name
                # Reserve 3 trailing bytes for a COMMIT-SPACE (FONT_16X16 + space) before the 0x07
                # terminator, so the 0x07 runs in 16x16 instead of drawing a pink control-glyph tile in
                # 8x16 (same mechanism as the dialogue line-end fix).
                body = _enc(sub)[:max(0, len(name) - 3)]
                # CENTER the half-width 8x16 name in the box (the box frame is sized for the original,
                # wider JP name, so left-aligned English sits in the left half). The original JP filled
                # `_run_glyphs(name)` glyphs at ~16px each; the English body is `len(body)` chars at
                # ~8px. Pad the front with 8x16 spaces (8px each) to shift the body to the box centre:
                # lead ≈ (jp_pixels - body_pixels) / 2 / 8 = jp_glyphs - body/2, clamped to the byte
                # budget left after body + the 3-byte commit/terminator. Trailing budget is zero-padded
                # (past the 0x07, not drawn).
                pad_budget = max(0, len(name) - len(body) - 3)
                lead = max(0, min(pad_budget, _run_glyphs(name) - len(body) // 2))
                rep = (prefix + bytes([0x20]) * lead + body + bytes([FONT_16X16, 0x20, END])
                       + bytes(pad_budget - lead))
            else:
                body = encode_16x16_page0(best_fit_name(run_map[ri], _run_glyphs(name)))[:avail]
                rep = prefix + body + bytes([END]) + bytes(len(name) - 1 - len(body))
            assert len(rep) == len(orig), f"run {ri}: {len(rep)} != {len(orig)}"
            out[a:b] = rep
            continue
        budget = _run_glyphs(orig)
        text = best_fit_name(run_map[ri], budget)
        if font == "16x16":
            # Mirror the stable 8x16 structure EXACTLY (leading 0x03 + body + 0x03 padding), but
            # fill the body with 16x16 page-0 codes. The leading 0x03 is what the stable 039 build
            # had; a run that starts with a raw text byte misparses (the banner dropped the first
            # chars -> "ARY" -> crash). The banner ignores the 0x03 for font (renders body in the
            # default 16x16), so page-0 letters show as correct uppercase. 0x03 padding (not space)
            # keeps box width to just the visible letters.
            cap = max(0, min(budget, len(orig) - 1))
            body = encode_16x16_page0(text)[:cap]
            rep = bytes([FONT_8X16]) + body + bytes([FONT_8X16]) * (len(orig) - 1 - len(body))
        else:
            rep = WordFlow(text).fill(len(orig), glyph_cap=budget)
        assert len(rep) == len(orig), f"run {ri}: {len(rep)} != {len(orig)}"
        out[a:b] = rep
    return bytes(out)


def substitute_piece_runs_grow(data: bytes, run_map: dict) -> bytes:
    """Replace named text runs (RUN_TEXTS) with English, GROWING the piece as needed.

    Each replaced run becomes `0x03` (8x16 ASCII font) + English; every other byte (controls,
    portrait codes, untouched/bytecode runs) is copied verbatim. The reconstructor recomputes all
    pointers, so growth is safe structurally; the bigger file must then be relocated.
    """
    out = bytearray()
    pos = 0
    for ri, a, b in iter_text_runs(data):
        if ri in run_map:
            out += data[pos:a]
            out += bytes([FONT_8X16]) + run_map[ri].encode("ascii", "replace")
            pos = b
    out += data[pos:]
    return bytes(out)


def substitute_piece_perseg_grow(data: bytes, seg_map: dict, wrap=18, min_glyphs=4) -> bytes:
    """Per-segment translation that GROWS segments to fit full English (needs relocation after)."""
    out = bytearray()
    pos = 0
    for idx, _posb, a, b in iter_segments(data):
        out += data[pos:a]
        out += _grow_segment(data[a:b], seg_map.get(idx), wrap, min_glyphs)
        pos = b
    out += data[pos:]
    return bytes(out)


def has_inter_segment_bytecode(data: bytes) -> bool:
    """True if the piece has EVENT bytecode (a text run, not a portrait/control) BETWEEN two
    portrait-delimited dialogue segments. Such pieces contain mid-conversation flow/event ops whose
    targets break when the script grows (the box-render loops / draws garbage — output/052..058,
    the `50 01 00 19f0…` op in E80C 500a). These must be translated EQUAL-LENGTH (no shift), not
    grown/paginated. Simple pieces (portrait box -> 0x07 -> next portrait box) grow safely."""
    segs = list(iter_segments(data))
    for k in range(len(segs) - 1):
        b = segs[k][3]          # end of this segment
        na = segs[k + 1][2]     # start of next segment
        gap = data[b:na]
        i = 0
        while i < len(gap):
            if _is_portrait(gap, i):
                i += 6
            elif gap[i] <= 0x0F:
                i += 1
            else:
                return True      # a real text/data run sits between segments -> event bytecode
    return False


def substitute_piece_perseg_paginate(data: bytes, seg_map: dict, wrap=22, seg_lines=3) -> bytes:
    """Translate dialogue segments with the 016 PAGINATION recipe: replace a segment's text with the
    full English wrapped to `wrap` chars, split into screens of <=seg_lines lines, each screen a fresh
    8x16 box. Screens are separated by `0x02` + the segment's OWN 6-byte portrait code (so the correct
    speaker stays on screen — not the fabricated Liete break that misfired in old attempts). This
    GROWS the piece; build_one injects in place while it still fits the sector span.

    Each screen = `0x03`+line joined by `0x01` (newline). A trailing `0x07` (box terminator) is kept.
    """
    out = bytearray()
    pos = 0
    for idx, posb, a, b in iter_segments(data):
        out += data[pos:a]
        seg = data[a:b]
        eng = seg_map.get(idx)
        if not eng:
            out += seg
        else:
            portrait = seg[:6]
            # Preserve the segment's trailing CONTROL suffix (0x02 new-box / 0x0e pause / 0x07 end /
            # 0x01) verbatim — it's what separates this conversation box from the next. Dropping it
            # merges segments into one overflowing box (output/054).
            t = len(seg)
            while t > 6 and seg[t - 1] <= 0x0F:
                t -= 1
            trailing = seg[t:]
            lines = _wrap(eng, wrap) or [""]
            screens = [lines[i:i + seg_lines] for i in range(0, len(lines), seg_lines)]
            rebuilt = bytearray()
            # In 8x16 mode (after 0x03) the control bytes 0x01/0x02/0x07 also DRAW a font glyph (the
            # stray \ / ) at line ends). So switch back to 16x16 (0x04) before EVERY control and 0x03
            # before each text line: controls run clean in 16x16, text draws in 8x16.
            # PINK-TILE FIX: the magenta tile at line ends was the control byte (0x01 newline / 0x02 /
            # 0x07) drawn as a GLYPH in 8x16 mode. The font switch (0x04) only COMMITS at the next TEXT
            # glyph (>=0x10), so a control right after the switch is still drawn in 8x16. We insert a
            # 16x16 SPACE (0x20) after the switch to COMMIT it before the control runs — the space lands
            # at a line/box end so it's invisible, and the control then renders clean in 16x16. Verified
            # via WRAM-inject on E810 (work/jinloop/e810_v20s: full English, no magenta). The leading
            # text 0x03 then re-selects 8x16. See docs/event-op-desync-fix.md / step3-followups OPEN-2.
            COMMIT = bytes([FONT_16X16, 0x20])   # switch to 16x16 + a space to commit the switch
            for si, screen in enumerate(screens):
                if si:
                    rebuilt += COMMIT + bytes([0x02]) + portrait      # commit, new-box, portrait
                else:
                    rebuilt += portrait
                for li, ln in enumerate(screen):
                    if li:
                        rebuilt += COMMIT + bytes([0x01])             # commit, then clean newline
                    rebuilt += bytes([FONT_8X16]) + _enc(ln)          # 8x16 text
            rebuilt += COMMIT + trailing                              # commit before 0x07/0x02
            out += rebuilt
        pos = b
    out += data[pos:]
    return bytes(out)


def parse_box_commands(data: bytes):
    """Linear top-level parse of a piece's INTERPRETER command stream (see work/scnrl/vm_notes.md).
    The engine reads 16-bit command words and dispatches on the top nibble; nibble 2 = "render a
    dialogue box of NNN inline content bytes" (`0x2NNN`), where the NNN content is the byte-encoded
    text (portraits + chars) the box renderer walks. Every other command is a plain 2-byte word.

    Returns a list of tokens: ('cmd', <2 bytes>) or ('box', <content bytes>). Verified clean on the
    original E80C 500a (two boxes, 0x20A4 over segs0-7 and 0x205C over segs8-9, ending exactly at
    the piece length)."""
    toks = []
    pos = 0
    while pos + 1 < len(data):
        w = (data[pos] << 8) | data[pos + 1]
        if (w >> 12) == 2:
            nnn = w & 0x0FFF
            toks.append(("box", data[pos + 2:pos + 2 + nnn]))
            pos += 2 + nnn
        else:
            toks.append(("cmd", data[pos:pos + 2]))
            pos += 2
    if pos < len(data):
        toks.append(("cmd", data[pos:]))
    return toks


def has_box_commands(data: bytes) -> bool:
    """True if the piece parses cleanly as an interpreter command stream with >=1 box command that
    starts with a portrait — i.e. growth must rewrite box-length words (use the box-aware paginate)."""
    pos = 0
    boxes = 0
    while pos + 1 < len(data):
        w = (data[pos] << 8) | data[pos + 1]
        if (w >> 12) == 2:
            nnn = w & 0x0FFF
            if pos + 2 < len(data) and data[pos + 2] == 0x0F:
                boxes += 1
            pos += 2 + nnn
        else:
            pos += 2
    return pos == len(data) and boxes > 0


def is_text_box_stream(data: bytes) -> bool:
    """True if the piece parses cleanly end-to-end as an interpreter command stream with >=1 `0x2NNN`
    box command (whether or not the box content starts with a portrait). These are the event-bytecode
    text-run pieces (E814 prize/title/menu screens, the museum terminal/info screens) where the flat
    iter_text_runs glues the box command onto the first line — substitute_piece_runs garbles them, so
    route through substitute_piece_boxruns instead. (has_box_commands requires a 0x0F portrait start,
    which these text screens don't have, so it returns False for them.)"""
    pos = 0
    boxes = 0
    while pos + 1 < len(data):
        w = (data[pos] << 8) | data[pos + 1]
        if (w >> 12) == 2:
            boxes += 1
            pos += 2 + (w & 0x0FFF)
        else:
            pos += 2
    return pos == len(data) and boxes > 0


def substitute_piece_boxes_merge(data: bytes, seg_map: dict, wrap=30, seg_lines=3) -> bytes:
    """For pieces with a mid-conversation EVENT OP between two dialogue boxes
    (has_inter_segment_bytecode, e.g. E80C 500a's `50 01 00 19 f0 00`).

    Such pieces corrupt when the boxes GROW: the box renderer and the event interpreter use separate
    pointers, and once box1 grows the renderer starts box2 at the op's address — so the op bytes draw
    as a garbage box (`つそたで9`) and the convo loops. Diagnosed via the YMIR harness + SH-2 trace
    (dispatch loop 0x0601E5C4, op handler 0x0601E9F2; see memory jin-loop-harness).

    FIX: collapse ALL of the piece's dialogue boxes into ONE box command (so there is no box->box
    handoff for the op to corrupt), paginating every segment to full English. The inter-box command
    bytes (the event op, which just sets a story flag) are moved to AFTER the merged box so their
    effect is preserved. Validated full-English + no-junk via the harness (work/jinloop/merge)."""
    grown = substitute_piece_boxes_paginate(data, seg_map, wrap=wrap, seg_lines=seg_lines)
    toks = parse_box_commands(grown)
    box_pos = [i for i, (k, _) in enumerate(toks) if k == "box"]
    if len(box_pos) < 2:
        return grown  # nothing to merge
    head = b"".join(p for k, p in toks[:box_pos[0]])
    tail = b"".join(p for k, p in toks[box_pos[-1] + 1:])
    inter = b"".join(p for i, (k, p) in enumerate(toks)
                     if box_pos[0] < i < box_pos[-1] and k != "box")  # the event op(s)
    boxes = [p for k, p in toks if k == "box"]
    merged = bytearray()
    for bi, bc in enumerate(boxes):
        c = bytearray(bc)
        if bi > 0:
            merged += bytes([FONT_16X16, 0x02])     # 16x16 + new-screen before the next box's content
        if bi < len(boxes) - 1 and c and c[-1] == END:
            c = c[:-1]                              # drop intermediate box terminators; keep the last
        merged += c
    nnn = len(merged)
    if nnn > 0x0FFF:
        raise ValueError(f"merged box content {nnn}B exceeds 0x0FFF; tighten --wrap")
    boxword = bytes([0x20 | (nnn >> 8), nnn & 0xFF])
    # op moved AFTER the merged box (sets its flag once the conversation has been shown)
    return head + boxword + bytes(merged) + inter + tail


def substitute_piece_boxes_paginate(data: bytes, seg_map: dict, wrap=30, seg_lines=3) -> bytes:
    """GROW dialogue with full English while keeping the engine's box-advance correct.

    A dialogue box is the interpreter command `0x2NNN` followed by NNN inline content bytes (a whole
    conversation block = one or more portrait-delimited screens). The interpreter advances its script
    pointer by NNN to reach the next command (SCNRL 0x0601E86E); the box renderer pages through the
    NNN content bytes. The plain pagination path grew the content but left NNN stale, so the engine
    advanced too few bytes and the next box started MID-TEXT (Sue's line repeating, garbage boxes —
    see work/scnrl/vm_notes.md). This version paginates the content INSIDE each box command and
    rewrites NNN to the new content length, so the advance stays correct.

    seg_map is keyed by GLOBAL segment index (as iter_segments numbers the whole piece). Segments only
    appear inside box content, so a running counter maps them to the per-box local indices.

    0x3NNN handling is SPAN-BASED. A 0x3NNN word is a conditional-block skip-length: when its guard
    fails the interpreter jumps NNN bytes (past the whole `... 1000 3NNN <body> f000` block). Its span
    therefore covers EVERY box inside that block, so NNN must grow by the TOTAL growth of all boxes in
    the span — not just the first box after the word. The old code updated only the first following box
    (resetting after one box), which under-counted multi-box blocks: E800 piece 0 is one 0x3690 routine
    that spans all 13 boxes, so +22 (box 1) was written where +716 (all 13) was needed -> the skip
    landed ~694B early, mid-routine, on re-entry -> intro replay + off-map warp. The single-box E80C
    500a case (one 0x3NNN per box, the next box sits past the span end) is unchanged. See
    docs/event-op-desync-fix.md."""
    out = bytearray()
    gidx = 0
    vpos = 0            # running offset into the ORIGINAL `data` (to test 0x3NNN span coverage)
    open_pre = []       # 0x3NNN skip-length words: {out_pos, orig nnn, vanilla span end, accum grow}
    for kind, payload in parse_box_commands(data):
        if kind == "cmd":
            if len(payload) >= 2 and (payload[0] >> 4) == 3:  # 0x3NNN conditional-block skip-length
                nnn0 = ((payload[0] << 8) | payload[1]) & 0x0FFF
                open_pre.append({"out_pos": len(out), "orig": nnn0,
                                 "end": vpos + 2 + nnn0, "grow": 0})
            out += payload
            vpos += len(payload)
            continue
        content = payload
        local_map = {}
        for lidx, _posb, _a, _b in iter_segments(content):
            if gidx in seg_map:
                local_map[lidx] = seg_map[gidx]
            gidx += 1
        new_content = substitute_piece_perseg_paginate(content, local_map, wrap=wrap, seg_lines=seg_lines)
        # WORD-ALIGNMENT: the engine's command interpreter reads 16-bit command words at EVEN
        # addresses (SH2 mov.w masks bit 0). A box command is `0x2NNN` (2 bytes) + NNN content bytes,
        # so the NEXT command (and any inter-box EVENT OP) is word-aligned only if NNN is EVEN. If a
        # grown box has ODD content, the op lands on an odd byte and is misread (e.g. 0x5001 read as
        # 0x0750) -> wrong dispatch -> garbage box + loop. Pad odd content to even with a trailing
        # byte (after the box terminator, so it never renders). (Diagnosed via the YMIR harness:
        # box1 grew +73 odd -> op at 0x2806A3 odd -> engine read 0x0750.)
        if len(new_content) & 1:
            new_content += bytes([FONT_16X16])  # 0x04, benign filler past the box terminator
        nnn = len(new_content)
        if nnn > 0x0FFF:
            raise ValueError(f"grown box content {nnn}B exceeds the 0x0FFF box-length field; "
                             f"split the conversation or tighten --wrap")
        # This box's growth extends EVERY conditional-block skip-length whose span still covers it (a
        # box can nest inside more than one 0x3NNN block -> add the delta to each open span).
        delta = nnn - len(content)
        for pre in open_pre:
            if vpos < pre["end"]:
                pre["grow"] += delta
        out += bytes([0x20 | (nnn >> 8), nnn & 0xFF]) + new_content
        vpos += 2 + len(content)
    # Rewrite each 0x3NNN skip-length by the total box growth within the block it spans (see docstring).
    for pre in open_pre:
        new_nnn = pre["orig"] + pre["grow"]
        if new_nnn > 0x0FFF:
            raise ValueError(f"grown conditional block {new_nnn}B exceeds the 0x0FFF skip-length field; "
                             f"split the conversation or tighten --wrap")
        out[pre["out_pos"]] = 0x30 | (new_nnn >> 8)
        out[pre["out_pos"] + 1] = new_nnn & 0xFF
    return bytes(out)


def _box_run_lines(content: bytes, min_glyphs: int):
    """Walk a box's inline content and yield (start, end, glyphs) for every maximal TEXT run, in
    order (controls/portrait codes skipped, 0x10-0x1F = 2-byte char). A box content has NO 0x2NNN
    box commands (the box command framed it), so unlike iter_text_runs over a whole bytecode piece
    these runs are clean text lines (the >=min_glyphs ones) and 1-glyph bytecode params."""
    i, n = 0, len(content)
    while i < n:
        if _is_portrait(content, i):
            i += 6
        elif content[i] <= 0x0F:
            i += 1
        else:
            j = i
            g = 0
            while j < n and not (content[j] <= 0x0F or _is_portrait(content, j)):
                j += 2 if 0x10 <= content[j] <= 0x1F else 1
                g += 1
            yield i, j, g
            i = j


def _eqlen_line(text: str, budget: int, at_8x16: bool, tight: bool = False):
    """One box content line replaced EQUAL-LENGTH (exactly `budget` bytes): an EXPLICIT `0x03`
    8x16-font switch, ASCII (truncated to fit), space padding, then a `0x04`+space COMMIT so the
    line's trailing control renders in 16x16 (the pink-tile fix). Keeps the box's 0x2NNN length
    unchanged -> no shift -> safe for pieces whose growth would desync a 0x50 event op (the
    minigame title/menu boxes). Returns (bytes, now_at_8x16=False, the commit left 16x16).

    The 0x03 is ALWAYS emitted, even when the box-start/new-box default font would already be 8x16
    (`at_8x16` is ignored for emission): the menu cursor-move DE-HIGHLIGHT redraw re-runs the box
    bytecode with the STALE font state left by the previous render (16x16 after our own `0x04 0x20`
    commits), so a first line that relied on the elided switch re-renders as page-0 16x16 garble —
    the terminal-menu "9 Xそたで 9" bug (`* Back *` read as 16x16 glyphs). One pad byte is the cost.

    tight=True (lane W1; opt-in per run via an MDT's TIGHT_RUN_PIECES): when the full text is
    EXACTLY one byte over the normal body room (budget-3), emit a 1-byte `0x04` commit with no
    trailing space instead of truncating — buys one character (E814 6003 'Feena's Panties',
    15 chars in a 17-byte line). The font restore still happens (0x04); only the cosmetic space
    pad is dropped — render-verify the surface (pink-tile class) when opting a run in."""
    sw = bytes([FONT_8X16])
    if budget - len(sw) < 2:                    # no room for the commit; plain 0x03 + body/pad
        body = _enc(text)[:max(0, budget - 1)]
        return bytes([FONT_8X16]) + body + bytes([FONT_8X16]) * (budget - 1 - len(body)), True
    full = _enc(text)
    if tight and len(full) == budget - len(sw) - 1:
        return sw + full + bytes([FONT_16X16]), False
    body = full[:budget - len(sw) - 2]
    pad = budget - len(sw) - len(body) - 2
    return sw + body + b"\x20" * pad + bytes([FONT_16X16, 0x20]), False


def _rebuild_box_runs(content: bytes, cstart: int, end_to_ri: dict, run_map: dict,
                      min_glyphs: int, grow: bool, tight_keys=frozenset()) -> bytes:
    """Rebuild one box's inline content. Each >=min_glyphs TEXT line whose GLOBAL run index (resolved
    via end_to_ri[absolute end]) is in run_map is replaced with English; controls and short
    bytecode-param runs (and untranslated JP lines) are copied verbatim. grow=True emits `0x03`+full
    ASCII and lets the box change length (caller rewrites 0x2NNN/0x3NNN); grow=False keeps every
    replaced line EQUAL-LENGTH (caller leaves the box length untouched). A `0x04`+space COMMIT is
    inserted before any control following an English line so the control renders in 16x16."""
    COMMIT = bytes([FONT_16X16, 0x20])
    out = bytearray()
    i, n = 0, len(content)
    prev_en = False     # last emitted token was 8x16 English (grow path) -> commit before next control
    at_8x16 = True      # renderer font at box start = the 8x16 default (eqlen path leading-0x03 elision)
    while i < n:
        if _is_portrait(content, i):
            if prev_en:
                out += COMMIT; prev_en = False; at_8x16 = False
            out += content[i:i + 6]; i += 6
        elif content[i] <= 0x0F:
            if prev_en:
                out += COMMIT; prev_en = False; at_8x16 = False
            if content[i] == 0x02:              # new-box resets to the default 8x16 font
                at_8x16 = True
            out += content[i:i + 1]; i += 1
        else:
            j = i
            g = 0
            while j < n and not (content[j] <= 0x0F or _is_portrait(content, j)):
                j += 2 if 0x10 <= content[j] <= 0x1F else 1
                g += 1
            ri = end_to_ri.get(cstart + j)
            if g >= min_glyphs and ri in run_map:
                if grow:
                    out += bytes([FONT_8X16]) + _enc(run_map[ri]); prev_en = True; at_8x16 = True
                else:
                    line, at_8x16 = _eqlen_line(run_map[ri], j - i, at_8x16,
                                                tight=ri in tight_keys)
                    out += line                                 # exact-length, self-committing
            else:                                               # param / untranslated run: verbatim
                if prev_en:
                    out += COMMIT; prev_en = False; at_8x16 = False
                out += content[i:j]
            i = j
    if prev_en:
        out += COMMIT
    return bytes(out)


def substitute_piece_boxruns(data: bytes, run_map: dict, grow_keys=None, min_glyphs=2,
                             tight_keys=frozenset()) -> bytes:
    """Translate a TEXT-RUN box-command piece (E814 piece 0 = Game-Room prize messages; 6001-6008 =
    minigame titles / control-help / giveaway) by replacing the text inside each `0x2NNN` box.

    Why a dedicated path: these are event-bytecode streams that parse_box_commands splits into boxes
    whose content is the displayed text (no portraits — boxes start with text). The flat
    iter_text_runs (which RUN_TEXTS keys index) GLUES the box-setup bytecode + the `0x2NNN` box
    command onto each box's first line, so substitute_piece_runs clobbers the box command -> garble.
    Here we operate per box: rewrite only the inline content, recompute `0x2NNN`, and (when growing)
    grow every `0x3NNN` conditional-skip word that spans the box so the interpreter still skips the
    right distance (the docs/event-op-desync-fix.md discipline). Runs map to lines by GLOBAL index
    (end_to_ri), so partially-translated pieces work (only run1 of a title piece is in run_map; its
    JP menu/description lines are copied verbatim).

    grow_keys: per-box GROW gating. A box GROWS only if all its mapped runs are in grow_keys (None =
    grow everything). Boxes with any non-growable mapped run are kept EQUAL-LENGTH (box size, and
    thus every following command's address, unchanged) — required for the title boxes 6001-6007,
    whose growth would desync the 0x50 event op that follows them (freeze, the step3-box-overflow
    class). grow_keys="auto" = grow a box iff it is SAFE: no `0x05` menu marker in its content (so we
    never grow an interactive menu) AND no `0x50` event op anywhere after it in the piece (so growth
    can't desync an absolute event-op target) — used by apply_en's blanket museum-screen routing so
    descriptions/inscriptions grow to full English while menus + op-guarded boxes stay equal-length.
    GDM_8X16 only — emits `0x03`+ASCII, correct under the 8x16-default font.

    Word-aligns each grown box to an even length (the interpreter reads 16-bit command words at even
    addresses); original boxes are already even, so equal-length boxes stay even untouched."""
    end_to_ri = {b: ri for ri, _a, b in iter_text_runs(data)}
    op_positions = []   # 0x50 event-op offsets (for grow_keys="auto" safety: never grow before one)
    if grow_keys == "auto":
        pos = 0
        for kind, payload in parse_box_commands(data):
            if kind == "box":
                pos += 2 + len(payload)
            else:
                if len(payload) >= 2 and payload[0] == 0x50:
                    op_positions.append(pos)
                pos += len(payload)
    out = bytearray()
    vpos = 0
    open_pre = []       # 0x3NNN skip-length words: {out_pos, orig nnn, vanilla span end, accum grow}
    for kind, payload in parse_box_commands(data):
        if kind == "cmd":
            if len(payload) >= 2 and (payload[0] >> 4) == 3:    # 0x3NNN conditional-block skip-length
                nnn0 = ((payload[0] << 8) | payload[1]) & 0x0FFF
                open_pre.append({"out_pos": len(out), "orig": nnn0,
                                 "end": vpos + 2 + nnn0, "grow": 0})
            out += payload
            vpos += len(payload)
            continue
        content = payload
        cstart = vpos + 2
        box_keys = [end_to_ri.get(cstart + j)
                    for _i, j, g in _box_run_lines(content, min_glyphs)
                    if g >= min_glyphs and end_to_ri.get(cstart + j) in run_map]
        if grow_keys == "auto":
            grow = (0x05 not in content) and not any(o > vpos for o in op_positions)
        else:
            grow = bool(box_keys) and (grow_keys is None or all(k in grow_keys for k in box_keys))
        new_content = _rebuild_box_runs(content, cstart, end_to_ri, run_map, min_glyphs, grow,
                                        tight_keys=tight_keys)
        if len(new_content) & 1:
            new_content += bytes([FONT_16X16])      # word-align past the box terminator (grow only)
        nnn = len(new_content)
        if nnn > 0x0FFF:
            raise ValueError(f"grown box {nnn}B exceeds the 0x0FFF box-length field")
        delta = nnn - len(content)
        for pre in open_pre:
            if vpos < pre["end"]:
                pre["grow"] += delta
        out += bytes([0x20 | (nnn >> 8), nnn & 0xFF]) + new_content
        vpos += 2 + len(content)
    for pre in open_pre:
        new_nnn = pre["orig"] + pre["grow"]
        if new_nnn > 0x0FFF:
            raise ValueError(f"grown conditional block {new_nnn}B exceeds the 0x0FFF skip-length field")
        out[pre["out_pos"]] = 0x30 | (new_nnn >> 8)
        out[pre["out_pos"] + 1] = new_nnn & 0xFF
    return bytes(out)


def substitute_piece_perseg(data: bytes, seg_map: dict, min_glyphs=4, glyph_limit=False) -> bytes:
    """Fill each portrait segment's text runs from seg_map[idx] (a string). Segments not in the
    map keep their original (Japanese) bytes. Lets us translate exactly the segments we've done."""
    out = bytearray(data)
    for idx, pos, a, b in iter_segments(data):
        if idx not in seg_map:
            continue
        flow = WordFlow(seg_map[idx])
        seg = data[a:b]
        # rebuild segment: keep portrait code + controls, fill text runs >= min_glyphs
        rebuilt = bytearray(seg[:6])
        for tok in _tokenize_box(seg):  # _tokenize_box skips the first 6 bytes (portrait)
            if tok[0] == "ctrl":
                rebuilt += tok[1]
            else:
                _, run_bytes, glyphs = tok
                if glyphs < min_glyphs:
                    rebuilt += run_bytes
                else:
                    rebuilt += flow.fill(len(run_bytes), glyph_cap=glyphs if glyph_limit else None)
        assert len(rebuilt) == len(seg)
        out[a:b] = rebuilt
    return bytes(out)


def substitute_piece_perbox(data: bytes, box_texts, start_variants=PORTRAIT_POS,
                            glyph_limit=False, min_glyphs=4) -> bytes:
    """Like substitute_piece but each portrait-started box gets its own English string from
    `box_texts` (list indexed by box order), so translations match their speaker."""
    out = bytearray()
    i = 0
    bn = 0
    while i < len(data):
        if _is_portrait(data, i) and data[i + 1] in start_variants:
            try:
                end = data.index(END, i + 6)
            except ValueError:
                out += data[i:]; break
            box = data[i:end + 1]
            out += box[:6]
            flow = WordFlow(box_texts[bn] if bn < len(box_texts) else "")
            for tok in _tokenize_box(box):
                if tok[0] == "ctrl":
                    out += tok[1]
                else:
                    _, run_bytes, glyphs = tok
                    if glyphs < min_glyphs:
                        out += run_bytes
                    else:
                        out += flow.fill(len(run_bytes), glyph_cap=glyphs if glyph_limit else None)
            bn += 1
            i = end + 1
        else:
            out.append(data[i]); i += 1
    assert len(out) == len(data), f"piece length changed {len(out)} != {len(data)}"
    return bytes(out)


def substitute_piece(data: bytes, text: str, start_variants=PORTRAIT_POS, glyph_limit=True,
                     min_glyphs=1) -> bytes:
    """Replace dialogue text inside portrait-started boxes.

    min_glyphs: only replace text runs with at least this many glyphs; shorter runs (likely
    parameters of multi-byte codes we don't fully model) are left as the original bytes.
    """
    flow = WordFlow(text)
    out = bytearray()
    i = 0
    while i < len(data):
        if _is_portrait(data, i) and data[i + 1] in start_variants:
            try:
                end = data.index(END, i + 6)
            except ValueError:
                out += data[i:]; break
            box = data[i:end + 1]
            out += box[:6]
            for tok in _tokenize_box(box):
                if tok[0] == "ctrl":
                    out += tok[1]
                else:
                    _, run_bytes, glyphs = tok
                    if glyphs < min_glyphs:
                        out += run_bytes  # keep original (probably a parameter, not dialogue)
                    else:
                        out += flow.fill(len(run_bytes), glyph_cap=glyphs if glyph_limit else None)
            i = end + 1
        else:
            out.append(data[i]); i += 1
    assert len(out) == len(data), f"piece length changed {len(out)} != {len(data)}"
    return bytes(out)
