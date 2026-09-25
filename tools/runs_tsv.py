# -*- coding: utf-8 -*-
"""런 단위 번역 자산(TSV)을 만든다. 기존 번역이 있으면 재사용한다.

열: file / off / len / ja / ko
  off = 스크립트 섹션 안에서의 **바이트 오프셋**
  len = 런의 **바이트 길이** (제자리 교체이므로 이 값을 넘기면 안 된다)
  ja  = 원문 (수정 금지)
  ko  = 번역문 (비우면 원문 유지)

⚠️ 런 안에는 제어코드가 없다(런 정의상 글자만 이어진 구간). 그래서 `{hex}` 토큰이
   나오지 않으며, 번역은 순수 텍스트다.

## 세션4 재사용 정책

세션3까지 `work/trans/runs.tsv` 에 번역 3,938건(66.8%)이 쌓여 있었다. `extract_runs.py`
를 확정 디코더로 재작성(§16)하면서 런 경계가 바뀌었으므로(인수 침범이 있던 런은
원문 자체가 달라진다 — 예 `ニパームの港` → `パームの港`), **원문 텍스트로 재사용을
매칭**한다: 원문이 그대로인 런은 번역이 자동으로 따라오고, 원문이 바뀐(=옛 경계가
틀렸던) 런은 재사용되지 않아 다시 확인해야 함이 드러난다 — 이게 맞는 동작이다.

우선순위: ① 세션3 `runs.tsv`(사람이 검수한 번역, 클린업 포함) → ② 세션2 `script.tsv`
(메시지 단위, 옛 자산). 둘 다 원문 문자열 → 번역 사전으로 바꿔 겹치면 ①이 이긴다.
"""
import csv
import glob
import os
import re
import sys

sys.path.insert(0, 'tools')
from extract_runs import extract, text

PREV = sorted(glob.glob('work/trans/runs.tsv.bak_session*_pre_*'), key=os.path.getmtime)
OLD_SCRIPT = 'work/trans/script.tsv'
OUT = 'work/trans/runs.tsv'
TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def runs_pairs(path):
    """세션3 runs.tsv 형식(원문 그대로, 토큰 없음)에서 (원문 → 번역) 사전."""
    d = {}
    if not path or not os.path.exists(path):
        return d
    for r in csv.DictReader(open(path, encoding='utf-8'), delimiter='\t'):
        ja, ko = r.get('ja', '').strip(), r.get('ko', '').strip()
        if ja and ko and ja != ko:
            d.setdefault(ja, ko)
    return d


def script_pairs(path):
    """옛 메시지 단위 번역(제어코드 토큰 포함)에서 (원문런 → 번역런) 사전."""
    d = {}
    if not os.path.exists(path):
        return d
    for r in csv.DictReader(open(path, encoding='utf-8'), delimiter='\t'):
        if not r['ko']:
            continue
        a = [p for p in TOKRE.split(r['ja']) if p and not TOKRE.fullmatch(p)]
        b = [p for p in TOKRE.split(r['ko']) if p and not TOKRE.fullmatch(p)]
        if len(a) != len(b):
            continue
        for x, y in zip(a, b):
            x, y = x.strip(), y.strip()
            if x and y and x != y:
                d.setdefault(x, y)
    return d


def main():
    reuse = {}
    prev_path = PREV[-1] if PREV else None
    n1 = 0
    if prev_path:
        p1 = runs_pairs(prev_path)
        reuse.update(p1)
        n1 = len(p1)
    p2 = script_pairs(OLD_SCRIPT)
    n2_new = sum(1 for k in p2 if k not in reuse)
    for k, v in p2.items():
        reuse.setdefault(k, v)
    print('재사용 소스: %s (%d종) + %s (%d종 추가)'
          % (prev_path or '(없음)', n1, OLD_SCRIPT, n2_new))

    rows = []
    hit = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, s, rs = extract(d)
        for off, L, codes in rs:
            ja = text(codes)
            ko = reuse.get(ja.strip(), '')
            if ko:
                hit += 1
            rows.append([f[6:], '%05X' % off, str(L), ja, ko])
    os.makedirs('work/trans', exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        w.writerow(['file', 'off', 'len', 'ja', 'ko'])
        w.writerows(rows)
    print('%s — 런 %d개 (자동 재사용 %d개, %.1f%%)'
          % (OUT, len(rows), hit, 100.0 * hit / max(len(rows), 1)))
    print('글자 %d자' % sum(len(r[3]) for r in rows))


if __name__ == '__main__':
    main()
