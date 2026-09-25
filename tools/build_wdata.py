# -*- coding: utf-8 -*-
"""`FIELD/WDATA.DAT` 제자리 교체 빌더.

번역 출처 2개를 이 순서로 합친다:
  1. 기존 TEXT2 번역(`ui_full_field/batle.tsv`) — 원문이 같으면 그대로 재사용
     ([[feedback_reuse_existing_work]]). 이름 93%·설명 66%·마법 85%가 여기서 덮인다.
  2. `work/trans/wdata_ko.py` — 1번이 못 덮은 233건

불변식: 원문 길이 초과 금지 / 남는 자리 공백 0x20 / 구간 밖 무변화 / 크기 불변.
"""
import csv
import os
import shutil
import struct
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
import codemap
from find_uncovered import decode, segments
from runs_build import encode, load_maps

SRC, DST = 'work/dm_all', 'work/build'
FN = 'FIELD_WDATA.DAT'
SECTIONS = (3, 4, 7, 8)

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)


def isjp(c):
    return c in HIRA or c in KATA or 0x4E00 <= ord(c) <= 0x9FFF


def text2_dict():
    out = {}
    for tsv, binf in (('work/trans/ui_full_field.tsv', 'FIELD_TEXT2.BIN'),
                      ('work/trans/ui_full_batle.tsv', 'BATLE_TEXT2.BIN')):
        d = open('work/dm/' + binf, 'rb').read()
        for r in csv.DictReader(open(tsv, encoding='utf-8'), delimiter='\t'):
            off = int(r['off'], 16)
            ko = (r['ko'] or '').strip()
            if not ko:
                continue
            j = off
            while j < len(d) and d[j] != 0:
                j += 1
            out.setdefault(B.decode(d[off:j]), ko)
    return out


def main():
    import wdata_ko
    rev, ko = load_maps()
    DIC = text2_dict()
    n_reuse = len(DIC)
    DIC2 = dict(wdata_ko.KO)

    src = os.path.join(SRC, FN)
    dst = os.path.join(DST, FN)
    if not os.path.exists(dst):
        shutil.copyfile(src, dst)
    orig = open(src, 'rb').read()
    cur = bytearray(open(dst, 'rb').read())
    before = bytes(cur)
    hdr = [struct.unpack_from('>I', orig, i * 4)[0] for i in range(13)]

    touched = []
    fails = []
    n_from = {'TEXT2재사용': 0, 'wdata_ko': 0}
    n_miss = []
    for k in SECTIONS:
        lo, hi = hdr[k], hdr[k + 1]
        for so, sl in segments(orig, lo, hi):
            t = decode(orig[so:so + sl])
            if sl < 2 or sum(1 for c in t if isjp(c)) < 2 or '�' in t:
                continue
            cands = DIC2.get(t)
            tag = 'wdata_ko'
            if cands is None:
                cands = DIC.get(t)
                tag = 'TEXT2재사용'
            if cands is None:
                n_miss.append((so, t))
                continue
            # 값은 문자열 또는 «후보 리스트» — 앞에서부터 예산에 맞는 첫 것을 쓴다
            if isinstance(cands, str):
                cands = [cands]
            nb = None
            why = ''
            for c in cands:
                try:
                    e = encode(c, rev, ko)
                except Exception as ex:
                    why = '인코딩 %s  %r' % (ex, c)
                    continue
                if len(e) <= sl:
                    nb, kr = e, c
                    break
                why = '길이 초과 %dB>%dB %r  <- %r' % (len(e), sl, c, t)
            if nb is None:
                fails.append((so, why))
                continue
            cur[so:so + sl] = nb + b'\x20' * (sl - len(nb))
            touched.append((so, sl))
            n_from[tag] += 1

    mask = bytearray(len(cur))
    for a, L in touched:
        mask[a:a + L] = b'\x01' * L
    outside = sum(1 for i in range(len(cur)) if not mask[i] and cur[i] != before[i])
    assert len(cur) == len(orig), '크기 변경'
    assert outside == 0, '구간 밖 %d바이트 변경' % outside
    open(dst, 'wb').write(bytes(cur))
    print('%s 반영 %d (TEXT2재사용 %d / 신규 %d)  사전 %d개  크기 %d  구간밖변경 0'
          % (FN, len(touched), n_from['TEXT2재사용'], n_from['wdata_ko'], n_reuse, len(cur)))
    if n_miss:
        print('★번역없음 %d건:' % len(n_miss))
        for so, t in n_miss[:20]:
            print('   0x%05X %s' % (so, t))
    if fails:
        print('★실패 %d건:' % len(fails))
        for so, w in fails:
            print('   0x%05X %s' % (so, w))


if __name__ == '__main__':
    main()
