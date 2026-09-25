# -*- coding: utf-8 -*-
"""**한 번도 조사하지 않은 파일**의 텍스트 조사 (2026-08-07 세션8).

실기 스샷에서 박물관 컨텐츠(명장면 셀렉트·몬스터 도감·캐릭터 표정집)와
전투 이름표가 통째로 깨진 한글 = 미번역 원문으로 나왔다.
`ジャスティン` 역추적으로 SCNRL/DICDT/MTMES/MTOUT/ITGET/WMESS 등이 드러났다.

여기서는 «빌드에서 한 번도 건드리지 않은 파일» 전부를 훑어 실제 일본어
문자열을 뽑는다. 판정은 [[feedback_scan_coverage_and_detectors]] 규칙대로
양성(가나 비율)·음성(제어 바이트 밀도)·고유율 3종을 모두 건다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)

TOUCHED = set(os.listdir('work/build')) if os.path.isdir('work/build') else set()


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def is_jp(ch):
    return ch in HIRA or ch in KATA or is_kanji(ch)


PUNCT = set('　 ！？、。・：‥…～「」『』（）♥♪○◆★％＋－／０１２３４５６７８９')
ASCII_OK = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 !?.,:-/%+')


def runs(d, minlen=3):
    """널 구분 문자열 후보 -> [(off, raw, text)]"""
    out = []
    i = 0
    n = len(d)
    while i < n:
        if d[i] == 0:
            i += 1
            continue
        j = i
        while j < n and d[j] != 0:
            j += 1
        if j - i >= minlen:
            out.append((i, d[i:j]))
        i = j + 1
    return out


def decode(raw):
    """전각/반각 모드를 따라가며 디코드. 반각은 halfwidth 표."""
    import halfwidth as H
    out = []
    half = False
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0x03:
            half = True
            i += 1
            continue
        if b == 0x04:
            half = False
            i += 1
            continue
        if b < 0x10:
            out.append('\x00')
            i += 1
            continue
        if half:
            out.append(H.IDX2CH.get(b - 0x20, '?') if b >= 0x20 else '?')
            i += 1
            continue
        if 0x10 <= b <= 0x1F and i + 1 < len(raw):
            out.append(B.M.get(0xE0 + (b - 0x10) * 256 + raw[i + 1], '?'))
            i += 2
            continue
        out.append(B.M.get(b - 0x20, '?'))
        i += 1
    return ''.join(out)


def score(t):
    """실제 일본어 문장/라벨인가."""
    core = [c for c in t if c != '\x00']
    if len(core) < 3:
        return False
    jp = sum(1 for c in core if is_jp(c))
    ok = sum(1 for c in core if is_jp(c) or c in PUNCT or c in ASCII_OK)
    if jp < 2:
        return False
    if ok / len(core) < 0.9:              # 음성: 깨진 글자·기호 섞이면 탈락
        return False
    if len(set(core)) / len(core) < 0.34:  # 고유율: 같은 글자 반복 = 데이터
        return False
    return True


def main():
    root = 'work/dm'
    only = sys.argv[1:]
    for fn in sorted(os.listdir(root)):
        if fn in TOUCHED or fn == 'bbg_region.bin':
            continue
        if only and not any(o in fn for o in only):
            continue
        d = open(os.path.join(root, fn), 'rb').read()
        hits = []
        for off, raw in runs(d):
            t = decode(raw)
            if score(t):
                hits.append((off, len(raw), t))
        print('\n=== %-20s %8d B   텍스트 후보 %d ===' % (fn, len(d), len(hits)))
        for off, ln, t in hits[:400]:
            print('  0x%06X len=%3d  %s' % (off, ln, t.replace('\x00', '|')))
        if len(hits) > 400:
            print('  … 외 %d' % (len(hits) - 400))


if __name__ == '__main__':
    main()
