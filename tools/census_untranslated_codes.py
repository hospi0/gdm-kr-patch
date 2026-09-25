# -*- coding: utf-8 -*-
"""§15.4 — 미번역 구간이 실제로 쓰는 글리프 코드를 전수 계산한다.

폰트 슬롯 재활용 방식이라(codemap 원본 글자 위에 한글을 다시 그린다), 미번역
대사가 참조하는 코드가 `kocodes.tsv`에 이미 한글로 재배정돼 있으면 화면에
깨져 보인다(실측 사례: E800.MDT +0x3E1 `はい！` 미번역 → 화면에 `안다!`로 표시,
§17 후속 — `안다` 는 실은 は・い・！ 코드가 한글 슬롯을 새로 참조한 것).

이 도구는 `work/trans/runs.tsv`(현재 추출 corpus)를 기준으로
  - 번역된 런이 쓰는 코드 집합 A
  - 미번역 런이 쓰는 코드 집합 B
을 나누고, `kocodes.tsv`가 재배정한 코드 집합 K 와 B 의 교집합
(= **지금 화면에서 깨지고 있는 코드**)을 낸다.

⚠️ 커버리지 한계: runs.tsv 는 `extract_runs.extract()`(번역대상 필터 통과)만
   담는다. 필터에서 걸러진 매우 짧은/노이즈성 런은 이 계산에 안 잡힌다 —
   그런 자리는 실기에 나타나도 원래도 아주 짧아 눈에 덜 띈다.
"""
import csv
import os
import sys

sys.path.insert(0, 'tools')
from extract_runs import extract
from script_budget import script_section

KOCODES = 'work/trans/kocodes.tsv'
RUNS = 'work/trans/runs.tsv'


def load_kocodes():
    codes = {}
    for line in open(KOCODES, encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            codes[int(a, 16)] = b
    return codes


def main():
    kocodes = load_kocodes()
    ko_set = set(kocodes)

    tr_status = {}
    with open(RUNS, encoding='utf-8') as fp:
        for r in csv.DictReader(fp, delimiter='\t'):
            tr_status[(r['file'], r['off'])] = bool(r['ko'].strip())

    used_tr, used_untr = set(), set()
    untr_chars = 0
    per_file_hits = {}

    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        name = f[6:]
        d = open('work/dm/' + f, 'rb').read()
        o, s, rs = extract(d)
        for off, L, codes in rs:
            key = (name, '%05X' % off)
            translated = tr_status.get(key, False)
            if translated:
                used_tr.update(codes)
            else:
                used_untr.update(codes)
                untr_chars += len(codes)
                hit = [c for c in codes if c in ko_set]
                if hit:
                    per_file_hits.setdefault(name, 0)
                    per_file_hits[name] += len(hit)

    clobbered = used_untr & ko_set
    print('번역된 런이 쓰는 코드 종류: %d' % len(used_tr))
    print('미번역 런이 쓰는 코드 종류: %d (글자 %d자)' % (len(used_untr), untr_chars))
    print('한글로 재배정된 코드 종류: %d' % len(ko_set))
    print()
    print('★ 미번역 런이 쓰는데 이미 한글로 덮인 코드: %d종' % len(clobbered))
    print()
    print('파일별 영향받는 글자수 (상위 15):')
    for name, n in sorted(per_file_hits.items(), key=lambda x: -x[1])[:15]:
        print('  %-14s %d자' % (name, n))
    print()
    print('영향받는 코드 목록 (앞 30개, 코드=한글배정):')
    for c in sorted(clobbered)[:30]:
        print('  0x%03X -> %r' % (c, kocodes[c]))

    with open('work/trans/clobbered_codes.tsv', 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t')
        w.writerow(['code_hex', 'ko_assigned'])
        for c in sorted(clobbered):
            w.writerow(['%03X' % c, kocodes[c]])
    print()
    print('저장: work/trans/clobbered_codes.tsv (%d행)' % len(clobbered))


if __name__ == '__main__':
    main()
