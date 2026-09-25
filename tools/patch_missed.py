# -*- coding: utf-8 -*-
"""런으로 안 잡힌 조각을 **직접 오프셋으로** 기록한다.

`runs_build.py` 는 extract() 가 돌려준 런만 처리하므로 이 조각들은 그 경로로는
절대 반영되지 않는다(세션7에 45건이 통째로 유실됐다). 여기서는 텍스트 구간의
base 를 구해 `base + off` 에 직접 쓴다.

불변식:
  1. 원문 슬롯 길이를 **넘으면 실패** (조용히 자르지 않는다)
  2. 남는 자리는 공백 0x20 (널 금지)
  3. 지정한 구간 **밖은 단 한 바이트도** 바뀌지 않는다
  4. 파일 크기 불변
  5. 원본 바이트가 표에 적힌 원문과 **정확히 일치**할 때만 기록 (오프셋 오류 차단)
"""
import os
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
from extract_runs import extract
from find_uncovered import decode
from runs_build import encode, load_maps

SRC, DST = 'work/dm', 'work/build'


def main():
    import uncovered_ko
    rev, ko = load_maps()
    byfile = {}
    for (f, off), (L, ja, kr) in uncovered_ko.T.items():
        byfile.setdefault(f, []).append((off, L, ja, kr))

    n_ok = 0
    fails = []
    for f, items in sorted(byfile.items()):
        p_src = os.path.join(SRC, 'FIELD_' + f)
        p_dst = os.path.join(DST, 'FIELD_' + f)
        orig = open(p_src, 'rb').read()
        cur = bytearray(open(p_dst, 'rb').read() if os.path.exists(p_dst) else orig)
        base, s, _ = extract(orig, f)
        touched = []
        for off, L, ja, kr in sorted(items):
            got = decode(orig[base + off:base + off + L])
            if got != ja:
                fails.append((f, off, '원문 불일치: %r != %r' % (got, ja)))
                continue
            try:
                nb = encode(kr, rev, ko)
            except Exception as e:
                fails.append((f, off, '인코딩 실패 %s' % e))
                continue
            if len(nb) > L:
                fails.append((f, off, '길이 초과 %dB > %dB  %r' % (len(nb), L, kr)))
                continue
            a = base + off
            cur[a:a + L] = nb + b'\x20' * (L - len(nb))
            touched.append((a, L))
            n_ok += 1
        # 불변식 3: 지정 구간 밖 무변화
        before = open(p_dst, 'rb').read() if os.path.exists(p_dst) else orig
        mask = bytearray(len(cur))
        for a, L in touched:
            mask[a:a + L] = b'\x01' * L
        for i in range(len(cur)):
            if not mask[i] and cur[i] != before[i]:
                fails.append((f, i, '구간 밖 변경'))
                break
        assert len(cur) == len(orig)
        open(p_dst, 'wb').write(bytes(cur))
        print('%-10s 반영 %d/%d' % (f, len(touched), len(items)))

    print('\n합계 반영 %d / %d' % (n_ok, len(uncovered_ko.T)))
    if fails:
        print('★실패 %d건:' % len(fails))
        for f, off, why in fails:
            print('   %-10s +0x%05X  %s' % (f, off, why))


if __name__ == '__main__':
    main()
