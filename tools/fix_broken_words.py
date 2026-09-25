# -*- coding: utf-8 -*-
"""자동 축약이 만든 **비단어**를 자연스러운 말로 되돌린다.

정책(사용자 지시): 문장 전체를 원본으로 되돌리지 않는다. **깨진 단어만** 고친다.
  1) 깨진 단어 자리에 원본 단어를 도로 넣어 보고, 예산에 들어가면 채택
  2) 안 들어가면 `SHORT` 표의 **더 짧은 진짜 단어**로 교체
     (예 `그만두기`→`관두기`, `데이터` 는 조사를 빼서라도 살린다)
  3) 그래도 안 되면 문장 안의 **조사 하나를 빼서** 자리를 만든다
"""
import io
import re
import sys

sys.path.insert(0, 'tools')
from runs_build import load_maps, encode, BuildError
import find_broken_words as F

REV, KO = load_maps()

# 원본이 너무 길 때 쓸 **짧지만 말이 되는** 대체어
SHORT = {
    '그만두기': ['관두기'],
    '그만두는': ['관두는'],
    '그만둔다': ['관둔다'],
    '데이터': ['데이터'],
    '세이브': ['세이브', '저장'],
    '기관차처럼': ['기차처럼'],          # 이건 원래 허용 가능
    '알려줬으면': ['알려주면'],
    '넘쳐났었는데': ['넘쳐났는데'],
    '으와아아아앗': ['으와아앗'],
    '어디쯤에서': ['어디서'],
    '항구에서': ['항구서'],
    '광산에서': ['광산서'],
}

# 자리를 만들기 위해 지워도 되는 조사(뒤에서부터 하나씩)
DROP_PARTICLE = re.compile(r'(?<=[가-힣])(을|를|이|가|은|는|의|에|도)(?=\s)')


def enc_len(t):
    try:
        return len(encode(t, REV, KO))
    except BuildError:
        return None


def try_fit(text, slot):
    n = enc_len(text)
    return n is not None and n <= slot


def make_room(text, slot):
    """조사를 뒤에서부터 하나씩 빼서 예산에 맞춘다."""
    cur = text
    while not try_fit(cur, slot):
        ms = list(DROP_PARTICLE.finditer(cur))
        if not ms:
            return None
        m = ms[-1]
        cur = cur[:m.start()] + cur[m.end():]
    return cur


def main():
    clean, runs = F.load(F.CLEAN), F.load(F.RUNS)
    fixes, failed = {}, []
    for k, (ln, ja, ck) in clean.items():
        if k not in runs:
            continue
        slot_s, _, rk = runs[k]
        if not ck.strip() or not rk.strip() or ck == rk:
            continue
        slot = int(slot_s)
        cw, rw = F.HAN.findall(ck), F.HAN.findall(rk)
        new = rk
        changed = []
        used = set()
        for w in rw:
            if w in cw:
                continue
            for i, c in enumerate(cw):
                if i in used:
                    continue
                dm = F.damaged(c, w)
                if dm and dm[0] == 'A':
                    used.add(i)
                    for cand in SHORT.get(c, []) + [c]:
                        trial = new.replace(w, cand, 1)
                        if try_fit(trial, slot):
                            new, _ = trial, changed.append((w, cand))
                            break
                    else:
                        cand = (SHORT.get(c) or [c])[0]
                        trial = make_room(new.replace(w, cand, 1), slot)
                        if trial:
                            new = trial
                            changed.append((w, cand + '(조사삭제)'))
                        else:
                            failed.append((k[0], k[1], w, c, rk))
                    break
        if changed and new != rk:
            fixes[k] = (new, changed)

    print('비단어 수정 %d건 / 실패 %d건' % (len(fixes), len(failed)))
    with io.open('work/trans/word_fixes.tsv', 'w', encoding='utf-8') as f:
        f.write('file\toff\tko\n')
        for (fn, off), (new, ch) in sorted(fixes.items()):
            f.write('%s\t%s\t%s\n' % (fn, off, new))
    for (fn, off), (new, ch) in list(sorted(fixes.items()))[:25]:
        print('  %-11s %s  %s\n      -> %s' % (fn, off, ch, new))
    if failed:
        print('\n실패(수작업 필요):')
        for x in failed[:15]:
            print('  ', x)
    print('\nwork/trans/word_fixes.tsv 저장')


if __name__ == '__main__':
    main()
