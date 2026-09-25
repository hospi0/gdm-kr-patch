# -*- coding: utf-8 -*-
"""batch_clean.tsv 의 번역을 필요시 축약해서 runs.tsv 에 병합한다."""
import csv
import re
import sys

sys.path.insert(0, 'tools')
from runs_build import load_maps, encode, BuildError

rev, ko = load_maps()


def fits(t, L):
    try:
        return len(encode(t, rev, ko)) <= L
    except BuildError:
        return False


FILLERS = ['정말로 ', '정말 ', '진짜로 ', '진짜 ', '그야말로 ', '아무래도 ', '역시 ',
           '그러니까 ', '그러니깐 ', '그렇지만 ', '그치만 ', '그야 ', '뭐랄까 ',
           '어쨌든 ', '어차피 ', '그나저나 ', '그건 그렇고 ', '그러고 보니 ',
           '이제 ', '자, ', '음, ', '뭐, ', '저기, ', '있잖아, ',
           '그런데 ', '그러면 ', '그렇다면 ', '그러니 ', '아니 ', '자아 ',
           '조금 ', '좀 더 ', '약간 ', '어쩐지 ', '왠지 ', '분명히 ', '분명 ']

CONTRACT = [
    ('것 같아', '듯해'), ('것 같다', '듯하다'), ('것 같은데', '듯한데'),
    ('하지 않아', '안 해'), ('하지 않는', '안 하는'), ('하지 않다', '안 하다'),
    ('되었다', '됐다'), ('되었어', '됐어'), ('이었다', '였다'), ('이었어', '였어'),
    ('습니다', '어요'), ('입니다', '이에요'), ('있습니다', '있어요'), ('합니다', '해요'),
    ('그렇게', '그리'), ('이렇게', '이리'), ('저렇게', '저리'), ('어떻게', '어찌'),
    ('그러하다', '그렇다'), ('무엇을', '뭘'), ('무엇이', '뭐가'), ('무엇인가', '뭔가'),
    ('그것은', '그건'), ('그것이', '그게'), ('이것은', '이건'), ('이것이', '이게'),
    ('저것은', '저건'), ('나는', '난'), ('나를', '날'), ('너는', '넌'), ('너를', '널'),
    ('것은', '건'), ('것이', '게'), ('하는 것', '하는 거'), ('하지만', '근데'),
    ('말이지', '말이야'), (' 말이야', ''), (' 말이지', ''), (' 말이다', ''),
    ('거든요', '거든'), ('니까요', '니까'), ('구나', '군'), ('는구나', '는군'),
    ('다구', '다'), ('한 번', '한번'), ('두 번', '두번'), ('세 번', '세번'),
    (' 좀 더', ' 더'), (' 정도로', '쯤'), (' 정도', '쯤'), (' 이제', ''),
    ('생각하고 또 생각해', '곰곰이 생각해'), ('뭐니 뭐니 해도', '뭐니뭐니해도'),
    ('있으면 좋겠는', '있으면'), ('알려줬으면', '알려주면'),
]

PARTICLE_RE = re.compile(r'([가-힣])(이|가|을|를|은|는|의|도|만|에|께)(?=[\s,.!?‥…～]|$)')
PARTICLE_RE2 = re.compile(r'([가-힣])(이|가|을|를|은|는|의|도|만|에|께)(?=[가-힣])')


def collapse_punct(t):
    t = re.sub(r'‥{2,}', '‥‥', t)
    t = re.sub(r'!{2,}', '!', t)
    t = re.sub(r'\?{2,}', '?', t)
    t = re.sub(r' {2,}', ' ', t)
    return t


def try_shrink(t, L):
    if fits(t, L):
        return t, 'ok'
    c = collapse_punct(t)
    if c != t and fits(c, L):
        return c, 'punct'
    t2 = c
    for f in FILLERS:
        if f in t2:
            cand = t2.replace(f, '', 1)
            if fits(cand, L):
                return cand, 'filler:' + f
            t2 = cand
    if fits(t2, L):
        return t2, 'fillers'
    for a, b in CONTRACT:
        if a in t2:
            cand = t2.replace(a, b)
            if fits(cand, L):
                return cand, 'contract:' + a
            t2 = cand
    if fits(t2, L):
        return t2, 'contracts'
    cur = t2
    for _ in range(8):
        matches = list(PARTICLE_RE.finditer(cur))
        if not matches:
            break
        mm = matches[-1]
        cand = cur[:mm.start(2)] + cur[mm.end(2):]
        if fits(cand, L):
            return cand, 'particle'
        cur = cand
    if fits(cur, L):
        return cur, 'particles'
    for _ in range(8):
        matches = list(PARTICLE_RE2.finditer(cur))
        if not matches:
            break
        mm = matches[-1]
        cand = cur[:mm.start(2)] + cur[mm.end(2):]
        if fits(cand, L):
            return cand, 'particle2'
        cur = cand
    if fits(cur, L):
        return cur, 'particles2'
    return None, 'fail'


def main():
    runs = list(csv.DictReader(open('work/trans/runs.tsv', encoding='utf-8'), delimiter='\t'))
    idx = {(r['file'], r['off']): i for i, r in enumerate(runs)}

    n_ok = n_fail = n_asis = 0
    fails = []
    for r in csv.DictReader(open('work/trans/batch_clean.tsv', encoding='utf-8'), delimiter='\t'):
        i = idx.get((r['file'], r['off']))
        if i is None:
            continue
        ko_t = r['ko'].strip()
        if not ko_t:
            continue
        L = int(runs[i]['len'])
        if fits(ko_t, L):
            runs[i]['ko'] = ko_t
            n_asis += 1
            continue
        newt, how = try_shrink(ko_t, L)
        if newt is None:
            fails.append((r['file'], r['off'], L, ko_t))
            n_fail += 1
        else:
            runs[i]['ko'] = newt
            n_ok += 1

    print('그대로 적용 %d / 자동 축약 성공 %d / 실패(사람 필요) %d' % (n_asis, n_ok, n_fail))
    with open('work/trans/runs.tsv.merged3', 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t')
        w.writerow(['file', 'off', 'len', 'ja', 'ko'])
        for r in runs:
            w.writerow([r['file'], r['off'], r['len'], r['ja'], r['ko']])
    with open('work/trans/shrink_fail.txt', 'w', encoding='utf-8') as f:
        for x in fails:
            f.write('%s\t%s\t%d\t%s\n' % x)
    print('저장: runs.tsv.merged3 (%d행) / shrink_fail.txt (%d건)' % (len(runs), len(fails)))


if __name__ == '__main__':
    main()
