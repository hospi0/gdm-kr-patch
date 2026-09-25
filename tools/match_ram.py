# -*- coding: utf-8 -*-
"""세이브스테이트의 Work RAM 안에서 디스크 파일이 어디에 적재됐는지 찾는다.

각 파일의 특징적인 조각(선두 32 B와 중간 32 B)을 RAM에서 검색한다.
어떤 파일이 상주 중인지 알면 그 화면이 무엇인지, 그리고 폰트를 어느
파일에서 찾아야 하는지가 좁혀진다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')


def main():
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    rams = {}
    for tag in ('WorkRAMH', 'WorkRAML', 'VRAM', 'VRAM_1'):
        p = 'work/state/%s.bin' % tag
        if os.path.exists(p):
            rams[tag] = open(p, 'rb').read()

    print('%-26s %-9s %s' % ('파일', '크기', 'RAM 적재 위치'))
    for path, (lba, size) in sorted(files.items()):
        if size < 512 or size > 8 << 20:
            continue
        d = I.read_range(buf, lba, min(size, 4096))
        # 선두 48 B 중 0이 아닌 부분을 지문으로 쓴다
        probe = d[:48]
        if probe.count(0) > 40:
            probe = d[256:304]
        if probe.count(0) > 40:
            continue
        found = []
        for tag, r in rams.items():
            k = r.find(probe)
            if k >= 0:
                found.append('%s+0x%06X' % (tag, k))
        if found:
            print('%-26s %-9d %s' % (path, size, ', '.join(found)))


if __name__ == '__main__':
    main()
