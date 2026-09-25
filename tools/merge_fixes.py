# -*- coding: utf-8 -*-
"""이번 회차 수정을 `runs.tsv` 에 병합한다.

  1) `word_fix_ko.FIX`   — 자동 축약이 만든 비단어 68건을 자연스러운 말로
  2) `missed_ko.KO`      — `extract_runs` 가 놓쳐 tsv 에 아예 없던 46건 신규 추가

⚠️ 병합 전 `runs.tsv` 를 백업한다(관례: `.bak_<태그>`).
"""
import io
import os
import shutil
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
from runs_build import load_maps, encode, BuildError
import word_fix_ko as W
import missed_ko as M

REV, KO = load_maps()
RUNS = 'work/trans/runs.tsv'
TAG = 'bak_session7_words'


def enc_len(t):
    try:
        return len(encode(t, REV, KO))
    except BuildError:
        return None


def main():
    shutil.copyfile(RUNS, RUNS + '.' + TAG)
    rows, order = {}, []
    for line in io.open(RUNS, encoding='utf-8'):
        a = line.rstrip('\n').split('\t')
        if len(a) < 4:
            continue
        k = (a[0], a[1])
        rows[k] = a + [''] * (5 - len(a))
        order.append(k)

    # 1) 비단어 수정
    n1 = 0
    for k, t in W.FIX.items():
        if k not in rows:
            print('  ? 없는 키', k)
            continue
        slot = int(rows[k][2])
        n = enc_len(t)
        if n is None or n > slot:
            print('  X 예산초과', k, t)
            continue
        rows[k][4] = t
        n1 += 1

    # 2) 미추출 문장 신규 추가
    todo = []
    for line in io.open('work/trans/todo_missed.tsv', encoding='utf-8'):
        a = line.rstrip('\n').split('\t')
        if len(a) < 4 or a[1] == 'off':
            continue
        todo.append((a[0], a[1], int(a[2]), a[3]))

    n2 = skip = 0
    for fn, off, ln, ja in todo:
        k = (fn, off)
        if (fn, int(off, 16)) in M.DROP:
            continue
        ov = M.OVERRIDE.get((fn, int(off, 16)))
        if ov:
            off2, ln2 = ov
            k = (fn, '%05X' % off2)
            ln = ln2
            # 원문 재계산 없이 OVERRIDE 문장을 KO 표에서 찾는다
        ko_t = None
        for ja_key, v in M.KO.items():
            if ja_key in ja or ja.endswith(ja_key):
                ko_t = v
                break
        if ko_t is None:
            skip += 1
            continue
        n = enc_len(ko_t)
        if n is None or n > ln:
            print('  X 신규 예산초과 %s %s (%s>%d) %s' % (fn, k[1], n, ln, ko_t))
            skip += 1
            continue
        if k in rows:
            rows[k][4] = ko_t
        else:
            rows[k] = [fn, k[1], str(ln), ja, ko_t]
            order.append(k)
        n2 += 1

    with io.open(RUNS, 'w', encoding='utf-8') as f:
        for k in order:
            f.write('\t'.join(rows[k]) + '\n')
    print('비단어 수정 %d건, 미추출 신규 %d건(건너뜀 %d) -> %s' % (n1, n2, skip, RUNS))


if __name__ == '__main__':
    main()
