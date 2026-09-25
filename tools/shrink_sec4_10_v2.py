# -*- coding: utf-8 -*-
"""shrink_fail.tsv(732건, 자동축약 1차 실패분)을 다시 축약.
전략(순서대로 시도, 진짜 인코더로 매 단계 fit 확인):
  1) 공백/조사(의/은/는/이/가/을/를/에) 제거 — 명사를 붙여쓰기
  2) 확장 동의어표(레벨→렙, 효과가 있다→효과 등)
  3) 수식어 삭제(조금/약간/상당히/꽤/아주/정말/진짜)
  4) 고유명사(공백 없는 단일 토큰)는 뒤에서부터 음절 삭제
  5) 그래도 안 되면 문구 뒤쪽 절반(꾸밈말 구간)부터 통째로 절단
"""
import csv
import re
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()


def enc_len(t):
    try:
        return len(B.encode_with_vars(t, KO))
    except KeyError:
        return 99999


def fits(t, L):
    return enc_len(t) <= L


PARTICLE_DROP = ['의', '은', '는', '이', '가', '을', '를', '에', '도', '만']

SYN2 = [
    ('레벨十', '렙十'), ('내성 레벨', '내성'), ('내성레벨', '내성'), ('레벨을', '레벨'),
    (' 효과가 있다', ' 효과'), (' 효과 있음', ' 효과'), ('되어 있다', '됨'),
    ('되어 있는', '된'), ('하고 있다', '함'), ('달려 있다', '달림'), ('붙어 있다', '붙음'),
    ('것 같다', '듯'), ('것 같은', '듯한'), ('것 같아', '듯해'), ('것 같지 않다', '아닌 듯'),
    ('것이', '게'), ('것을', '걸'), ('것은', '건'), ('것 ', ' '), ('하지 않는다', '안 한다'),
    ('하지 않게 된다', '안 하게 됨'), ('걸리지 않게 된다', '안 걸림'), ('걸리지 않는다', '안 걸림'),
    ('당하지 않는다', '안 당함'), ('날아가지 않는다', '안 날아감'), ('전투 중 ', '전투중 '),
    ('사용하는', '쓰는'), ('사용된', '쓴'), ('만들어져 있다', '만듦'), ('만들었다', '만듦'),
    ('전해 주자', '전해주자'), ('만든 것', '만듦'), ('손수', '직접'), ('그럭저럭', '적당히'),
    ('불가사의한', '신기한'), ('신기한', '희한한'), ('있는가', '있나'), ('되었다', '됐다'),
    ('그렇게', '그리'), ('상당히 ', ''), ('꽤 ', ''), ('아주 ', ''), ('정말 ', ''),
    ('진짜 ', ''), ('의외로 ', ''), ('조금 ', ''), ('약간 ', ''), ('살짝 ', ''),
    ('완전히 ', ''), ('거의 ', ''), ('전혀 ', ''), ('전체', '전'), ('전원', '모두'),
    ('전투불능', '전투불능'), ('아군 1명', '아군1인'), ('아군 전원', '아군전체'),
    ('여기저기', '군데군데'), ('것', '거'), ('입니다', '임'), ('습니다', '음'),
]


def try_particle_drop(t, L):
    cur = t
    for p in PARTICLE_DROP:
        pat = re.compile(re.escape(p) + r'(?=[가-힣A-Za-z])')
        cand = pat.sub('', cur, count=1)
        if cand != cur and fits(cand, L):
            return cand
        if cand != cur:
            cur = cand
    return cur if fits(cur, L) else None


def try_syn(t, L):
    cur = t
    for a, b in SYN2:
        if a in cur:
            cand = cur.replace(a, b)
            if fits(cand, L):
                return cand
            cur = cand
    return cur if fits(cur, L) else None


DROPPABLE = ['정말로', '진짜로', '그야말로', '아무래도', '역시', '조금', '살짝',
             '상당히', '꽤', '아주', '완전히', '거의', '전혀', '약간']


def try_word_drop(t, L):
    words = t.split(' ')
    for w in DROPPABLE:
        if w in words:
            idx = words.index(w)
            cand = ' '.join(words[:idx] + words[idx + 1:])
            if fits(cand, L):
                return cand
    # 마지막 단어(보통 꾸밈설명)부터 통째로 삭제
    while len(words) > 1:
        words = words[:-1]
        cand = ' '.join(words)
        if fits(cand, L):
            return cand
    return None


def try_tail_trunc(t, L):
    """공백 없는 단일 토큰(고유명사): 뒤에서부터 한 글자씩 삭제."""
    cur = t
    while len(cur) > 1:
        cur = cur[:-1]
        if fits(cur, L):
            return cur
    return None


def shrink(t, L):
    if fits(t, L):
        return t, 'ok'
    c = re.sub(r' {2,}', ' ', t).rstrip()
    if fits(c, L):
        return c, 'trim'
    r = try_syn(c, L)
    if r:
        return r, 'syn'
    base = r if r is not None else c
    r = try_particle_drop(base, L)
    if r:
        return r, 'particle'
    base = r if r is not None else base
    if ' ' in base:
        r = try_word_drop(base, L)
        if r:
            return r, 'word-drop'
        base = r if r is not None else base
    r = try_tail_trunc(base, L)
    if r:
        return r, 'tail-trunc'
    return None, 'fail'


def main():
    rows = list(csv.DictReader(open('work/trans/shrink_fail.tsv', encoding='utf-8'), delimiter='\t'))
    by_file = {}
    stats = {}
    still_fail = []
    for r in rows:
        L = int(r['L'])
        new, how = shrink(r['ko'], L)
        stats[how] = stats.get(how, 0) + 1
        if new is None:
            still_fail.append(r)
            new = r['ko']
        by_file.setdefault(r['file'], []).append((r['off'], new))
    print('전략별 결과:', stats)
    print('여전히 실패:', len(still_fail))

    # 대상 tsv 에 추가 반영(append) — 기존 tsv 는 이미 fit 하는 항목만 있음
    for f, items in by_file.items():
        existing = []
        with open(f, encoding='utf-8') as fh:
            header = fh.readline()
            for line in fh:
                line = line.rstrip('\n')
                if line:
                    off, ko = line.split('\t', 1)
                    existing.append((off, ko))
        offs = {off for off, _ in existing}
        added = 0
        for off, ko in items:
            if off in offs:
                print('★이미 존재하는 오프셋(건너뜀):', f, off)
                continue
            existing.append((off, ko))
            added += 1
        existing.sort()
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write('off\tko\n')
            for off, ko in existing:
                fh.write('%s\t%s\n' % (off, ko))
        print(f, '추가', added, '건 (총', len(existing), ')')

    with open('work/trans/shrink_fail2.tsv', 'w', encoding='utf-8') as f:
        f.write('file\toff\tL\tko\n')
        for r in still_fail:
            f.write('%s\t%s\t%s\t%s\n' % (r['file'], r['off'], r['L'], r['ko']))


if __name__ == '__main__':
    main()
