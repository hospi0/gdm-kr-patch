# -*- coding: utf-8 -*-
"""FACE2.DAT / DORAM.BIN 등 «추가로 발견한 파일»의 텍스트를 제자리 교체한다.

원문 앞에 오피코드 부스러기가 붙는 경우가 많아, 세그먼트를 디코드한 뒤
**끝에서부터 원문 키와 일치하는 지점**을 찾아 시작 바이트를 자동 계산한다.
(손으로 오프셋을 세다 틀린 적이 있어서 자동화한다)

불변식: 원문 길이 초과 금지 / 남는 자리 공백 0x20 / 구간 밖 무변화 / 크기 불변.
"""
import os
import shutil
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
from find_uncovered import decode, segments
from runs_build import encode, load_maps

SRC, DST = 'work/dm_all', 'work/build'


def main():
    import extra_ko
    rev, ko = load_maps()
    KO = extra_ko.KO
    n_ok = 0
    fails = []
    for fn, ranges in extra_ko.SPECS.items():
        src = os.path.join(SRC, fn)
        dst = os.path.join(DST, fn)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
        orig = open(src, 'rb').read()
        cur = bytearray(open(dst, 'rb').read())
        touched = []
        for lo, hi in ranges:
            for so, sl in segments(orig, lo, hi):
                t = decode(orig[so:so + sl])
                kr = None
                start = None
                # ★키의 «바이트 패턴»으로 찾는다. 디코드 문자열을 앞에서 잘라 가며
                #   맞추면 **2바이트 글자 한가운데서 시작**할 수 있다.
                #   실측 사고: 세그먼트가 ` 務ャスティン！` 로 디코드되는 자리는
                #   실제로는 [제어인수 0x14][ジ][ャ]… 이고, `ャスティン！` 로 맞추면
                #   `ジ` 의 첫 바이트가 남아 화면에 `버저스틴！` 으로 찍혔다.
                #   바이트 검색은 정렬이 보장된다 — 단 키는 «줄 전체»여야 한다.
                # ★긴 키부터 — 짧은 키가 긴 레코드의 «뒷부분»에만 맞아
                #   글자 중간부터 덮어쓰는 사고를 막는다.
                #   실측: `手動分配` 레코드에 `分配` 키가 맞아 `手動분배` 가 됐다.
                for key, val in sorted(KO.items(), key=lambda kv: -len(kv[0])):
                    try:
                        kb = B.encode_with_vars(key, {})
                    except Exception:
                        continue
                    pos = orig.find(kb, so, so + sl)
                    if pos >= 0 and pos + len(kb) == so + sl:
                        kr, start = val, pos
                        break
                if kr is None:
                    continue
                L = sl - (start - so)
                try:
                    nb = encode(kr, rev, ko)
                except Exception as e:
                    fails.append((fn, start, '인코딩 %s' % e))
                    continue
                if len(nb) > L:
                    fails.append((fn, start, '길이 초과 %dB>%dB %r' % (len(nb), L, kr)))
                    continue
                cur[start:start + L] = nb + b'\x20' * (L - len(nb))
                touched.append((start, L))
                n_ok += 1
        before = open(dst, 'rb').read()
        mask = bytearray(len(cur))
        for a, L in touched:
            mask[a:a + L] = b'\x01' * L
        for i in range(len(cur)):
            if not mask[i] and cur[i] != before[i]:
                fails.append((fn, i, '구간 밖 변경'))
                break
        assert len(cur) == len(orig), '크기 변경'
        open(dst, 'wb').write(bytes(cur))
        print('%-20s 반영 %d' % (fn, len(touched)))
    print('\n합계 %d' % n_ok)
    if fails:
        print('★실패 %d건:' % len(fails))
        for f, o, w in fails:
            print('   %-20s 0x%05X %s' % (f, o, w))


if __name__ == '__main__':
    main()
