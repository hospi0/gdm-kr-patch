#!/usr/bin/env python3
"""Lane-B theater integration: fold ALL theater deliverables into one merged RC track, in place.

Given a merged RC Track1.bin (dialogue + menus + DICDT already applied), this adds:

  (a) E804 theater menu VERIFICATION: the dialogue step (build_final --widen, GDM_8X16 default)
      already produces the English 600a menu ("** Back ** / ** Listen: Drama ** / ** Theater
      Guide **") and grows the guide-description box to full English via the boxruns auto-route
      (the rc_15..rc_21 garble was rc_20 having been built WITHOUT GDM_8X16 -> page-0 codes).
      The dialogue-built E804 (English Pakon dialogue + banners + menu, relocated to a high LBA)
      is KEPT AS-IS; this step asserts the menu strings are really on the track (fail-fast if the
      pipeline regresses to page-0 again).

  (b) The caption HOOK: the relocatable caption blob (2x font + FAD-synced drama-1 table) written
      IN-PLACE into the RC E804's CPU-loaded free zero run (the vanilla 0x1CA14 run, shifted by
      the SCN growth to ~0x1D214 -> LWRAM ~0x29D214; found generically via the MDT header's
      end-of-data/window fields), plus the IP.BIN room-entry bootstrap: 0x2394 CD-stream redirect
      -> the 92 B 3-ZONE gate in the stable IP prefix (hook_loader.ROOM_BOOTSTRAP3_SRC: install
      ONLY on drama-stream FADs when the blob sentinel is resident; uninstall on relocated-zone
      FADs = the E800 reload that clobbers the blob at theater exit; everything else neutral —
      the in-room BGM stream can no longer race a reinstall against the exit clobber).

  (c) The English drama-title PLATES: DORAM.DAT's slot-8 [6] block re-encoded with the English
      plates (gfx_ship.build_doram_bytes, hard round-trip gate), injected IN PLACE at the vanilla
      DORAM LBA (fits: English DORAM is smaller) so DORAM reads stay in the hook's NEUTRAL zone
      and stale-index savestates still stream the English plates.

Usage:
    python3 src/theater/rc_integrate.py --track output/pB_rc/Track1.bin

Idempotent-ish: operates on the track file in place (Track1.bin), rewriting E804's free run + IP +
DORAM. Called automatically as step 4 of tools/build_rc.py (unless --no-theater).

CAPTION CAPACITY (lane E): the blob now carries the FULL 5-drama table (~15.5 KB, 366 records =
all 299 translated lines, 4-row pages with time-split pagination — no truncation). It no longer
fits the ~1.5 KB free tail, so this step GROWS E804's CPU-load window: insert N zero sectors at
the window boundary (file A*2048) and bump the header sector counts 0x180/0x1F4 by N (the
header-driven window was proven live by the dialogue build's +1-sector SCN growth; a vanilla-vs-RC
header diff shows 0x180/0x1F4 are the ONLY sector-tracking fields — 0x184 = footer sector count is
unchanged and every other delta is an in-window byte offset, which a boundary insert does not
shift). The grown E804 is then RELOCATED to the end of the track (relayout.relocate_and_grow:
appended sectors + dir record + PVD), exactly like the pipeline already relocates DICDT etc.
LWRAM safety: the grown window ends well below 0x2D8000 = 0x280000 + E800's own 176-sector CPU
window, which every hall entry clobbers — nothing persistent can live there (and the region above
E804's old window is byte-identical across walk-in/menu/drama dumps = stale hall data).
"""
from __future__ import annotations
import argparse
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "theater"))
sys.path.insert(0, str(ROOT / "script"))

import iso            # noqa: E402
import inject as inject_mod  # noqa: E402
import relayout       # noqa: E402
import build_mdt      # noqa: E402
import hook_build as HB          # noqa: E402
import hook_loader as HL         # noqa: E402
import gfx_ship       # noqa: E402

VANILLA_T1 = ROOT / "input/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin"
GFX001 = ROOT / "output/gfx_001/Track1.bin"


# --------------------------------------------------------------------------------------------
RAW, USER, SYNC = 2352, 2048, 16


def extract_from_track(track: Path, rec: dict) -> bytes:
    """Read a file's bytes from a MODE1/2352 track given its dir record."""
    out = bytearray()
    with open(track, "rb") as f:
        for s in range((rec["size"] + USER - 1) // USER):
            f.seek((rec["lba"] + s) * RAW + SYNC)
            out += f.read(USER)
    return bytes(out[:rec["size"]])


def write_into_file_on_track(track: Path, lba: int, file_off: int, data: bytes) -> None:
    """Overwrite `data` at byte offset `file_off` inside the file starting at `lba` (sector-aware)."""
    with open(track, "r+b") as f:
        i = 0
        while i < len(data):
            sector, within = divmod(file_off + i, USER)
            n = min(USER - within, len(data) - i)
            f.seek((lba + sector) * RAW + SYNC + within)
            f.write(data[i:i + n])
            i += n


def find_blob_run(mdt: bytes, need: int, cpu_window: int, end_of_data: int) -> int:
    """Return the blob home: the FREE TAIL of the CPU-loaded window, i.e. [end_of_data, cpu_window)
    (the MDT header's 0x1F8 end-of-data .. the 0x180 sector-count boundary). ONLY this region is
    safe: zero bytes elsewhere in the window are real SCN/bytecode content, so no generic scanning.
    Accepts the region if it is all-zero (fresh build) or already starts with a previously written
    blob (idempotent re-run: any 4-byte LWRAM pointer into the region = the address-as-sentinel)."""
    off = (end_of_data + 3) & ~3
    if off + need > cpu_window:
        raise SystemExit(f"E804 free tail [{end_of_data:#x},{cpu_window:#x}) too small for {need} B blob")
    region = mdt[off:off + need]
    resident_sentinel = struct.unpack(">I", region[:4])[0] if len(region) >= 4 else 0
    lwram = HL.E804_LOAD + off
    if all(b == 0 for b in region) or lwram < resident_sentinel < lwram + need:
        return off
    raise SystemExit(f"E804 free tail at {off:#x} is neither zero nor a previous blob "
                     f"(starts {region[:8].hex()}) — refusing to overwrite")


def integrate_e804_and_hook(track: Path, work: Path) -> dict:
    """(a) English equal-length E804 injected at the vanilla LBA + record repointed;
       (b) caption blob piggybacked in E804's free run + IP room bootstrap patched."""
    # Take the DIALOGUE-BUILT E804 from the track as-is (English Pakon dialogue + banners + menu;
    # relocated by the widen build). Item-(a) gate: the English menu labels must be on the track.
    with open(track, "rb") as f:
        rec = iso.find_record(f, "E804.MDT")
    mdt = extract_from_track(track, rec)
    # Label needles track script/E804_en.py's 600a wording (single-* decoration since the
    # Lane C in-budget rewording: "* Back * / * Listen to Drama * / * Theater Guide *").
    for needle in (b"* Back *", b"Listen", b"Theater Guide"):
        if needle not in mdt:
            raise SystemExit(
                f"E804 menu gate FAILED: {needle!r} not in the track's E804. The dialogue step "
                "likely ran without GDM_8X16 (page-0 garble, the rc_20 regression) — rebuild with "
                "the current tools/build_final.py (--widen defaults the 8x16 text paths on).")
    print(f"E804 menu gate: English 600a labels present (E804 @ LBA {rec['lba']}, "
          f"FAD {rec['lba'] + 150:#x}, {len(mdt)} B)")

    # E804 CPU-load window = header entry 0x180 sector count * 2048 (the linearly-LWRAM-loaded prefix)
    cpu_window = struct.unpack(">I", mdt[0x180:0x184])[0] * 2048
    end_of_data = struct.unpack(">I", mdt[0x1FC:0x200])[0]     # header 0x1F8 entry, 2nd word

    # bake the caption blob for the piggyback home (LWRAM 0x280000 + file offset). The blob magic is
    # its own vhook entry ADDRESS (bootstrap3's address-as-sentinel; see hook_loader). Two-pass: the
    # entry address does not depend on the magic value, so bake once to learn it, then rebake.
    # all_dramas=True (lane E): the FULL 5-drama table; the vhook FAD gate spans drama1..drama5.
    bake = lambda base, magic: HL.bake_blob(blob_base=base, magic=magic, scale2x=True,
                                            fad_offset=HL.FAD_LEAD_SECTORS, all_dramas=True)
    off0 = (end_of_data + 3) & ~3
    blob0, _ = bake(HL.E804_LOAD + off0, 0)

    # --- lane E: grow the CPU window if the free tail can't hold the full-table blob -----------
    grown = 0
    tail = cpu_window - off0
    if tail < len(blob0):
        grown = (len(blob0) - tail + 2047) // 2048
        A = struct.unpack(">I", mdt[0x180:0x184])[0]
        assert A * 2048 == cpu_window
        mdt = mdt[:cpu_window] + b"\x00" * (grown * 2048) + mdt[cpu_window:]
        patched_hdr = bytearray(mdt)
        struct.pack_into(">I", patched_hdr, 0x180, A + grown)   # CPU-window sector count
        struct.pack_into(">I", patched_hdr, 0x1F4, A + grown)   # (mirror; 0x184 footer count stays)
        mdt = bytes(patched_hdr)
        cpu_window += grown * 2048
        new_lwram_end = HL.E804_LOAD + cpu_window
        assert new_lwram_end <= 0x2D8000, f"grown window end {new_lwram_end:#x} beyond E800-clobbered zone"
        print(f"E804 CPU window GROWN +{grown} sectors -> {cpu_window // 2048} "
              f"(0x{cpu_window:x}; LWRAM ..{new_lwram_end:#x}); free tail now {cpu_window - off0} B")

    off = find_blob_run(mdt, len(blob0), cpu_window, end_of_data)
    _, meta1 = bake(HL.E804_LOAD + off, 0)
    blob, meta = bake(HL.E804_LOAD + off, meta1["vhook_entry"])
    assert meta["vhook_entry"] == meta["magic"], "vhook entry moved between magic passes"
    assert len(blob) == len(blob0), "blob length changed between passes"

    # 3-zone FAD gate (see hook_loader.ROOM_BOOTSTRAP3_SRC): install only on drama-stream reads,
    # uninstall on relocated-zone reads (E800 reload = theater exit), everything else (in-room BGM
    # ~0xA2xx, E804 reloads 0x7B17, vanilla files) is NEUTRAL. This kills the exit race: a BGM
    # chunk interleaved with the E800 load can no longer reinstall between the uninstall and the
    # blob-clobbering transfer.
    import hook_caption_table as hct
    drama_lo = min(hct.GM3_LBA + s + hct.FAD_OFFSET for s in hct.DRAMA_START_SEC.values())
    max_drama_fad = max(hct.GM3_LBA + s + hct.FAD_OFFSET for s in hct.DRAMA_END_SEC.values())
    with open(track, "rb") as f:
        e800_fad = iso.find_record(f, "E800.MDT")["lba"] + 150
    if not (max_drama_fad < e800_fad):
        raise SystemExit(f"theater FAD layout unexpected: max_drama {max_drama_fad:#x} !< E800 {e800_fad:#x}")
    exit_thr = (max_drama_fad + e800_fad) // 2
    bootstrap, _ = HL.build_room_bootstrap3(meta, drama_lo=drama_lo, exit_thr=exit_thr)
    print(f"3-zone gate: neutral<{drama_lo:#x} install<{exit_thr:#x} exit>={exit_thr:#x} "
          f"(drama {drama_lo:#x}..{max_drama_fad:#x}, E800 {e800_fad:#x})")

    # write the blob into E804's free tail; if the window grew, the whole grown E804 must be
    # RELOCATED (it no longer fits its span) — appended at the end of the track like DICDT etc.
    patched = bytearray(mdt); patched[off:off + len(blob)] = blob
    if grown:
        tmp_mdt = work / "E804_grown.MDT"
        tmp_mdt.write_bytes(bytes(patched))
        out_tmp = str(track) + ".e804"
        if relayout.relocate_and_grow(str(track), "E804.MDT", str(tmp_mdt), out_tmp) != 0:
            raise SystemExit("E804 relocate_and_grow failed")
        shutil.move(out_tmp, track)
        with open(track, "rb") as f:
            rec = iso.find_record(f, "E804.MDT")
        assert rec["size"] == len(patched), (rec["size"], len(patched))
        e804_fad = rec["lba"] + 150
        # E804's own reloads must not land in the INSTALL zone (EXIT/NEUTRAL are both harmless)
        assert not (drama_lo <= e804_fad < exit_thr), f"relocated E804 FAD {e804_fad:#x} in install zone"
        print(f"E804 grown+relocated -> LBA {rec['lba']} (FAD {e804_fad:#x}, "
              f"{'EXIT' if e804_fad >= exit_thr else 'NEUTRAL'} zone for its own reloads)")
    else:
        write_into_file_on_track(track, rec["lba"], off, blob)
    # keep offline copies for harness iteration (inject blob.bin / rebuild the bootstrap from meta)
    (work / "E804_english_with_blob.MDT").write_bytes(bytes(patched))
    (work / "blob.bin").write_bytes(blob)
    import json
    (work / "blob_meta.json").write_text(json.dumps(
        {**meta, "e804_lba": rec["lba"], "e804_file_off": off, "bootstrap_len": len(bootstrap),
         "drama_lo": drama_lo, "exit_thr": exit_thr, "grown_sectors": grown,
         "cpu_window": cpu_window}, indent=1))

    # patch IP.BIN (system area): 0x2394 redirect -> bootstrap; bootstrap at the stable 96 B prefix
    HB.patch_ip(track, {0x2394: struct.pack(">I", HB.HOOK_ADDR), HB.GAP_FILE: bootstrap})
    tm = meta.get("table_meta", {})
    print(f"caption blob {len(blob)} B @ E804 file {off:#x} (LWRAM {HL.E804_LOAD + off:#x}); "
          f"{meta['table_lines']} caption records ({tm.get('lines', '?')} lines, all 5 dramas, "
          f"per-drama {tm.get('per_drama')}); bootstrap {len(bootstrap)} B; "
          f"CPU window {cpu_window:#x} end-of-data {end_of_data:#x}")
    return {"e804_lba": rec["lba"], "blob_off": off, "blob_len": len(blob),
            "table_lines": meta["table_lines"], "bootstrap_len": len(bootstrap),
            "grown_sectors": grown}


def integrate_plates(track: Path) -> None:
    """(c) English DORAM plates injected IN PLACE at the vanilla DORAM LBA (the English DORAM is
    SMALLER than vanilla, so it fits the original span). In-place (not relocated) on purpose:
      * keeps every DORAM read at its vanilla FAD (0x79xx) = NEUTRAL zone for the caption hook's
        3-zone FAD gate (a relocated DORAM would sit in the EXIT zone and spuriously uninstall);
      * savestates minted on other discs (stale resident file index -> vanilla LBA) still stream
        the ENGLISH plates, keeping the screening menu headlessly testable."""
    # ensure the vanilla DORAM cache exists (gfx_ship reads work/theater/gfx/DORAM.DAT)
    if not gfx_ship.DORAM.exists():
        gfx_ship.DORAM.parent.mkdir(parents=True, exist_ok=True)
        build_mdt.sh(sys.executable, str(ROOT / "src/iso.py"), "extract", str(VANILLA_T1),
                     "DORAM.DAT", str(gfx_ship.DORAM))
    try:
        new_doram = gfx_ship.build_doram_bytes()
    except Exception as ex:
        # fall back to the already-built English DORAM baked into output/gfx_001 (relocated there)
        if not GFX001.exists():
            raise SystemExit(f"plate build failed ({ex}) and no {GFX001} fallback")
        print(f"plate fresh-build unavailable ({ex}); extracting English DORAM from {GFX001}")
        tmp = gfx_ship.DORAM.parent / "DORAM_english_from_gfx001.DAT"
        build_mdt.sh(sys.executable, str(ROOT / "src/iso.py"), "extract", str(GFX001), "DORAM.DAT", str(tmp))
        new_doram = tmp.read_bytes()
    with open(track, "rb") as f:
        rec = None
        for path, lba, size, rec_raw in iso.walk_records(f):
            if path.upper() == "/FIELD/DORAM.DAT":
                rec = {"lba": lba, "size": size, "rec_raw": rec_raw}
                break
    if rec is None:
        raise SystemExit("/FIELD/DORAM.DAT not found in track")
    if len(new_doram) > rec["size"]:
        raise SystemExit(f"English DORAM {len(new_doram)} B > vanilla span {rec['size']} B; "
                         "in-place injection impossible (fall back to relayout)")
    tmp_dat = track.parent / "DORAM_english.DAT"
    tmp_dat.write_bytes(new_doram)
    out = str(track) + ".doram"
    rc = inject_mod.inject(str(track), str(tmp_dat), rec["lba"], out,
                           max_bytes=rec["size"], allow_overflow=False)
    if rc != 0:
        raise SystemExit("DORAM in-place injection failed")
    shutil.move(out, track)
    with open(track, "r+b") as f:
        relayout._patch_u32_both(f, rec["rec_raw"] + 10, len(new_doram))   # dir data length
    tmp_dat.unlink()
    print(f"DORAM English plates IN PLACE @ LBA {rec['lba']} ({len(new_doram)} B <= {rec['size']} B; "
          f"dir size updated)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track", required=True, help="merged RC Track1.bin (patched in place)")
    ap.add_argument("--no-plates", action="store_true", help="skip the DORAM English-plate step")
    ap.add_argument("--no-hook", action="store_true", help="skip the caption hook + E804 menu step")
    a = ap.parse_args()
    track = Path(a.track)
    if not track.exists():
        raise SystemExit(f"no such track: {track}")
    work = track.parent / "work" / "theater"
    work.mkdir(parents=True, exist_ok=True)

    if not a.no_hook:
        integrate_e804_and_hook(track, work)
    if not a.no_plates:
        integrate_plates(track)
    print(f"theater integration complete -> {track}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
