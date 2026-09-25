# -*- coding: utf-8 -*-
"""비트맵 자산의 진짜 행 stride를 추측 대신 실측한다.

방법: 후보 stride S마다 바이트열을 S폭 행렬로 접고, 세로로 이웃한 행끼리의
바이트 상관(같은 열에서 값이 이어지는 정도)을 잰다. 진짜 stride에서
세로 상관이 뚜렷하게 커진다. 이미지가 아니면 어느 S도 튀지 않는다.
"""
import sys


def vertical_score(d, s):
    """행렬로 접었을 때 세로 이웃 바이트가 '둘 다 0' 또는 '둘 다 비0'인 비율."""
    n = (len(d) // s) * s
    if n < s * 4:
        return 0.0
    agree = tot = 0
    for i in range(n - s):
        a, b = d[i], d[i + s]
        agree += (a == 0) == (b == 0)
        tot += 1
    return agree / tot if tot else 0.0


def main(path, lo=4, hi=260, off=0, length=None):
    d = open(path, 'rb').read()
    d = d[off:off + length] if length else d[off:]
    base = sum(1 for x in d if x == 0) / len(d)
    base = base * base + (1 - base) ** 2   # 무작위 배치에서 기대되는 일치율
    res = [(vertical_score(d, s), s) for s in range(lo, hi + 1)]
    res.sort(reverse=True)
    print('%s  (%d B, 0바이트 비율 기반 기대치 %.3f)' % (path, len(d), base))
    print('상위 stride 후보:')
    for sc, s in res[:12]:
        print('   stride %3d B  세로일치 %.3f  (기대 대비 +%.3f)' % (s, sc, sc - base))


if __name__ == '__main__':
    a = sys.argv
    main(a[1], off=int(a[2], 0) if len(a) > 2 else 0,
         length=int(a[3], 0) if len(a) > 3 else None)
