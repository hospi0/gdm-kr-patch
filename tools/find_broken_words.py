# -*- coding: utf-8 -*-
"""자동 축약이 만들어 낸 **비단어**를 찾는다.

이전 세션의 `auto_shrink`/`shrink_overflow` 가 예산을 맞추려고 조사·음절을 지우면서
말이 안 되는 단어를 만들었다(실기 제보):
  `그만두기`→`그두기`, `데이터`→`데터`, `세이브`→`세브`, `있을 리가`→`있 리가`,
  `하는 게`→`하 게`, `남은 건`→`남 건`.

검출법: 축약 **전** 원문이 `work/trans/batch_clean.tsv` 에 남아 있다.
단어 단위로 짝지어, 축약본 단어가 원본 단어의 **부분수열이면서 접두·접미가 아닌**
(= 가운데 음절이 빠진) 경우를 비단어로 본다. 접미 삭제라도 1음절만 남으면 역시 잡는다.
"""
import io
import re
import sys

sys.path.insert(0, 'tools')
from runs_build import load_maps, encode, BuildError

REV, KO = load_maps()
CLEAN = 'work/trans/batch_clean.tsv'
RUNS = 'work/trans/runs.tsv'
HAN = re.compile(r'[가-힣]+')


def enc_len(t):
    try:
        return len(encode(t, REV, KO))
    except BuildError:
        return None


def load(p):
    d = {}
    for line in io.open(p, encoding='utf-8'):
        a = line.rstrip('\n').split('\t')
        if len(a) >= 5:
            d[(a[0], a[1])] = (a[2], a[3], a[4])
    return d


def is_subseq(short, long_):
    it = iter(long_)
    return all(c in it for c in short)


BOUND = ('거', '것', '게', '건', '리', '수', '때', '뿐', '줄', '데', '지')


def damaged(clean_w, cut_w):
    """(등급, 사유) 또는 None.
    'A' = **가운데 음절이 빠진** 비단어(데이터→데터, 그만두기→그두기)
    'B' = 어미가 잘려 1음절만 남음(있을→있, 하는→하) — 뒤에 의존명사가 오면 비문
    """
    if cut_w == clean_w or not cut_w or len(cut_w) >= len(clean_w):
        return None
    if not is_subseq(cut_w, clean_w):
        return None
    if clean_w.startswith(cut_w):
        return ('B', '어미잘림') if len(cut_w) == 1 else None
    if clean_w.endswith(cut_w):
        return ('B', '앞잘림') if len(cut_w) == 1 else None
    return ('A', '가운데음절삭제')


def main():
    clean, runs = load(CLEAN), load(RUNS)
    hits = []
    for k, (ln, ja, ck) in clean.items():
        if k not in runs:
            continue
        _, _, rk = runs[k]
        if not ck.strip() or not rk.strip() or ck == rk:
            continue
        cw = HAN.findall(ck)
        rw = HAN.findall(rk)
        bad = []
        used = set()
        for w in rw:
            if w in cw:
                continue
            for i, c in enumerate(cw):
                if i in used:
                    continue
                dm = damaged(c, w)
                if dm:
                    bad.append((dm[0], c, w))
                    used.add(i)
                    break
        if bad:
            hits.append((k[0], k[1], ln, ja, ck, rk, bad))

    A = [h for h in hits if any(b[0] == 'A' for b in h[6])]
    B = [h for h in hits if h not in A]
    print('A. 가운데 음절 삭제(비단어) %d건 / B. 1음절만 남음 %d건' % (len(A), len(B)))
    with io.open('work/trans/broken_words.txt', 'w', encoding='utf-8') as f:
        for fn, off, ln, ja, ck, rk, bad in hits:
            f.write('%s\t%s\t%s\n  JA %s\n  현재 %s\n  원본 %s\n  깨진단어 %s\n'
                    % (fn, off, ln, ja, rk, ck, bad))
    print('\n=== A. 비단어 (반드시 수정) ===')
    for h in A:
        print('  %-11s %s  %s' % (h[0], h[1], [(b[1], b[2]) for b in h[6] if b[0] == 'A']))
        print('      현재 %s' % h[5])
        print('      원본 %s' % h[4])
    print('\n=== B. 어미 잘림 (앞 20) ===')
    for h in B[:20]:
        print('  %-11s %s  %s' % (h[0], h[1], [(b[1], b[2]) for b in h[6]]))
        print('      현재 %s' % h[5])
    print('\nwork/trans/broken_words.txt 저장')


if __name__ == '__main__':
    main()
