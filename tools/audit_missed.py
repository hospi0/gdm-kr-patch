# -*- coding: utf-8 -*-
"""**독립 검출기** — `extract_runs` 를 신뢰하지 않고 미추출 문장을 찾는다.

앞선 감사(`audit_runs.py`)는 `extract_runs` 결과를 기준으로 tsv 와 대조했다 —
**순환 논리다.** 실제로 `E810.MDT` 섹션 0x222 의
`見たいフィルムを LRボタンで そして` 는 앞쪽 쓰레기 바이트와 한 런으로 묶여
노이즈 판정으로 통째로 버려져 있었다(§19 "오염 접두"와 같은 유형).

여기선 블록·앵커 로직을 **쓰지 않고** 섹션 전체를 그리디 디코드한 뒤,
"진짜 일본어 문장"으로 보이는 **최대 구간**을 뽑아 tsv 커버리지와 대조한다.
"""
import os
import re
import sys

sys.path.insert(0, 'tools')
import extract_runs as ER
import codemap

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
PUNCT = set('‥…。、・「」『』！？⁉‼～ー♪♥○※（）　 ：')

DM = 'work/dm'
TSV = 'work/trans/runs.tsv'


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def greedy(sec):
    """(바이트오프셋, 글자) 목록 — 그리디 디코드."""
    out = []
    i = 0
    n = len(sec)
    while i < n:
        b = sec[i]
        if 0x10 <= b <= 0x1F and i + 1 < n:
            out.append((i, ER.m.get(0xE0 + (b - 0x10) * 256 + sec[i + 1], '?')))
            i += 2
        elif b >= 0x20:
            out.append((i, ER.m.get(b - 0x20, '?')))
            i += 1
        else:
            out.append((i, None))          # 제어코드 = 경계
            i += 1
    return out


def sentences(sec, minlen=6):
    """진짜 일본어로 보이는 최대 구간 [(시작, 끝, 문장)]."""
    toks = greedy(sec)
    out = []
    cur = []
    for off, ch in toks:
        good = ch is not None and (ch in HIRA or ch in KATA or is_kanji(ch) or ch in PUNCT
                                   or ch.isdigit() or ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        if good:
            cur.append((off, ch))
        else:
            if cur:
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)

    res = []
    for run in out:
        t = ''.join(c for _, c in run)
        if len(t) < minlen:
            continue
        hira = sum(1 for c in t if c in HIRA)
        kan = sum(1 for c in t if is_kanji(c))
        kat = sum(1 for c in t if c in KATA)
        pun = sum(1 for c in t if c in PUNCT)
        # 라틴 대문자·숫자는 게임 UI 문구(`LRボタン`, `Aボタン：`)에 정상적으로 쓰인다
        lat = sum(1 for c in t if c.isdigit() or c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        if hira < 3 or (hira + kan + kat + pun + lat) < len(t) * 0.9:
            continue
        if t.count('自') or t.count('方') > 1 or t.count('敵') > 1:
            continue                       # §18 에서 확인된 3D 데이터 노이즈 지문
        # 진짜 문장 지문: 조사/어미가 보인다
        if not re.search(r'[はがをにでとへの][ぁ-ん一-鿿]|[ますませんだよねかたてるらしいっ]{2}', t):
            continue
        res.append((run[0][0], run[-1][0], t))
    return res


def load_tsv_ranges():
    rng = {}
    with open(TSV, encoding='utf-8') as f:
        for line in f:
            a = line.rstrip('\n').split('\t')
            if len(a) < 4 or a[1] == 'off':
                continue
            try:
                fn, off, ln = a[0], int(a[1], 16), int(a[2])
            except ValueError:
                continue
            ko = a[4] if len(a) > 4 else ''
            rng.setdefault(fn, []).append((off, off + ln, ko))
    return rng


def main():
    tsv = load_tsv_ranges()
    missed = []
    for fn in sorted(os.listdir(DM)):
        if not fn.endswith('.MDT'):
            continue
        short = fn[6:]
        if short in ('0000.MDT', '0004.MDT', 'EC08.MDT', 'E8FF.MDT'):
            continue                       # §18.3: 대사가 아예 없는 노이즈 파일
        d = open(os.path.join(DM, fn), 'rb').read()
        try:
            o, sec, _ = ER.extract(d, short)
        except Exception:
            continue
        covered = tsv.get(short, [])
        for a, b, t in sentences(sec):
            # tsv 구간과 겹치면 커버된 것으로 본다
            if any(not (b < s or a > e) for s, e, _ in covered):
                continue
            missed.append((short, a, t))

    print('독립 검출: tsv 가 전혀 안 덮는 일본어 문장 %d건' % len(missed))
    with open('work/trans/audit_missed.txt', 'w', encoding='utf-8') as f:
        for s_, a, t in missed:
            f.write('%-12s %05X  %s\n' % (s_, a, t))
    for s_, a, t in missed[:40]:
        print('  %-12s %05X  %s' % (s_, a, t))
    print('\nwork/trans/audit_missed.txt 저장')


if __name__ == '__main__':
    main()
