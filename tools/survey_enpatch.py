# -*- coding: utf-8 -*-
"""영문패치 CD-1/CD-2 SSP(내부 ZIP)가 교체하는 파일 목록을 뽑고,
Digital Museum 디스크와 이름·크기를 대조한다.

판정 목적:
  - 영문패치가 손댄 파일 = 본편에서 텍스트·폰트·그래픽 텍스트가 사는 곳(오라클).
  - DM에 같은 이름이 있고 크기까지 같으면 같은 자산일 가능성이 높다 → 우선 조사 대상.
"""
import sys
import os
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
BS = chr(92)


KINDS = ('._DFR', '._RPL', '._NEW', '._TRK')


def entries(path):
    """{디스크상 경로: (종류, 패치엔트리 크기)}  종류 = DFR/RPL/NEW/TRK/기타"""
    z = zipfile.ZipFile(path)
    out = {}
    for n in z.namelist():
        p = n.replace(BS, '/')
        kind = 'other'
        for k in KINDS:
            if p.endswith(k):
                kind, p = k[2:], p[:-len(k)]
                break
        out[p] = (kind, z.getinfo(n).file_size)
    return out


def main():
    cd1 = entries('work/en/CD-1.SSP')
    cd2 = entries('work/en/CD-2.SSP')
    print('CD-1 교체 항목 %d / CD-2 교체 항목 %d' % (len(cd1), len(cd2)))

    buf = I.load_track(TRACK1)
    dm = {k.lstrip('/'): v for k, v in I.list_files(buf).items()}

    import collections
    print('CD-1 종류별:', collections.Counter(k for k, _ in cd1.values()))
    print('CD-2 종류별:', collections.Counter(k for k, _ in cd2.values()))

    print()
    print('== CD-1에서 전체교체(_RPL)/신규(_NEW)/트랙(_TRK) 항목 ==')
    for n, (k, s) in sorted(cd1.items()):
        if k in ('RPL', 'NEW', 'TRK', 'other'):
            mark = 'DM있음' if n in dm else '-'
            print('  [%-5s] %-28s patch=%-9d %s' % (k, n, s, mark))

    hit = sorted(n for n in cd1 if n in dm)
    print()
    print('== 영문패치 대상 ∩ DM 파일: %d개 ==' % len(hit))
    for n in hit:
        k, s = cd1[n]
        print('  [%-3s] %-24s DM_size=%d' % (k, n, dm[n][1]))


if __name__ == '__main__':
    main()
