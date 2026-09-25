# -*- coding: utf-8 -*-
"""kocodes.tsv 에 **박물관 번역이 새로 필요로 하는 음절**을 추가한다 (append only).

세션7의 「827 음절 벽」은 하드 한계가 아니었다 — 그때까지 배정한 개수일 뿐,
글리프표는 1,504칸이고 실측 여유 슬롯이 600개 이상 남아 있다.
기존 코드는 절대 건드리지 않는다(이미 확정된 번역이 깨진다).

예약(재배정 금지):
  · 기존 kocodes 전부
  · **최종 빌드에 원문으로 남는 텍스트**가 쓰는 문자 — `runs.tsv` 의 ko 빈칸 행
  · 가나 전체 + 문장부호
⚠️ GM3.STZ(압축) 안의 명장면 목록은 열거할 수 없다. 그쪽은 이미 미번역이라
   판독 불가 상태이므로 슬롯 재활용으로 더 나빠질 것이 없다고 판단했다.
"""
import csv
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import codemap
from codemap_kanji_src import kanji_map
from expand_kocodes import KOCODES, N_TABLE, load_kocodes

PUNCT_KEEP = '・‥…～！？「」『』（）♥♪♩○◆★§：、。'


def reserved_codes(existing):
    m = codemap.base_map()
    m.update(kanji_map())
    rev = {}
    for c, ch in sorted(m.items()):
        rev.setdefault(ch, c)
    res = set(existing)
    keep = set()
    for r in csv.DictReader(open('work/trans/runs.tsv', encoding='utf-8'), delimiter='\t'):
        if not (r['ko'] or '').strip():
            keep.update(r['ja'])
    keep.update(codemap.HIRA)
    keep.update(codemap.KATA)
    keep.update(PUNCT_KEEP)
    for ch in keep:
        if ch in rev:
            res.add(rev[ch])
    return res


def needed(existing):
    import museum_ko
    import museum_desc_ko
    have = set(existing.values())
    out = []
    cand_lists = list(museum_ko.KO.values())
    cand_lists += [[v] for v in museum_desc_ko.KO.values()]
    for cands in cand_lists:
        for t in cands:
            for ch in t:
                if '가' <= ch <= '힣' and ch not in have and ch not in out:
                    out.append(ch)
    return out


def main():
    existing = load_kocodes()
    res = reserved_codes(existing)
    free = [c for c in range(0xD8, N_TABLE) if c not in res]
    new = needed(existing)
    print('추가 필요 음절 %d종: %s' % (len(new), ' '.join(new)))
    print('가용 슬롯 %d개' % len(free))
    if len(new) > len(free):
        raise SystemExit('슬롯 부족')
    if not new:
        print('추가 없음')
        return
    with open(KOCODES, 'a', encoding='utf-8') as f:
        for code, ch in zip(free, new):
            f.write('%03X\t%s\n' % (code, ch))
    print('추가 %d개 (0x%03X ~ 0x%03X), kocodes 총 %d항목'
          % (len(new), free[0], free[len(new) - 1], len(existing) + len(new)))


if __name__ == '__main__':
    main()
