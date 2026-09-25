# -*- coding: utf-8 -*-
"""sec4_10 UI 번역 중 예산 초과분을 자동 축약. MDT용 auto_shrink.py 는 대사체
필러(정말로/역시 등) 대상이라 이 짧은 스탯태그·이름 코퍼스엔 안 맞음 — 자체
동의어표+구조 축약을 시도하고, 그래도 안 들어가면 실패 목록만 낸다(수작업용).
"""
import csv
import json
import re
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()


def fits(t, L):
    try:
        return len(B.encode_with_vars(t, KO)) <= L
    except KeyError:
        return False


def enc_len(t):
    try:
        return len(B.encode_with_vars(t, KO))
    except KeyError:
        return 99999


# 동의어(긴말→짧은말), 순서대로 시도
SYN = [
    ('화염', '불'), ('폭렬', '폭발'), ('눈보라', '냉기'), ('상당히 ', ''), ('꽤 ', ''),
    ('조금 ', '살짝 '), ('살짝 ', ''), ('약간 ', ''), ('아주 ', ''), ('정말 ', ''),
    ('그럭저럭', '그런대로'), ('의외로 ', ''), ('불가사의한', '신기한'), ('신기한', '희한한'),
    ('되어 있다', '됐다'), ('있는가', '있나'), ('되었다', '됐다'), ('그렇게', '그리'),
    ('것 같다', '듯하다'), ('것 같은', '듯한'), ('것 같아', '듯해'), ('하고 있다', '한다'),
    ('붙어 있다', '달렸다'), ('달려 있다', '달렸다'), ('붙어있는', '달린'),
    ('붙어 있는', '달린'), ('되어 있는', '된'), ('만들어져 있다', '만들었다'),
    ('것 같지 않다', '아닌 듯'), ('만드는', '만든'), ('되지 않는다', '안 된다'),
    ('당하지 않는다', '안 당한다'), ('걸리지 않게 된다', '안 걸린다'),
    ('걸리지 않는다', '안 걸린다'), ('하지 않는다', '안 한다'), ('하지 않게 된다', '안 하게 된다'),
    ('날아가지 않는다', '안 날아간다'), (' 효과가 있다', ' 효과'), (' 효과 있음', ' 효과'),
    ('전 상태이상', '전상태'), ('전 마법내성', '전마내성'), ('전상태이상', '전상태'),
    ('내성 레벨', '내성'), ('레벨을', '레벨'), (' 최강의', ' 최강'), ('레벨十', '렙十'),
    ('저스틴', '저스틴'), ('것이', '게'), ('것을', '걸'), ('것은', '건'),
    ('전투 중 ', '전투중 '), ('의 것', '거'), ('사용하는', '쓰는'), ('사용된', '쓴'),
    ('전해 주자', '전해주자'), ('것 같은데', '듯한데'), ('사냥꾼', '사냥꾼'),
]

# 단어 단위 삭제(뒤에서부터 시도) — 공백 구분 다중 단어 항목에서 덜 중요한 수식어부터
DROPPABLE_WORDS = ['정말로', '진짜로', '그야말로', '아무래도', '역시', '조금', '살짝',
                    '상당히', '꽤', '아주', '완전히', '거의', '전혀']


def try_word_drop(t, L):
    words = t.split(' ')
    for w in DROPPABLE_WORDS:
        if w in words:
            idx = words.index(w)
            cand = ' '.join(words[:idx] + words[idx + 1:])
            if fits(cand, L):
                return cand
    return None


def try_syn(t, L):
    cur = t
    for a, b in SYN:
        if a in cur:
            cand = cur.replace(a, b)
            if fits(cand, L):
                return cand
            cur = cand
    return cur if fits(cur, L) else None


def shrink(t, L):
    if fits(t, L):
        return t, 'ok'
    c = re.sub(r' {2,}', ' ', t).rstrip()
    if c != t and fits(c, L):
        return c, 'trim'
    r = try_syn(c, L)
    if r:
        return r, 'syn'
    r = try_word_drop(c, L)
    if r:
        return r, 'word-drop'
    r2 = try_syn(c, L)  # syn 결과가 안 맞았어도 축약된 상태로 word-drop 재시도
    base = r2 if r2 else c
    r = try_word_drop(base, L)
    if r:
        return r, 'syn+word-drop'
    return None, 'fail'


def process(tsv_path, bin_path):
    d = open(bin_path, 'rb').read()
    rows = list(csv.DictReader(open(tsv_path, encoding='utf-8'), delimiter='\t'))
    out = []
    fails = []
    changed = 0
    for r in rows:
        off = int(r['off'], 16)
        j = off
        while j < len(d) and d[j] != 0:
            j += 1
        L = j - off
        t = r['ko']
        if fits(t, L):
            out.append((r['off'], t))
            continue
        new, how = shrink(t, L)
        if new is None:
            fails.append((r['off'], L, t, enc_len(t)))
            out.append((r['off'], t))   # 실패해도 원문 유지(수작업 대상 표시)
        else:
            out.append((r['off'], new))
            changed += 1
    with open(tsv_path, 'w', encoding='utf-8') as f:
        f.write('off\tko\n')
        for off, ko in out:
            f.write('%s\t%s\n' % (off, ko))
    print('%s: 축약 %d건, 실패 %d건' % (tsv_path, changed, len(fails)))
    return fails


if __name__ == '__main__':
    all_fails = []
    for tsv, bin_ in [('work/trans/ui_sec4_10_field.tsv', 'work/dm/FIELD_TEXT2.BIN'),
                      ('work/trans/ui_sec4_10_batle.tsv', 'work/dm/BATLE_TEXT2.BIN')]:
        all_fails += [(tsv,) + f for f in process(tsv, bin_)]
    print('\n총 실패(수작업 필요) %d건' % len(all_fails))
    with open('work/trans/shrink_fail.tsv', 'w', encoding='utf-8') as f:
        f.write('file\toff\tL\tko\tenc_len\n')
        for tsv, off, L, ko, el in all_fails:
            f.write('%s\t%s\t%d\t%s\t%d\n' % (tsv, off, L, ko, el))
