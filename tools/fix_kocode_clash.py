# -*- coding: utf-8 -*-
"""kocodes 슬롯 충돌 교정 — 아직 쓰이는 글자의 자리를 뺏은 음절을 옮긴다.

사고: 세션8에 음절 128종을 추가하면서 예약 목록을 «가나 + 고정 문장부호»로만
잡았다. 그런데 우리 **번역문 자체가 ※ ─ ♥ 같은 기호와 일부 한자**를 그대로
쓰고 있었고, 그 글자들의 코드에 새 음절을 얹어 버렸다.
실기: 메뉴의 `※※` 가 `룡룡` 으로 나왔다.

예약 규칙(이게 정답):
  **최종 텍스트에 등장하는 모든 «한글 아닌» 글자의 코드**를 예약한다.
  원문(미번역)뿐 아니라 **우리 번역문이 쓰는 기호·한자**까지 포함해야 한다.
  [[feedback_slot_reassign_all_builders]]
"""
import csv
import glob
import os
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import codemap
from codemap_kanji_src import kanji_map
from script_build import PUNCT_FALLBACK

KOCODES = 'work/trans/kocodes.tsv'
N_TABLE = 1504


def load(p):
    out = []
    for line in open(p, encoding='utf-8'):
        s = line.rstrip('\n')
        if not s or s.startswith('#'):
            continue
        a, b = s.split('\t')[:2]
        out.append((int(a, 16), b))
    return out


def used_non_hangul():
    """최종 텍스트에 나오는 «한글 아닌» 글자 전부."""
    used = set()

    def add(t):
        for ch in t or '':
            if not ('가' <= ch <= '힣'):
                used.add(ch)

    for r in csv.DictReader(open('work/trans/runs.tsv', encoding='utf-8'), delimiter='\t'):
        add(r['ko'])
        if not (r['ko'] or '').strip():
            add(r['ja'])
    import museum_desc_ko
    import museum_ko
    import sysmenu_ko2
    import uncovered_ko
    for v in museum_ko.KO.values():
        for t in v:
            add(t)
    for v in museum_desc_ko.KO.values():
        add(v)
    for v in uncovered_ko.T.values():
        add(v[2])
    for v in sysmenu_ko2.SEG.values():
        for t in v:
            add(t)
    for p in glob.glob('work/trans/*.tsv'):
        if os.path.basename(p) in ('kocodes.tsv',):
            continue
        for line in open(p, encoding='utf-8'):
            for cell in line.rstrip('\n').split('\t'):
                add(cell)
    return used


def main():
    rows = load(KOCODES)
    m = codemap.base_map()
    m.update(kanji_map())
    rev = {}
    for c, ch in sorted(m.items()):
        rev.setdefault(ch, c)

    used = used_non_hangul()
    occupied = set()
    for ch in used:
        if ch in rev:
            occupied.add(rev[ch])
        t = PUNCT_FALLBACK.get(ch)
        if t and t in rev:
            occupied.add(rev[t])

    taken = {c for c, _ in rows}
    # ★이번 세션에 «추가한» 코드만 검사한다. 기존 827개는 원래 예약 규칙대로
    #   배정된 것이라 손대면 확정 번역이 전부 깨진다.
    old = {c for c, _ in load('work/trans/kocodes.tsv.bak_session8')}
    clash = [(c, ch) for c, ch in rows if c in occupied and c not in old]
    print('kocodes %d항목 / 사용중 비한글 %d종(코드 %d개) / 충돌 %d건'
          % (len(rows), len(used), len(occupied), len(clash)))
    if not clash:
        print('충돌 없음')
        return
    free = [c for c in range(0xD8, N_TABLE) if c not in taken and c not in occupied]
    print('가용 슬롯 %d개' % len(free))
    remap = {}
    for (c, ch), nc in zip(clash, free):
        remap[c] = nc
        print('   0x%03X %r  <- 원래 %r  =>  0x%03X (원래 %r)'
              % (c, ch, m.get(c), nc, m.get(nc)))
    with open(KOCODES, 'w', encoding='utf-8') as f:
        for c, ch in rows:
            f.write('%03X\t%s\n' % (remap.get(c, c), ch))
    print('\n%d개 재배정 완료 — ★font_apply 부터 전 빌더 재실행 필요' % len(remap))


if __name__ == '__main__':
    main()
