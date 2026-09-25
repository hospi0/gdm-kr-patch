# -*- coding: utf-8 -*-
"""이벤트 스크립트 섹션을 분석해 **절대 오프셋 점프가 있는지** 판정한다.

이게 갈리면 번역 재삽입 정책이 갈린다.
  - 점프가 있으면 텍스트 길이를 바꿀 때 전부 재계산해야 한다
  - 없으면 MDT 헤더의 섹션 오프셋만 고치면 된다

방법: 섹션을 BE16 워드열로 보고
  (a) 워드 빈도 → 자주 쓰이는 오피코드 후보
  (b) 값이 **자기 섹션 범위 안**에 드는 워드의 분포
      진짜 오프셋이면 파일이 달라져도 **그 파일의 섹션 크기에 맞춰** 값이 바뀐다
      → 여러 MDT를 비교하면 잡음과 구분된다
"""
import struct
import sys
from collections import Counter

MDT = 'work/dm/FIELD_E800.MDT'


def sections(d):
    out = []
    for i in range(64):
        a, b = struct.unpack_from('>II', d, i * 8)
        if a == 0 and b == 0:
            break
        if (a >> 24) == 0xFF or b == 0 or b > len(d):
            continue
        off = a & 0xFFFFFF
        if off + b <= len(d):
            out.append((i, a >> 24, off, b))
    return out


def find_script(d):
    """텍스트 종결자 07 + 메시지 시작 0F 03 이 가장 많은 섹션"""
    best = None
    for i, t, off, ln in sections(d):
        s = d[off:off + ln]
        n = s.count(b'\x0f\x03') + s.count(b'\x0a\x0c')
        if best is None or n > best[0]:
            best = (n, i, t, off, ln)
    return best


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else MDT
    d = open(path, 'rb').read()
    n, idx, t, off, ln = find_script(d)
    print('%s' % path)
    print('스크립트 섹션 = 레코드 %d (타입 %02X) 0x%06X ~ 0x%06X, %d B, 메시지마커 %d개'
          % (idx, t, off, off + ln, ln, n))
    s = d[off:off + ln]

    words = [struct.unpack_from('>H', s, i)[0] for i in range(0, len(s) - 1, 2)]
    print()
    print('== 자주 나오는 BE16 워드 20개 ==')
    for w, c in Counter(words).most_common(20):
        print('  0x%04X  %d회' % (w, c))

    print()
    print('== 값이 섹션 범위 안(0~0x%X)에 드는 워드 ==' % ln)
    inrange = [(i * 2, w) for i, w in enumerate(words) if 0 < w < ln]
    print('  %d개 / 전체 %d워드 (%.1f%%)' % (len(inrange), len(words),
                                            100.0 * len(inrange) / len(words)))
    # 기대 잡음: 균등하다면 ln/65536
    print('  균등 가정 기대치 %.1f%%' % (100.0 * ln / 65536))

    print()
    print('== 절대 파일 오프셋(0x%X~0x%X)에 드는 워드 ==' % (off, off + ln))
    absr = [(i * 2, w) for i, w in enumerate(words) if off <= w < off + ln]
    print('  %d개 (%.1f%%), 균등 기대치 %.1f%%'
          % (len(absr), 100.0 * len(absr) / len(words), 100.0 * ln / 65536))

    print()
    print('== 앞머리 64바이트 (라벨/포인터표 여부) ==')
    for a in range(0, 64, 16):
        print('  +%04X  %s' % (a, ' '.join('%02X' % b for b in s[a:a + 16])))


if __name__ == '__main__':
    main()
