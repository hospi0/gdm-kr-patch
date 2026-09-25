#!/usr/bin/env python3
"""Minimal CRI ADX (type 3 / standard 4-bit ADPCM) decoder + GM3.STZ drama extractor.

The 5 theater dramas are stored as ADX streams inside /FIELD/GM3.STZ, indexed by /FIELD/GM3.IDX
(4-byte BE entries [tag16][start_sector16], sector offsets into GM3.STZ; the low16 wraps and we carry
it). The 5 dramas are the consecutive long stereo ADX at index 295-299. We decode straight off disk
to WAV so we never touch the emulator and can get ALL FIVE dramas (no ticket/savestate dependency).

  python3 src/theater/adx.py extract <track1.bin> --out work/theater   # all 5 dramas -> WAV
  python3 src/theater/adx.py decode  <file.adx> <out.wav>

WAVs go under work/ (gitignored) — never commit game audio (CLAUDE.md hard-rule #3).
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
import wave
from pathlib import Path

import numpy as np

RAW_SECTOR = 2352
SYNC_HEADER = 16
USER_DATA = 2048
GM3_LBA = 39128
GM3_SIZE = 248184832
GM3_NSEC = (GM3_SIZE + USER_DATA - 1) // USER_DATA
DRAMA_IDX = list(range(295, 300))  # the 5 dramas (Tickets 1-5)


def read_logical(f, lba: int, nbytes: int) -> bytes:
    out = bytearray()
    nsec = (nbytes + USER_DATA - 1) // USER_DATA
    for i in range(nsec):
        f.seek((lba + i) * RAW_SECTOR + SYNC_HEADER)
        out += f.read(USER_DATA)
    return bytes(out[:nbytes])


def parse_idx(idx: bytes):
    ents = [struct.unpack(">HH", idx[i:i + 4]) for i in range(0, len(idx), 4)]
    while ents and ents[-1] == (0, 0):
        ents.pop()
    abs_sec, carry, prev = [], 0, None
    for _hi, lo in ents:
        if prev is not None and lo < prev:
            carry += 65536
        abs_sec.append(lo + carry)
        prev = lo
    return abs_sec


def adx_coeffs(highpass: int, sr: int) -> tuple[int, int]:
    z = math.cos(2.0 * math.pi * highpass / sr)
    a = math.sqrt(2.0) - z
    b = math.sqrt(2.0) - 1.0
    c = (a - math.sqrt((a + b) * (a - b))) / b
    return round(c * 2.0 * 4096), round(-(c * c) * 4096)


def decode_adx(data: bytes) -> tuple[np.ndarray, int, int]:
    """Return (interleaved int16 samples [n*ch], sample_rate, channels)."""
    if data[:2] != b"\x80\x00":
        raise ValueError("not an ADX stream")
    copyright_off = struct.unpack(">H", data[2:4])[0]
    start = copyright_off + 4
    channels = data[7]
    sr = struct.unpack(">I", data[8:12])[0]
    total = struct.unpack(">I", data[12:16])[0]
    highpass = struct.unpack(">H", data[16:18])[0]
    coef1, coef2 = adx_coeffs(highpass, sr)

    BLOCK = 18           # bytes per channel-frame
    SAMP = 32            # samples per frame
    body = data[start:]
    frame_stride = BLOCK * channels
    nframes = len(body) // frame_stride

    out = np.zeros((channels, nframes * SAMP), dtype=np.int16)
    for ch in range(channels):
        hist1 = hist2 = 0
        pos = ch * BLOCK
        sidx = 0
        smp = out[ch]
        for _ in range(nframes):
            scale = struct.unpack(">h", body[pos:pos + 2])[0]
            nibbles = body[pos + 2:pos + BLOCK]
            for byte in nibbles:
                for nib in (byte >> 4, byte & 0xF):
                    if nib >= 8:
                        nib -= 16
                    pred = (coef1 * hist1 + coef2 * hist2) >> 12
                    s = nib * scale + pred
                    s = -32768 if s < -32768 else (32767 if s > 32767 else s)
                    smp[sidx] = s
                    sidx += 1
                    hist2 = hist1
                    hist1 = s
            pos += frame_stride

    total = min(total, out.shape[1])
    out = out[:, :total]
    inter = out.T.reshape(-1)  # interleave channels
    return inter, sr, channels


def write_wav(path: Path, samples: np.ndarray, sr: int, channels: int):
    w = wave.open(str(path), "wb")
    w.setnchannels(channels)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(samples.astype("<i2").tobytes())
    w.close()


def cmd_extract(args):
    disc = Path(args.track1)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    with open(disc, "rb") as f:
        idx = read_logical(f, GM3_LBA - 2, 4096)  # GM3.IDX is 2 sectors before GM3.STZ (lba 39126)
        # safer: locate via known IDX file we already extracted
        idxfile = outdir / "GM3.IDX"
        if idxfile.exists():
            idx = idxfile.read_bytes()
        abs_sec = parse_idx(idx)
        for n, k in enumerate(DRAMA_IDX, 1):
            s0 = abs_sec[k]
            s1 = abs_sec[k + 1] if k + 1 < len(abs_sec) else GM3_NSEC
            nbytes = (s1 - s0) * USER_DATA
            blob = read_logical(f, GM3_LBA + s0, nbytes)
            samples, sr, ch = decode_adx(blob)
            wavp = outdir / f"drama{n}_idx{k}.wav"
            write_wav(wavp, samples, sr, ch)
            dur = samples.shape[0] / ch / sr
            print(f"drama{n} (idx {k}): {dur:6.1f}s {sr}Hz ch{ch} -> {wavp}")


def cmd_decode(args):
    blob = Path(args.adx).read_bytes()
    samples, sr, ch = decode_adx(blob)
    write_wav(Path(args.out), samples, sr, ch)
    print(f"{samples.shape[0]//ch/sr:.1f}s {sr}Hz ch{ch} -> {args.out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract"); e.add_argument("track1"); e.add_argument("--out", default="work/theater"); e.set_defaults(fn=cmd_extract)
    d = sub.add_parser("decode"); d.add_argument("adx"); d.add_argument("out"); d.set_defaults(fn=cmd_decode)
    a = ap.parse_args()
    return a.fn(a) or 0


if __name__ == "__main__":
    raise SystemExit(main())
