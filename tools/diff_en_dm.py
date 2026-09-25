# -*- coding: utf-8 -*-
"""DM 원본 파일 ↔ 영문패치 교체본을 바이트 대조해 '다른 구간(run)'을 뽑는다.

메모리 교훈 [[feedback_use_existing_translation_patch_as_oracle]]:
기존 타국어 패치 diff는 폰트·텍스트 위치를 한 방에 알려준다.

주의: DM과 본편 Grandia는 서로 다른 게임이므로 같은 이름·같은 크기라도
내용이 같다는 보장이 없다. 여기서는 '얼마나 같은가'를 먼저 측정해
오라클로 쓸 수 있는 파일인지부터 판정한다.
"""
import os

PAIRS = [
    ('work/dm/BIN_MES1B.DAT', 'work/en/rpl/CD-1_BIN_MES1B.DAT'),
    ('work/dm/BIN_MES1C.DAT', 'work/en/rpl/CD-1_BIN_MES1C.DAT'),
    ('work/dm/BIN_SWN5M.DAT', 'work/en/rpl/CD-1_BIN_SWN5M.DAT'),
    ('work/dm/FIELD_SWN6M.DAT', 'work/en/rpl/CD-1_FIELD_SWN6M.DAT'),
    ('work/dm/BIN_SCNRL.BIN', 'work/en/rpl/CD-1_BIN_SCNRL.BIN'),
    ('work/dm/BIN_SWN9M.DAT', 'work/en/rpl/CD-1_BIN_SWN9M.DAT'),
    ('work/dm/BATLE_TEXT2.BIN', 'work/en/rpl/CD-1_BATLE_TEXT2.BIN'),
]


def runs(a, b):
    """다른 바이트의 연속 구간 [(start, end)] (end 미포함)"""
    n = min(len(a), len(b))
    out = []
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def main():
    for pa, pb in PAIRS:
        if not (os.path.exists(pa) and os.path.exists(pb)):
            print('건너뜀 (파일 없음): %s' % pa)
            continue
        a = open(pa, 'rb').read()
        b = open(pb, 'rb').read()
        n = min(len(a), len(b))
        rs = runs(a, b)
        ndiff = sum(e - s for s, e in rs)
        print('== %s  vs  %s' % (os.path.basename(pa), os.path.basename(pb)))
        print('   크기 DM=%d EN=%d  겹치는 %d B 중 다름 %d B (%.1f%%), 구간 %d개'
              % (len(a), len(b), n, ndiff, 100.0 * ndiff / n if n else 0, len(rs)))
        for s, e in rs[:8]:
            print('     0x%06X-0x%06X (%d B)  DM:%s  EN:%s'
                  % (s, e, e - s, a[s:min(e, s + 12)].hex(), b[s:min(e, s + 12)].hex()))
        if len(rs) > 8:
            print('     ... 외 %d 구간' % (len(rs) - 8))
        print()


if __name__ == '__main__':
    main()
