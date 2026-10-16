# -*- coding: utf-8 -*-
r"""보이스 드라마 5편 받아쓰기 (2026-10-14) — work/theater/drama*.wav → work/theater/drama*_ja.tsv (시작·끝·원문).
  faster-whisper large-v3 (C:\claude\utils\whisper-venv), numpy 배열로 넘김, VAD 끔(짧은 외침이 빠짐 — [[feedback_asr_vad_drops_short_shouts]]).
  C:\claude\utils\whisper-venv\Scripts\python.exe tools/drama_asr.py
"""
import glob, os, sys, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
D = os.path.join(ROOT, 'work', 'theater')


def load16k(p):
    w = wave.open(p)
    sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    a = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    t = np.arange(0, len(a) / sr, 1 / 16000)
    return np.interp(t, np.arange(len(a)) / sr, a).astype(np.float32)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    from faster_whisper import WhisperModel
    m = WhisperModel('large-v3', device='cuda', compute_type='float16')
    if '--words' in sys.argv:          # 2026-10-16: 단어 시각(첫 단어 시작 = 실제 발화 시작) → 자막 싱크 보정용
        import json
        for p in sorted(glob.glob(os.path.join(D, 'drama*_idx*.wav'))):
            segs, _ = m.transcribe(load16k(p), language='ja', vad_filter=False, beam_size=5,
                                   condition_on_previous_text=False, word_timestamps=True)
            out = [dict(start=s.start, end=s.end, text=s.text.strip(),
                        words=[(w.start, w.end, w.word) for w in (s.words or [])]) for s in segs if s.text.strip()]
            json.dump(out, open(p.replace('.wav', '_words.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
            print(os.path.basename(p), len(out), flush=True)
        return
    for p in sorted(glob.glob(os.path.join(D, 'drama*_idx*.wav'))):
        out = p.replace('.wav', '_ja.tsv')
        segs, _ = m.transcribe(load16k(p), language='ja', vad_filter=False, beam_size=5,
                               condition_on_previous_text=False)
        n = 0
        with open(out, 'w', encoding='utf-8') as f:
            f.write('시작\t끝\t원문\n')
            for s in segs:
                t = s.text.strip()
                if t:
                    f.write('%.2f\t%.2f\t%s\n' % (s.start, s.end, t)); n += 1
        print('%s → %d줄' % (os.path.basename(out), n), flush=True)


if __name__ == '__main__':
    main()
