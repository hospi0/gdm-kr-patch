# -*- coding: utf-8 -*-
"""bintext(UI·아이템 텍스트) 번역 반영 — 후보 tsv를 개별 문자열 제자리 교체로 빌드.

사용: python tools/ui_build.py <tsv경로> <대상.BIN 파일명>
tsv 열: off(hex, 원문 오프셋) / ko

정책은 `bintext.rebuild()` 와 동일(MDT `runs_build.py` 와 같은 제자리 교체 원리):
개별 문자열은 원래 널종단 구간 길이를 넘지 않는 한도 안에서만 교체, 남는 자리는
`0x00` 패딩. 대상 밖 바이트는 절대 안 바뀐다 — 되읽기 검증에서 바이트로 확인한다.
"""
import csv
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

SRC = 'work/dm'
DST = 'work/build'


def main(tsv_path, fname):
    rev, ko = load_maps()
    trans = {}
    for r in csv.DictReader(open(tsv_path, encoding='utf-8'), delimiter='\t'):
        trans[int(r['off'], 16)] = r['ko']

    d = open(os.path.join(SRC, fname), 'rb').read()
    try:
        nb = B.rebuild(d, trans, ko)
    except (KeyError, ValueError) as e:
        print('실패:', e)
        return 1

    if len(nb) != len(d):
        print('★크기 변경 %d -> %d (있으면 안 됨)' % (len(d), len(nb)))
        return 1

    os.makedirs(DST, exist_ok=True)
    open(os.path.join(DST, fname), 'wb').write(nb)
    print('%s 갱신 완료 (%d B, 크기 불변)' % (fname, len(nb)))

    # 되읽기 검증 — 바이트로 비교한다(문자로 비교하면 슬롯 재배정 탓에 틀어진다)
    bad = 0
    for off, ko_text in trans.items():
        j = off
        while j < len(d) and d[j] != 0:
            j += 1
        L = j - off
        enc = B.encode_with_vars(ko_text, ko)
        want = enc + b'\x20' * (L - len(enc))   # ★공백 패딩(널 금지) — bintext.rebuild 주석 참조
        got = nb[off:off + L]
        if got != want:
            bad += 1
            print('  ★불일치 @0x%X  want=%s got=%s' % (off, want.hex(' '), got.hex(' ')))

    # 대상 밖(미번역) 바이트는 원본과 완전히 같아야 한다
    outside = bytearray(len(nb))
    for off in trans:
        j = off
        while j < len(d) and d[j] != 0:
            j += 1
        for i in range(off, j):
            outside[i] = 1
    leak = sum(1 for i in range(len(nb)) if not outside[i] and nb[i] != d[i])
    print('되읽기 검증: %s (반영 %d건 중 불일치 %d) / 대상 밖 변경 %d바이트'
          % ('통과' if bad == 0 and leak == 0 else '실패', len(trans), bad, leak))
    return 1 if (bad or leak) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
