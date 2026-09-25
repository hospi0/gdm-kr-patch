#!/usr/bin/env python3
"""Release-candidate disc builder: one command -> output/rc_NN/Grandia-DM-patched.cue.

Chains the two validated pipelines (see docs/MERGE-coordination.md) for the RC phase:
  1. tools/build_final.py --widen   (dialogue: all /FIELD MDTs full-English + SCNRL offset-widen +
                                     2000 full-English)  -> output/rc_NN-widen/Track1.bin
  2. menus/build_full_disc.py --base (menus/items/battle text onto that track: 5 in-place label
                                     files + 3 relocated grown files)  -> output/rc_NN/

This supersedes the ad-hoc `final-widen` + `merged` names for the RC phase; those still work for
back-compat. The dialogue step now carries the span-based 0x3NNN skip-length fix (src/subst.py), so
E800's intro keeps full prose without the re-entry replay / off-map warp.

  python3 tools/build_rc.py 1        # -> output/rc_01/  (and output/rc_01-widen/)
  python3 tools/build_rc.py 02       # same; NN is zero-padded to 2 digits

output/ is gitignored; each RC is a fresh numbered folder so emulator tests always grab the latest.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*cmd):
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run([str(c) for c in cmd])
    if r.returncode:
        raise SystemExit(f"step failed (exit {r.returncode}): {' '.join(map(str, cmd))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("nn", help="RC number (1 / 01 -> output/rc_01/) or a literal tag (pB_rc -> output/pB_rc/)")
    ap.add_argument("--wrap", type=int, default=30, help="dialogue line-wrap (passed to build_final)")
    ap.add_argument("--no-theater", action="store_true",
                    help="skip step 4 (theater: E804 caption hook + IP detour + English DORAM plates)")
    ap.add_argument("--theater-only", metavar="TRACK1",
                    help="skip steps 1-3 and run only the theater step on an existing merged track "
                         "(copied to output/<tag>/); for iterating the theater integration")
    ap.add_argument("--no-mgame", action="store_true",
                    help="skip step 5 (minigame English title assets, patches/mgame/*.xdelta3)")
    a = ap.parse_args()
    if re.fullmatch(r"\d{1,3}", a.nn):
        tag = f"rc_{int(a.nn):02d}"
    elif re.fullmatch(r"[A-Za-z][\w-]*", a.nn):
        tag = a.nn
    else:
        raise SystemExit(f"NN must be a number or a tag (got {a.nn!r})")
    widen = f"{tag}-widen"

    if a.theater_only:
        import shutil
        outdir = ROOT / f"output/{tag}"
        outdir.mkdir(parents=True, exist_ok=True)
        final_track = outdir / "Track1.bin"
        shutil.copyfile(a.theater_only, final_track)
        src_dir = Path(a.theater_only).parent
        for t2 in (src_dir / "Track2.bin",):
            if t2.exists():
                shutil.copyfile(t2, outdir / "Track2.bin")
        (outdir / "Grandia-DM-patched.cue").write_text(
            'FILE "Track1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
            'FILE "Track2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')
        run(sys.executable, ROOT / "src/theater/rc_integrate.py", "--track", final_track)
        print(f"theater-only build: output/{tag}/")
        return 0

    # 1) dialogue + SCNRL widen + 2000 (carries the E800 0x3NNN fix automatically)
    run(sys.executable, ROOT / "tools/build_final.py", "--widen", "--wrap", a.wrap,
        "--attempt", widen)
    widen_track = ROOT / f"output/{widen}/Track1.bin"
    if not widen_track.exists():
        raise SystemExit(f"expected {widen_track} after step 1")

    # 2) menus/items/battle text merged onto the dialogue track
    run(sys.executable, ROOT / "menus/build_full_disc.py", ROOT / f"output/{tag}", "--base", widen_track)

    # 3) Monster-Encyclopedia: relocate the English DICDT.DAT (names/labels/locales/descriptions)
    #    into the final track. The game rebuilds its file-index table from the ISO dir at cold boot,
    #    so the relocated copy is what loads (see docs/museum-viewers-format.md).
    final_track = ROOT / f"output/{tag}/Track1.bin"
    tmp = final_track.with_name("Track1.bin.dicdt")
    run(sys.executable, ROOT / "tools/build_dicdt.py", "--bin", final_track, "--out", tmp)
    tmp.replace(final_track)

    # 3b) Monster-guide viewer QUIT dialog (lane DLG2, #10): the Start/pause confirm dialog
    #     終了しますか?/はい/いいえ -> QUIT?/YES/NO. It is a 128x48 8bpp VDP1 sprite (char 0x412c0)
    #     stored UNCOMPRESSED as two cursor-state variants in /FIELD/DICDT.DAT at file offset
    #     0x1FAD0 (YES-hl) / 0x212D0 (NO-hl); DICDT loads to LWRAM 0x240000 so they DMA to VDP1.
    #     Content-addressed, size-preserving, in-place (JP art bytes -> English, reusing the design
    #     dialog's exact QUIT?/YES/NO glyph stamps). MUST run AFTER step 3 (patches the relocated
    #     English DICDT). Idempotent; touches only the two 6144-B art regions (DICDT text untouched,
    #     so it composes with build_dicdt + Lane J's monst_text2_fix). See
    #     docs/lanes/laneDLG2-monsterdialog.md.
    run(sys.executable, ROOT / "tools/viewer_quitdlg_monst.py", "fold", final_track)

    # 4) Theater (lane B): English DORAM title plates (in-place) + caption blob piggybacked into
    #    the dialogue-built E804's free tail + IP.BIN 3-zone room-bootstrap detour + English-menu
    #    assert. All layout-derived constants (blob LWRAM base, drama/exit FAD gates) are recomputed
    #    from THIS track, so the step composes with any upstream relocation the dialogue/menus steps
    #    performed. See src/theater/rc_integrate.py + docs/theater-hook.md s14.
    if not a.no_theater:
        run(sys.executable, ROOT / "src/theater/rc_integrate.py", "--track", final_track)

    # 5) Minigames (lane D): the 8 all-English arcade title-screen assets (KNPAN/RFROG/MGSUE/
    #    FI_DT/OBONG/BY100/BARLG/HYABG), shipped as patches/mgame/*.xdelta3 against the vanilla
    #    bytes and folded IN PLACE (size-preserving, no relocation -> composes with step 4's
    #    track-derived constants in any order). See docs/mgame-format.md session 9.
    if not a.no_mgame:
        run(sys.executable, ROOT / "tools/mg_fold_rc.py", "--track", final_track)

    # 5b) Lane W7 (rc_47) — JP-sweep text folds. Both are pattern-gated in-place equal-length
    #     patches (JP bytes -> apply, English -> skip, neither -> error), idempotent:
    #     - pW7_missed_text_fold: 22 MDT strings the Step-2 pipeline missed (portrait-less opening
    #       boxes, item-get popups, door-lock signs) across 2000/D804/E814/EB00-EB14.
    #     - pW7_mgame_text_fold: 42 minigame-INTERNAL strings (game-2 cheer-battle 16x16-tbl
    #       dialogue, game-7 tank-battle JIS-X0201 intro). MUST run after mg_fold_rc (step 5): the
    #       mgame xdelta3 deltas are md5-gated against vanilla bytes, so text patches go on top.
    #     See docs/lanes/laneJP-sweep.md.
    run(sys.executable, ROOT / "tools/pW7_missed_text_fold.py", final_track)
    if not a.no_mgame:
        run(sys.executable, ROOT / "tools/pW7_mgame_text_fold.py", final_track)

    # 6) Museum design-materials viewer (lanes F+K): English tab titles + 96 plate captions in
    #    /FIELD/MTMES.DAT (tbl text, vanilla-size, in place) AND fully-English MTOUT.DAT (category
    #    menu labels + baked banner/selected-bar art via patches/viewer/MTOUT.DAT.xdelta3, md5-gated).
    #    See tools/viewer_mtmes.py + docs/lanes/laneF-viewers.md + docs/lanes/laneK-category.md.
    run(sys.executable, ROOT / "tools/viewer_mtmes.py", "fold", final_track)

    # 6b) Expressions viewer (lane N2): top-left banner キャラクター表情集 -> EXPRESSIONS.
    #    Baked 144x41 8bpp VDP1 plate sprite in /FIELD/FACE0.DAT slot3 (codec func 0x0601A716,
    #    same family as MTOUT/theater); re-encoded English blob shipped as
    #    patches/viewer/FACE0.DAT.xdelta3 (md5-gated, in-place, no oracle). Independent of the
    #    FACE2 nameplate/pause-dialog folds. See docs/lanes/laneN2-banner.md.
    run(sys.executable, ROOT / "tools/facer_banner.py", "fold", final_track)

    # 6c) Expressions nameplates (lane N) then the shared viewer EXIT dialog (lane O). ORDER MATTERS:
    #    facer_names rewrites FACE2.DAT slots 0/1 (nameplate name+expression, reproduced from
    #    docs/menus/expressions-en.json); viewer_pausedlg then content-address-patches FACE2's
    #    exit-dialog block (0x3ec8, 終了しますか?/はい/いいえ -> QUIT?/YES/NO) AND /FIELD/DORAM.BIN's
    #    theater-screening exit dialog. facer MUST run first (it regenerates FACE2 with the JP
    #    dialog bytes; the content-addressed pausedlg patch then converts them). See
    #    docs/lanes/laneN-expressions.md + laneO-pausedialogs.md.
    run(sys.executable, ROOT / "tools/facer_names.py", "fold", final_track)
    run(sys.executable, ROOT / "tools/viewer_pausedlg.py", "patch", final_track)
    # 6c-quips) Expressions voice-clip QUIPS (lane QUIP, #27): the 256 comment quips shown on C.
    #    FACE2.DAT slot 3 (records) + slot 2 (offset table). English (16.4 KB) exceeds slot 3's
    #    10.3 KB span and FACE2 is fully packed, so this GROWS slot 3, shifts slots 4-37, fixes the
    #    header, and RELOCATES the file via src/relayout.py (LBA 38453 -> 198358, +6112 B). MUST run
    #    LAST in the FACE2 chain: it reads the CURRENT on-disc FACE2 and preserves slots 0/1
    #    (facer_names nameplates) + the exit-dialog block (viewer_pausedlg) verbatim, so those apply
    #    first. Idempotent; the quip box honours 0x03 half-width. Later steps (7/8) find files by
    #    record name, so they tolerate the relocation. See docs/lanes/laneQUIP-quips.md.
    run(sys.executable, ROOT / "tools/facer_quips.py", "fold", final_track)

    # 7) Title screen (lane G): English start-menu labels (pre-rendered 8bpp sprite bitmaps in
    #    /BIN/TTL.DAT sec 5, ST1 codec) — in-place, size-preserving. Order-independent with 4-6.
    run(sys.executable, ROOT / "tools/title_menu.py", "fold", final_track)

    # 7b) Save-data browser (lane O7): the SVLD/SAVER/CNFIG "Save System RAM" viewer's stat/equip
    #     labels are a shared JIS X0201 half-width table (SVLD.BIN @0xacf8 loads to HWRAM 0x060b2000,
    #     SAVER.BIN @0xf334, CNFIG.BIN @0x94e0). Font = raw 8-bit JIS X0201, NO 0x03 -> equal-length
    #     ASCII replace in place (CMDMN-canonical labels). Size-preserving, byte-gated, idempotent.
    run(sys.executable, ROOT / "tools/save_browser_en.py", "fold", final_track)

    # 7c) Moves/Skills GROWTH screen layout (lane N5): the English spell names (from WDATA sec6, the
    #     N1/N2 field-menu source) were drawn full-length then COVERED by the beige LV box + LV#/
    #     element/SP# widgets painted at fixed tile-x. The per-row drawer in /FIELD/CMDMN.BIN draws
    #     each widget cell at box=r11+9 / number=r11+11 (name anchored at r11=tile 19). This bumps
    #     those 6 relative offsets (+9->+12, +11->+14) so the widget cluster shifts +3 tiles into the
    #     empty right margin (tiles 40-43), widening the name field 9->12 chars. NO text change (so no
    #     battle regression — battle reads BBG sec1, not this overlay). The N2 "Moves LEVEL n" pause
    #     page shares the routine and shifts too, staying in-panel (gains name room). Size-preserving,
    #     byte-gated, idempotent. See docs/lanes/pN5-moves-growth-cutoff.md.
    run(sys.executable, ROOT / "tools/pN5_growth_relayout.py", "fold", final_track)

    # 7d) Monster-book detail STAT-PANEL labels (lane W4 / O5): the page-interior 8bpp tile store
    #     (parchment + ステータス/レベル/... label pixels) sits VERBATIM in /FIELD/DICDT.DAT at file
    #     offset 0xCFA0 (streamed linearly to LWRAM 0x240000 at book-open; NO decompressor — the old
    #     laneM2 "book-open decompressor" wall was a misdiagnosis of the resident CD streamer
    #     0x060044F0). Rewrites the 1748 label-ink bytes (ink 187 / emboss 186, used ONLY by the
    #     labels) to Title-Case English (Status/Level/Endurance/Attack/Defense/Agility/Move/Exp) via
    #     the empirically decoded screen->blob map (patches/viewer/pW4_screenmap.npz). md5-gated
    #     0xF4C0 window, size-preserving, idempotent; composes with the step-3 DICDT encyclopedia
    #     fold (disjoint bytes). Must run after step 3 (finds DICDT.DAT by ISO record). Lane doc:
    #     docs/lanes/laneW4-stats-panel.md; proof docs/lanes/pW4_stats-panel-en-DISC-proof.png.
    run(sys.executable, ROOT / "tools/pW4_monst_stats_fold.py", "fold", final_track)

    # 8) Battle text (lanes Q2/MOV/BAT/BAT2): the live-rendered battle text lives in a 9-section
    #    text item embedded in every /BATLE/*.BBG (loads verbatim to a size-locked LWRAM region) +
    #    per-monster records in /BATLE/M_DAT.BIN. Two size-preserving in-place folds:
    #
    #    a) battle_bbg_repack (lane BAT2, rc_28): ONE unified repack of the BBG text item that
    #       composes ALL four section translations in a single pass, sourcing the extra English
    #       bytes from the truly-INERT sec3+sec6 donor pool instead of sec7:
    #         sec0 = command PANEL (name / "Command input" / verbs)          [was battle_sec0]
    #         sec1 = spell/skill NAME list (Moves screen + battle magic menu) [was moves_sec1]
    #         sec4 = spell/skill DESCRIPTION boxes                            [was battle_skills]
    #         sec5 = in-battle ITEM menu NAMES (NEW — matches field terms.json item names)
    #       CRITICAL FIX: sec7 is the 512-entry item DESCRIPTIONS table (NOT a runtime placeholder
    #       as Lanes Q/BAT assumed). The old separate folds shrank sec7 as their donor, truncating
    #       descriptions for items ~238-511 (Herbs/Panacea/Walnuts/magic-books) in rc_24..rc_27.
    #       The repack keeps sec7 FULL and stubs the inert sec3 (dup spell names) + sec6 (kanji item
    #       names — the menu renders sec5 KANA; sec6 proven unread in battle) to NUL. Item total
    #       length is preserved (size-locked). REPLACES battle_sec0/moves_sec1/battle_skills (those
    #       tools' translate fns are reused verbatim → sec0/1/4 output byte-identical, no regression).
    #       MUST run on vanilla-state BBGs (sec7 full) → it is the ONLY BBG-item step. Idempotent.
    #       See docs/lanes/laneBAT2-battle.md.
    #    b) battle_mdat: enemy NAMES + ATTACK/action names in /BATLE/M_DAT.BIN per-monster records —
    #       the tbl copy (appear/target BANNER + ACTION field, 0x03+ASCII) + adjacent hwkata copy
    #       (status panel). Dictionary-guided: G1 enemy names + 286 G1 attack names (category
    #       "attack" in g1-terms-aligned.json) + DM-original exceptions. Separate file from the BBG.
    #    NB: the top name-plate sprites + Combo/Critical/Defend popups are a pre-rasterised VDP1
    #    sprite atlas cached at the session's first battle; their source (BBG sec0) is English so a
    #    COLD-BOOT playthrough renders them English (mid-game savestates keep the cached JP atlas).
    #    See docs/lanes/laneBAT2-battle.md TASK C.
    run(sys.executable, ROOT / "tools/battle_bbg_repack.py", "fold", final_track)
    #    a2) battle message table (lane N7): the in-battle escape taunts / battle-open / skill-learn /
    #        revival messages (じゃーねーっ バイバーイ …) are sec2 of the SAME 9-section BBG text item
    #        (NOT a separate 0x47a00 block, as the OUTSTANDING premise assumed). The in-battle message
    #        box reads BBG sec2, not the /FIELD/TEXT2.BIN copy (A/B PNG-proven). MUST run AFTER
    #        battle_bbg_repack: it grows sec2 (+273 B) from the sec6 NUL donor that repack leaves,
    #        keeping item/file size locked and sec7 descriptions intact. Wording mirrors the shipped
    #        TEXT2 canon for cross-surface consistency. Idempotent, md5-gated, all 34 BBGs.
    #        See docs/lanes/laneN7-battle-msgtable.md.
    run(sys.executable, ROOT / "tools/pN7_battle_msgtable.py", "fold", final_track)
    #    a3) pO6_item_desc_fold (lane W5, rc_47): in-battle ITEM DESCRIPTIONS (sec7) -> full English
    #        (288/288 real items on the standard BBG; 481 on B005/B006; 137 on BTEST). Grows the BBG
    #        text item G1-style (recompute pointer table) and RELOCATES the grown file (append at
    #        track end + repoint the ISO dir record). MUST run AFTER battle_bbg_repack and
    #        pN7_battle_msgtable (it preserves their sec0..6/sec8 bytes verbatim, only swaps sec7).
    #        rc_40's empty-floor "sibling absolute-address" wall was a misdiagnosis: the breaker was
    #        the grow delta not being a multiple of 4 (misaligned staged siblings -> SH-2 address
    #        errors in the word/long setup copies). Fixed by 4-byte-padding the grown item.
    #        Idempotent (re-run: 34 skipped, +0 sectors). See docs/lanes/laneO6-item-desc.md.
    run(sys.executable, ROOT / "tools/pO6_item_desc_fold.py", "fold", final_track)
    run(sys.executable, ROOT / "tools/battle_mdat.py", "fold", final_track)
    #    c) battle_results_gfx (lane TILEFONT): the POST-BATTLE RESULTS screen text is a baked
    #       VDP2 tile-font (32x8 strips) stored UNCOMPRESSED in /BATLE/ENDW.DAT. Re-authors the
    #       exp line "N EXP gained!" to English (size-preserving, md5-gated). The 報酬/ゴールド/
    #       アイテム labels are DEFERRED (shared/reused strips need a tilemap edit) — see
    #       docs/lanes/laneTILEFONT.md.
    run(sys.executable, ROOT / "tools/battle_results_gfx.py", "fold", final_track)
    #    c2) battle_skillgain_gfx (lane N3): the SECOND post-battle screen (戦闘結果/習得技術)
    #        per-character skill-gain rows are the SAME ENDW.DAT tile-font (a second glyph block
    #        at char*0x20+0x5D4C). Re-authors ぶき/ほのお/みず/かぜ/つち スキル ->
    #        Weapon/Fire/Water/Wind/Earth Skill (size-preserving, md5-gated). The red 戦闘結果/
    #        習得技術 banner is a VDP1 sprite (compressed-atlas wall) -> DEFERRED. See
    #        docs/lanes/laneTILEFONT.md and docs/OUTSTANDING.md (N3).
    run(sys.executable, ROOT / "tools/battle_skillgain_gfx.py", "fold", final_track)
    #    c2b) pW3_endw_style (lane W3, rc_47+ polish): G1-STYLE post-battle presentation.
    #         (i) The red page headers 戦闘結果/習得技術/経験値 (the old c2 DEFER) are VDP1
    #         sprites decoded from a compressed stream INSIDE ENDW.DAT (0x3A48, same codec as
    #         the battle chrome) — transplants the G1 EN fan patch's own stream ("Battle
    #         Result"/"Skills"/"EXP Points", orange-red fill + dark border) and SWAPS the two
    #         page-header display-list elements (DM's page->cell map is reversed vs G1).
    #         (ii) Flips the label cells' tilemap-template words to palette bank 5 so the
    #         c/c2 label glyphs (ink 8) render the exact G1 yellow. Ships WITH c/c2 (shared
    #         ink/bank design). See docs/lanes/laneW3-style-parity.md.
    run(sys.executable, ROOT / "tools/pW3_endw_style.py", "fold", final_track)
    #    c3) pVDF_battlemenu_fold (lane pVDF, rc_39): in-battle SKILL submenu header しゅうとくスキル
    #        -> "Acquired". A VDP2 TILE-FONT label (like c/c2) in its OWN compressed blob (disc
    #        0xEB0674 -> decodes via the pO4 codec to VDP2 VRAM 0x25E03400, dedicated cells char#
    #        0x1b2-0x1b9). Re-encodes with a length-limited package-merge Huffman codelen (the blob's
    #        sparse tree lacks the symbols English needs), written unpadded (ROM stops at the END
    #        token). Disjoint from every other fold (its own blob); size-preserving, byte-gated,
    #        idempotent, deterministic. Validated via inject-oracle + bit-exact disc decode (live
    #        folded-disc render is the documented cold-boot wall — the /BATLE archive is HWRAM-cached
    #        from battle start). Strategy-option + 道具 title labels remain DEFER (VDP1-blit / resident
    #        VDP2 font). See docs/lanes/pVDF_battle-menus.md.
    run(sys.executable, ROOT / "tools/pVDF_battlemenu_fold.py", "fold", final_track)
    #    d) battle_banner_reroute (lane BANNER / O3): the mid-attack ACTION BANNER showed the skill
    #       DESCRIPTION (BBG sec4) instead of its NAME. Reroutes the banner render code in
    #       /BATLE/MGDAT.BIN (2 instruction words: header[3]->header[1]) to read sec1 NAMES. Pairs
    #       with moves_sec1's 0x03-prefixed sec1 names (BBG sec1) so the name renders in ASCII font.
    run(sys.executable, ROOT / "tools/battle_banner_reroute.py", "fold", final_track)
    #    e) pO4_chrome_fold (lane O4/O1): the in-battle CHROME sprite atlas (魔法LV# header + 技
    #       command-ring technique label) is a COMPRESSED VDP1 sprite atlas — the historic wall.
    #       rc_35 cracked the codec end-to-end: a flat 4bpp pixel-nibble stream (delta-coded zero-run
    #       tokens interleaved with canonical-Huffman literal runs; pixels delta-filtered
    #       out=(prev-sym)&0xF). This tool authors 魔法->MAGIC (native 32px multi-cell) + 技->SKL
    #       (native 16px cell) into the atlas, re-encodes with the cracked inverse codec (self-verify
    #       round-trips 28640/28640 bit-exact vs the game's own decoder), and folds the stream in place
    #       at the SYS.IDX /BATLE archive offset (Track1.bin raw 0xEBE910 -> VDP1 VRAM 0x44000).
    #       Size-preserving (16380 <= 16384 B), byte-gated, idempotent, deterministic. Remaining chrome
    #       labels (defend bar / strategy / ring / item title = separate streams) + full "Skill" (needs
    #       a VDP1 CMDSIZE width edit) + the party name-plates (source unlocated; 0xEBDFA4 is the
    #       language-neutral command-icon atlas, NOT plates) are DEFERRED. See docs/lanes/pO4_encoder-cracked.md.
    #       *** STEP RETIRED (lane W2, rc_47): both pO4 cells are superseded — 0x477c0 is authored
    #       Title-Case "Magic" by pO4b (8f), and 技 no longer renders from 0x473a0 at all (the pW2
    #       repack, 8f4, repoints all three 技 geometry triples to the 48x16 "Moves" home @0x4a520
    #       and blanks the old cell). Running pO4 here would re-draw uppercase MAGIC/SKL every build
    #       and oscillate with 8f/8f4, breaking chain idempotency. The module stays as the shared
    #       helper library (write_logical/_put) for the other chrome folds. ***
    # run(sys.executable, ROOT / "tools/pO4_chrome_fold.py", "fold", final_track)   # retired (see above)
    #    f) pO4b_chrome_labels (lane O4/O1, rc_36): the 7 battle command-RING option labels live in the
    #       SAME compressed VDP1 chrome atlas as 魔法/技 (disc 0xEBE910 -> VDP1 VRAM 0x44000), as self-
    #       contained 56x16 cells. Authors コンボ->COMBO, クリティカル->CRITICAL, ぼうぎょ->DEFEND,
    #       みる->LOOK, とうそう->FLEE, さくせん->STRATEGY, どうぐ->ITEM and re-encodes with the cracked
    #       codec. Runs AFTER pO4_chrome_fold (8e): each tool decodes the current stream and edits only
    #       its own cells, so 魔法/技 (8e) and the ring labels (8f) compose; both idempotent + byte-gated
    #       + deterministic. (The strategy-OPTION text + item-panel 道具 title ARE a separate VDP2
    #       tile-font layer -> still DEFERRED; but the DEFEND BAR is NOT VDP2 — it is VDP1 sprites in
    #       THIS same chrome atlas, shipped by pDEF below.) See docs/lanes/pO4b_chrome-labels.md.
    #       *** REORDERED (rc_48 composition, 2026-07-06): pO4b now runs LAST in the chrome chain
    #       (8f5, after pW2). The vanilla atlas stream is already near the 0x4000 hardware budget,
    #       and encoding the ALL-CAPS ring labels (lane X2) against the still-mostly-JP atlas
    #       overflows at every zthresh (min 16411 > 16384). Running pO4b after pDEF/pTOP/pW2 have
    #       replaced the big JP cells keeps every intermediate stage within budget (final stream
    #       14337 B). Order among the four folds is otherwise free — each edits only its own
    #       cells; chain re-verified idempotent + bit-exact in this order. ***
    #    f2) pDEF_defendbar_fold (lane pDEF, rc_37): the in-battle DEFEND BAR (防御実行/防御/回避). RE
    #        finding: it is NOT a VDP2 tile-font (the prior pO4b guess) — it is VDP1 sprites in the SAME
    #        0xEBE910 chrome atlas (cells 0x4a920=防御, 0x4ade0=実行, 0x4aee0=回避 at VDP1 VRAM 0x44000+).
    #        Authors 防御->DEFEND (shared cell, drawn centre + L-box), 実行->"!" (=> L-box "DEFEND!"),
    #        回避->EVADE. Runs AFTER pO4b: decodes the current atlas, preserves 魔法/技 + all ring labels,
    #        draws only the 3 defend cells, re-encodes. Idempotent, byte-gated, deterministic (verified
    #        the 4-fold chrome chain all skip on re-run, encoder round-trips 28640/28640). Canon =
    #        menus/battle_text.py (TrekkiesUnite G1: 防御->Defend, 回避->Evade). See docs/lanes/pDEF_defend-bar.md.
    run(sys.executable, ROOT / "tools/pDEF_defendbar_fold.py", "fold", final_track)
    #    f3) pTOP_chrome_buttons_fold (lane pTOP, rc_42): the in-battle STRATEGY submenu TOP BUTTONS,
    #        also VDP1 sprites in the SAME 0xEBE910 chrome atlas (cells 0x48160/0x48260=作戦設定,
    #        0x489a0=個人, 0x48aa0/0x48ba0=作戦実行 SHARED L+R, 0x48ca0=全体). Authors 作戦設定->"Tactics",
    #        個人->"Single" + 全体->"Party" + the shared 作戦実行 tail->" Tactics" (Title Case, tf font, to
    #        match the shipped row labels + the canonical G1 STRATEGY screen). Runs AFTER pDEF: decodes the
    #        current atlas, preserves 魔法/技 + ring labels + defend bar, draws only the button cells,
    #        re-encodes. Idempotent, byte-gated. Canon recorded in dictionary/exceptions.json. See
    #        docs/lanes/pTOP_strategy-buttons.md + pVDF2_strategy-menu.md.
    run(sys.executable, ROOT / "tools/pTOP_chrome_buttons_fold.py", "fold", final_track)
    #    f4) pW2_atlas_repack (lane W2, rc_47): CHROME-ATLAS REPACK — relocates co-resident cells to
    #        create >=0x180-byte homes and repoints their geometry triples (w6=2*w7, w7=SRCA word,
    #        w8=CMDSIZE) on disc: the 8 strategy VALUE cells shrink 64x16->48x16 and move to
    #        0x180-stride homes (triples @0xEAD42E+0x14*i), freeing 0x4a520..0x4a920. Ships the two
    #        rc_46 width walls: 技 -> "Moves" in a new 48x16 home @0x4a520 (3 table triples
    #        @0xEABC3C/0xEABD78/0xEAC09E; replaces "SKL"), and 防御実行 -> "Endure" (L-box first cell
    #        repointed OFF the shared SCALED centre 0x4a920 to @0x4a6a0, triple @0xEAD522; authored
    #        64px across 0x4a6a0+0x4ade0). MUST run AFTER pDEF/pTOP (pW2 owns the value cells +
    #        0x4ade0 now — those folds no longer touch them, keeping the chain idempotent). Encoder
    #        round-trip bit-exact, size-preserving, geometry+byte-gated. See docs/lanes/laneW2-atlas-repack.md.
    run(sys.executable, ROOT / "tools/pW2_atlas_repack.py", "fold", final_track)
    #    f5) pO4b_chrome_labels (see the 8f comment above — reordered to run last in the chrome
    #        chain so the intermediate stream stays within the 0x4000 budget).
    run(sys.executable, ROOT / "tools/pO4b_chrome_labels_fold.py", "fold", final_track)
    #    g) pO4c_nameplate_fold (lane pO4c, rc_36): party battle NAME-PLATES. A SEPARATE battle-HUD
    #       sprite atlas (NOT the 0xEBE910 chrome atlas): /BATLE/*.BBG raw 0x29bc4 (35 byte-identical
    #       copies) -> one MODE-1 (XOR-filter) decode of 0xFCA0 B to VDP1 VRAM 0x04000. Authors
    #       ジャスティン/スー/フィーナ -> JUSTIN/SUE/FEENA into the name cells (VRAM 0x05950/0x05bc0/
    #       0x05aa0). rc_35's mode-2 encoder can't emit this (mode-2 re-encode overflows the block by
    #       ~2 KB); the codec self-writes its pixel-filter opcode at 0x0601ABFC from a table at
    #       0x0601A9BC (mode 1 = xor r14,r13), so this uses a new mode-1 encoder tools/pO4c_encode_mode1.py
    #       (round-trip 64672/64672 bit-exact). In-place, never grows the 24855 B block (24529 B),
    #       idempotent, deterministic, byte-gated. Disjoint block from the BBG text-item / sec2 folds
    #       (0x12c74 vs 0x4739c) so it composes with 8a/8a2. See docs/lanes/pO4c_nameplate-DONE.md.
    run(sys.executable, ROOT / "tools/pO4c_nameplate_fold.py", "fold", final_track)

    cue = ROOT / f"output/{tag}/Grandia-DM-patched.cue"
    print("\n" + "=" * 64)
    print(f"RC built: {cue}")
    print(f"  dialogue+widen : output/{widen}/")
    print(f"  merged (menus) : output/{tag}/")
    if not a.no_theater:
        print(f"  theater        : plates + captions + IP hook (rc_integrate)")
    print("  verify offline : python3 tools/jinloop.py --attempt", tag, "--no-build   (intro render)")
    print("  GUI gate (user): load in YMIR, watch intro, LEAVE+RE-ENTER hall -> no replay, on-map")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
