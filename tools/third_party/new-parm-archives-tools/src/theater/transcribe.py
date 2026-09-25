#!/usr/bin/env python3
"""Transcribe a theater-drama WAV to timed Japanese text via faster-whisper (ASR).

The dramas are spoken Japanese with no on-screen text; the agent can't hear audio, so we run a
speech-to-text model to get BOTH the JP transcript AND per-segment timestamps (which double as the
caption timing). Output is machine-generated and MUST be reviewed/corrected (ASR is imperfect on
1996 game VO) before it becomes the canonical script — write it under work/theater/ (gitignored),
not script/.

  python3 src/theater/transcribe.py work/theater/drama1_loop_18-125s.wav --model large-v3
  # -> work/theater/<wav-stem>.asr.json  (+ .asr.txt readable)

Models cache to ~/.cache/huggingface on first use (network). large-v3 = best JP quality (slow on
CPU); medium = faster pilot. Decoding uses PyAV (no system ffmpeg needed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--lang", default="ja")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8", help="int8 (CPU) / float16 (GPU)")
    ap.add_argument("--vad", action="store_true", help="enable VAD (default OFF — it drops game VO)")
    ap.add_argument("--prompt", default=(
        "グランディアのキャラクターたちが繰り広げるラジオドラマ。"
        "ジャスティン、フィーナ、スー、ガダン、パコン、リエーテ、ガドウィンなどが会話する。"),
        help="initial_prompt to prime character names / register")
    a = ap.parse_args()

    from faster_whisper import WhisperModel

    wav = Path(a.wav)
    if not wav.exists():
        print(f"ERROR: {wav} not found", file=sys.stderr)
        return 1

    print(f"loading model={a.model} device={a.device} compute={a.compute_type} ...", file=sys.stderr)
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type)

    print(f"transcribing {wav.name} (lang={a.lang}) ...", file=sys.stderr)
    # Tuned for 1996 game radio-drama VO over a constant music bed (validated on drama #1):
    # VAD off (it drops the masked VO), a character-name initial_prompt, and relaxed no-speech /
    # compression-ratio thresholds so quiet lines aren't dropped as "music" or hallucinated.
    segments, info = model.transcribe(
        str(wav),
        language=a.lang,
        vad_filter=a.vad,
        beam_size=5,
        temperature=0.0,
        no_speech_threshold=0.3,
        compression_ratio_threshold=2.0,
        condition_on_previous_text=False,  # long musical gaps; avoid hallucination drift
        initial_prompt=a.prompt,
    )

    out = {"wav": str(wav), "model": a.model, "lang": a.lang,
           "duration": getattr(info, "duration", None), "segments": []}
    txt_lines = []
    for s in segments:
        seg = {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        out["segments"].append(seg)
        line = f"[{fmt(s.start)} -> {fmt(s.end)}] {s.text.strip()}"
        print(line)
        txt_lines.append(line)

    j = wav.with_suffix(".asr.json")
    t = wav.with_suffix(".asr.txt")
    j.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    t.write_text("\n".join(txt_lines) + "\n")
    print(f"\nwrote {j}\nwrote {t}\n{len(out['segments'])} segments", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
