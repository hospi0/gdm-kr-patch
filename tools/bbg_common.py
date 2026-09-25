# -*- coding: utf-8 -*-
"""서로 다른 전투배경(BBG) 파일에서 '바이트가 동일한 긴 구간'을 찾는다.

배경 그림은 파일마다 달라야 하므로, 여러 BBG에 똑같이 들어 있는 큰 덩어리는
공유 자산(UI·폰트 등)이다. 영문패치가 모든 BBG의 같은 오프셋을 고친 것과
같은 현상을 DM 안에서 독립적으로 확인하는 것이 목적이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')


def common_runs(a, b, minlen=512):
    n = min(len(a), len(b))
    out = []
    i = 0
    while i < n:
        if a[i] == b[i]:
            j = i
            while j < n and a[j] == b[j]:
                j += 1
            if j - i >= minlen:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def main():
    buf = I.load_track(TRACK1)
    f = I.list_files(buf)
    names = ['/BATLE/B001.BBG', '/BATLE/B014.BBG', '/BATLE/B255.BBG']
    data = [I.read_range(buf, *f[n]) for n in names]
    runs = common_runs(data[0], data[1])
    # 세 번째 파일에도 같은 구간이 동일한지 확인해 잡음을 걸러낸다
    keep = []
    for s, e in runs:
        if e <= len(data[2]) and data[0][s:e] == data[2][s:e]:
            keep.append((s, e))
    print('B001 %d B / B014 %d B / B255 %d B' % tuple(len(d) for d in data))
    print('3개 모두 동일한 512B 이상 구간: %d개' % len(keep))
    tot = 0
    for s, e in keep:
        nz = sum(1 for x in data[0][s:e] if x)
        print('  0x%06X-0x%06X  %7d B  비영 %5.1f%%' % (s, e, e - s, 100.0 * nz / (e - s)))
        tot += e - s
    print('합계 %d B' % tot)
    os.makedirs('work/dm', exist_ok=True)
    open('work/dm/BATLE_B001.BBG', 'wb').write(data[0])


if __name__ == '__main__':
    main()
