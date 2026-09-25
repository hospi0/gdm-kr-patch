# -*- coding: utf-8 -*-
"""BBG의 BE32 섹션 표를 풀어, 여러 BBG에서 '같은 내용의 섹션'을 찾는다.

오프셋이 파일마다 달라도 섹션 단위로는 같을 수 있으므로 해시로 대조한다.
"""
import hashlib
import os
import sys
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')


def sections(d):
    offs = []
    i = 0
    while i + 4 <= len(d):
        v = struct.unpack_from('>I', d, i)[0]
        if offs and not (offs[-1] <= v <= len(d)):
            break
        if not offs and not (4 <= v <= len(d)):
            return []
        offs.append(v)
        i += 4
        if offs[0] <= i:
            break
    ends = offs[1:] + [len(d)]
    return list(zip(offs, ends))


def main():
    buf = I.load_track(TRACK1)
    f = I.list_files(buf)
    names = ['/BATLE/B001.BBG', '/BATLE/B014.BBG', '/BATLE/B255.BBG',
             '/BATLE/BTEST.BBG', '/FIELD/B000.BBG']
    tabs = {}
    for n in names:
        if n not in f:
            continue
        d = I.read_range(buf, *f[n])
        secs = sections(d)
        tabs[n] = (d, secs)
        print('%-20s %7d B  섹션 %d개: %s'
              % (n, len(d), len(secs),
                 [('0x%X:%d' % (s, e - s)) for s, e in secs][:10]))
    print()
    # 섹션 해시 교집합
    hashes = {}
    for n, (d, secs) in tabs.items():
        hs = {}
        for k, (s, e) in enumerate(secs):
            hs[hashlib.md5(d[s:e]).hexdigest()] = (k, s, e)
        hashes[n] = hs
    base = names[0]
    common = set(hashes[base])
    for n in names[1:]:
        if n in hashes:
            common &= set(hashes[n])
    print('모든 BBG에 공통인 섹션 %d개' % len(common))
    d0 = tabs[base][0]
    for h in sorted(common, key=lambda h: -(hashes[base][h][2] - hashes[base][h][1])):
        k, s, e = hashes[base][h]
        nz = sum(1 for x in d0[s:e] if x)
        print('  섹션#%-2d 0x%06X-0x%06X %7d B  비영 %5.1f%%'
              % (k, s, e, e - s, 100.0 * nz / max(1, e - s)))


if __name__ == '__main__':
    main()
