# -*- coding: utf-8 -*-
"""폰트 코덱 전수 왕복 검증.

통과 기준 (하나라도 어기면 실패):
  1. 모든 코드에서 encode(decode(레코드)) 가 **원본 레코드 바이트와 완전히 같다**
     → 원본이 최소 인코딩이며 우리 인코더가 그걸 재현한다는 뜻
  2. 표를 통째로 다시 지은 블롭이 **원본 구간 바이트와 완전히 같다**
     → 오프셋표 재작성·레코드 공유 규칙까지 재현한다는 뜻
  3. 픽셀 변환 raw ↔ rows 가 왕복한다
"""
import struct
import sys

sys.path.insert(0, 'tools')
import font_codec as C

PATH = 'work/dm/BIN_FDATA.BIN'


def check_region(d, base, name):
    n = C.table_count(d, base)
    ok = fail = 0
    first_fail = None
    recs, seen_off = [], {}
    for i in range(n):
        off = C.entry_offset(d, base, i)
        rec = base + off
        raw, ln = C.decode_record(d, rec)
        orig = d[rec:rec + ln]
        again = C.encode_record(raw)
        if again == orig:
            ok += 1
        else:
            fail += 1
            if first_fail is None:
                first_fail = (i, off, orig.hex(), again.hex())
        recs.append(orig)
        seen_off.setdefault(off, i)
    print('%s: 항목 %d개' % (name, n))
    print('  (1) 레코드 왕복 일치 %d / 불일치 %d' % (ok, fail))
    if first_fail:
        i, off, a, b = first_fail
        print('      첫 불일치 코드 0x%X (오프셋 0x%X)' % (i, off))
        print('        원본 %s' % a)
        print('        재생 %s' % b)

    # (2) 전체 재구성
    blob = C.build(recs)
    end = max(C.entry_offset(d, base, i) + C.decode_record(d, base + C.entry_offset(d, base, i))[1]
              for i in range(n))
    orig_region = d[base:base + end]
    same = blob == orig_region
    print('  (2) 구간 전체 재구성 %s (원본 %d B / 재생 %d B)'
          % ('일치' if same else '불일치', len(orig_region), len(blob)))
    if not same:
        for k in range(min(len(blob), len(orig_region))):
            if blob[k] != orig_region[k]:
                print('      첫 차이 +0x%X: 원본 %02X ≠ 재생 %02X' % (k, orig_region[k], blob[k]))
                break
    return fail == 0 and same


def check_pixels(d):
    n = C.table_count(d, C.FULL_BASE)
    bad = 0
    for code in range(n):
        raw = C.glyph_full(d, code)
        if C.rows_to_raw(C.raw_to_rows(raw)) != raw:
            bad += 1
    print('(3) 픽셀 변환 왕복 불일치 %d / %d' % (bad, n))
    return bad == 0


def main():
    d = open(PATH, 'rb').read()
    r1 = check_region(d, C.FULL_BASE, '전각(+0xA00)')
    r2 = check_region(d, C.HALF_BASE, '반각(+0x000)')
    r3 = check_pixels(d)
    print()
    print('판정: %s' % ('통과' if (r1 and r2 and r3) else '실패'))
    return 0 if (r1 and r2 and r3) else 1


if __name__ == '__main__':
    sys.exit(main())
