# -*- coding: utf-8 -*-
"""kocodes.tsv 에 새로 필요한 한글 음절을 추가한다 (기존 624항목은 그대로 두고 append).

번역이 늘어나며(1,100 -> 2,875) 처음 계획(work/trans/slot_plan.json, 622자)에
없던 한글 음절이 나왔다. 기존 코드에 손대면 이미 확정된 번역이 깨지므로
**추가만 한다.**
"""
import csv
import sys
from collections import Counter

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_build import PUNCT_FALLBACK

KOCODES = 'work/trans/kocodes.tsv'
N_TABLE = 1504


def load_kocodes():
    codes = {}
    for line in open(KOCODES, encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            codes[int(a, 16)] = b
    return codes


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    rev = {}
    for c, ch in sorted(m.items()):
        rev.setdefault(ch, c)

    existing = load_kocodes()
    used_codes = set(existing)
    used_ko_chars = set(existing.values())

    # 현재 번역 전체(기존 완료분 + 이번 정리분)에서 실제로 쓰는 문자를 전부 모은다
    sources = ['work/trans/runs.tsv', 'work/trans/batch_clean.tsv']
    need = Counter()
    keep_asis = set()
    for path in sources:
        for r in csv.DictReader(open(path, encoding='utf-8'), delimiter='\t'):
            ko = r['ko'].strip()
            if not ko:
                continue
            for ch in ko:
                if 0xAC00 <= ord(ch) <= 0xD7A3:
                    if ch not in used_ko_chars:
                        need[ch] += 1
                else:
                    keep_asis.add(ch)

    print('신규 필요 한글 %d종' % len(need))

    # 원문 그대로 남기는 글자(・‥！？ 등)의 코드는 절대 재배정 금지
    reserved = set(used_codes)
    for ch in keep_asis:
        t = PUNCT_FALLBACK.get(ch, ch)
        if t in rev:
            reserved.add(rev[t])

    free = [c for c in range(0xD8, N_TABLE) if c not in reserved]
    print('배정 가능 2바이트 슬롯 %d개' % len(free))

    new_chars = [ch for ch, _ in need.most_common()]
    assert len(new_chars) <= len(free), '슬롯 부족: 필요 %d > 가용 %d' % (len(new_chars), len(free))

    added = list(zip(free, new_chars))
    with open(KOCODES, 'a', encoding='utf-8') as f:
        for code, ch in added:
            f.write('%03X\t%s\n' % (code, ch))

    print('추가된 항목 %d개, 코드 범위 %03X ~ %03X'
          % (len(added), added[0][0], added[-1][0]))
    print('kocodes.tsv 총 %d항목' % (len(existing) + len(added)))


if __name__ == '__main__':
    main()
