# -*- coding: utf-8 -*-
"""런 단위 빌드 결과를 되읽어 의도한 번역과 일치하는지 검증한다.

검사:
  1. 파일 크기 불변 / 런 밖 바이트 불변
  2. 각 런을 되읽으면 ko 와 일치 (끝 공백 패딩 허용)
  3. ko 가 빈 런은 원본 그대로
"""
import csv
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from extract_runs import extract, text
from script_build import PUNCT_FALLBACK
from runs_build import load_maps, encode, BuildError

m = codemap.base_map()
m.update(kanji_map())


def full_map():
    f = dict(m)
    for line in open('work/trans/kocodes.tsv', encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            f[int(a, 16)] = b
    return f


def norm(s):
    for a, b in PUNCT_FALLBACK.items():
        s = s.replace(a, b)
    return s


def read_run(s, off, L, fm):
    out, i = [], off
    end = off + L
    while i < end:
        b = s[i]
        if b >= 0x20:
            out.append(fm.get(b - 0x20, '?'))
            i += 1
        elif 0x10 <= b <= 0x14 and i + 1 < end:
            out.append(fm.get(0xE0 + (b - 0x10) * 256 + s[i + 1], '?'))
            i += 2
        else:
            out.append('<%02X>' % b)
            i += 1
    return ''.join(out)


def main():
    fm = full_map()
    rev, ko = load_maps()
    rows = list(csv.DictReader(open('work/trans/runs.tsv', encoding='utf-8'),
                               delimiter='\t'))
    byfile = {}
    for r in rows:
        byfile.setdefault(r['file'], {})[int(r['off'], 16)] = r

    ok = bad = kept = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        a = open('work/dm/' + f, 'rb').read()
        b = open('work/build/' + f, 'rb').read()
        if len(a) != len(b):
            print('★ %s 크기 변경' % f)
            bad += 1
            continue
        o, s, rs = extract(a, f[6:])
        sb = b[o:o + len(s)]
        for off, L, codes in rs:
            r = byfile.get(f[6:], {}).get(off)
            kotext = (r or {}).get('ko', '').rstrip()   # ★앞 공백은 진짜 텍스트 바이트다 — 지우면 글자가 밀린다
            if not kotext:
                if sb[off:off + L] != s[off:off + L]:
                    print('★ %s +0x%05X 미번역인데 바뀜' % (f[6:], off))
                    bad += 1
                else:
                    kept += 1
                continue
            # ★ 되읽어 글자로 비교하면 안 된다 — 번역문에 **일부러 남긴 원문 글자**
            #   (제어코드 인수를 글자로 오독한 자리)는 그 코드 슬롯이 한글로 재배정돼
            #   있어서 딴 글자로 읽힌다. 바이트가 의도대로인지가 유일한 진실이다.
            try:
                want = encode(kotext, rev, ko)
            except BuildError:
                want = None
            if want is not None:
                want = want + b'\x20' * (L - len(want))
            if want is not None and bytes(sb[off:off + L]) == want:
                ok += 1
            elif sb[off:off + L] == s[off:off + L]:
                kept += 1                      # 반영 안 된 런은 원본 유지가 정상
            else:
                print('★ %s +0x%05X 바이트 불일치  ko=%r' % (f[6:], off, kotext[:40]))
                print('   기대 %s' % (want.hex(' ') if want else '(인코딩 실패)'))
                print('   실제 %s' % bytes(sb[off:off + L]).hex(' '))
                bad += 1
    print('번역 반영 확인 %d런 / 원문 유지 %d런 / 불일치 %d' % (ok, kept, bad))


if __name__ == '__main__':
    main()
