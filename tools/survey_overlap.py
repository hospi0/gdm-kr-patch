# -*- coding: utf-8 -*-
"""본편 Grandia 영문패치(SSP)의 대상 파일 목록과 Digital Museum 디스크의
파일 목록이 얼마나 겹치는지 센다.

목적: 영문패치를 오라클로 쓸 수 있는 경계를 확정한다.
같은 이름이어도 내용은 다를 수 있으므로, 여기서는 '이름 겹침'만 판정한다.
"""
import sys
import os
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

SSP = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
       r'/SS_Grandia_EN_v1.1.1/SS_Grandia_v1.1.1.SSP')
TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')


def main():
    z = zipfile.ZipFile(SSP)
    do = z.read('driveOrder.txt').decode()
    gr = set()
    for line in do.splitlines():
        if not line.strip():
            continue
        gr.add(line.split(',')[0].replace(chr(92), '/'))

    buf = I.load_track(TRACK1)
    dm = {k.lstrip('/'): v for k, v in I.list_files(buf).items()}

    common = sorted(gr & set(dm))
    print('Grandia CD1 대상 파일 %d개 / DM 파일 %d개 / 이름 공통 %d개'
          % (len(gr), len(dm), len(common)))
    for c in common:
        print('  %-24s DM size=%d' % (c, dm[c][1]))

    print()
    print('-- DM에만 있는 이름 (상위 40) --')
    for c in sorted(set(dm) - gr)[:40]:
        print('  %-24s size=%d' % (c, dm[c][1]))


if __name__ == '__main__':
    main()
