# -*- coding: utf-8 -*-
"""MDT 대사 전수 감사 — **미추출 / 미번역 / 불완전 번역**을 한 번에 찾는다.

세 가지를 구분해서 센다:
  A. 미추출  : `extract_runs` 가 찾은 런인데 `runs.tsv` 에 없는 것
               → 번역 파이프라인이 아예 모르는 문장. 화면에서 깨진다.
  B. 미번역  : tsv 에 있는데 ko 가 비어 있는 것 → 역시 깨진다.
  C. 불완전  : ko 가 있으나 의심스러운 것
               · ja 대비 너무 짧다(글자수 비 < 0.45)
               · ko 에 일본어 글자가 남아 있다
               · ko 가 조사 없이 끝나는 등 깨진 흔적(`들어오 건`, `마누라뿐라`)
                 → 여기선 **길이비·잔류 일본어**만 기계적으로 잡고, 어색한
                   한국어는 사람이 볼 목록으로 뽑는다.

★ ko 가 실제로 화면에서 깨지는지는 "그 문장이 한글 슬롯을 쓰는 JP 글자를
  포함하는가"로 판정한다(미번역이면 무조건 깨짐).
"""
import os
import re
import sys

sys.path.insert(0, 'tools')
import extract_runs as ER

TSV = 'work/trans/runs.tsv'
DM = 'work/dm'


def load_tsv():
    out = {}
    with open(TSV, encoding='utf-8') as f:
        for line in f:
            a = line.rstrip('\n').split('\t')
            if len(a) < 4:
                continue
            fname, off, ln, ja = a[0], a[1], a[2], a[3]
            ko = a[4] if len(a) > 4 else ''
            out[(fname, off.upper())] = (ja, ko)
    return out


JP_RE = re.compile(r'[぀-ヿ一-鿿]')


def main():
    tsv = load_tsv()
    unextracted, untranslated, suspicious = [], [], []
    total = 0
    for fn in sorted(os.listdir(DM)):
        if not fn.endswith('.MDT'):
            continue
        short = fn[6:]                       # FIELD_E810.MDT -> E810.MDT
        d = open(os.path.join(DM, fn), 'rb').read()
        try:
            o, s, runs = ER.extract(d, short)
        except Exception as e:
            print('  ! %s 추출 실패 %s' % (short, e))
            continue
        for off, ln, codes in runs:
            total += 1
            key = (short, '%05X' % off)
            ja = ER.text(codes)
            if key not in tsv:
                unextracted.append((short, off, ja))
                continue
            _ja, ko = tsv[key]
            if not ko.strip():
                untranslated.append((short, off, ja))
                continue
            why = []
            if JP_RE.search(ko):
                why.append('일본어잔류')
            cj = len(re.sub(r'\s', '', ja))
            ck = len(re.sub(r'\s', '', ko))
            if cj >= 6 and ck / cj < 0.45:
                why.append('너무짧음 %d/%d' % (ck, cj))
            if why:
                suspicious.append((short, off, ja, ko, ','.join(why)))

    print('MDT 런 총 %d개' % total)
    print('  A. 미추출   %d' % len(unextracted))
    print('  B. 미번역   %d' % len(untranslated))
    print('  C. 의심     %d' % len(suspicious))

    with open('work/trans/audit_runs.txt', 'w', encoding='utf-8') as f:
        f.write('=== A. 미추출 (파이프라인이 모르는 문장 — 화면에서 깨짐) %d ===\n' % len(unextracted))
        for s_, o_, ja in unextracted:
            f.write('%-12s %05X  %s\n' % (s_, o_, ja))
        f.write('\n=== B. 미번역 (ko 비어 있음) %d ===\n' % len(untranslated))
        for s_, o_, ja in untranslated:
            f.write('%-12s %05X  %s\n' % (s_, o_, ja))
        f.write('\n=== C. 의심 (불완전 가능) %d ===\n' % len(suspicious))
        for s_, o_, ja, ko, why in suspicious:
            f.write('%-12s %05X  [%s]\n    JA %s\n    KO %s\n' % (s_, o_, why, ja, ko))
    print('\nwork/trans/audit_runs.txt 저장')


if __name__ == '__main__':
    main()
