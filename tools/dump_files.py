# -*- coding: utf-8 -*-
"""조사용 덤프: (a) 영문패치의 _RPL/_NEW 원본 바이트, (b) DM 디스크의 지정 파일.

원본 디스크 자산은 저장소에 커밋하지 않는다(work/ 는 .gitignore 대상).
"""
import sys
import os
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
BS = chr(92)


def dump_en(kinds=('_RPL', '_NEW')):
    os.makedirs('work/en/rpl', exist_ok=True)
    for cd in ('CD-1', 'CD-2'):
        z = zipfile.ZipFile('work/en/%s.SSP' % cd)
        for n in z.namelist():
            p = n.replace(BS, '/')
            for k in kinds:
                if p.endswith('.' + k):
                    out = 'work/en/rpl/%s_%s' % (cd, p[:-len(k) - 1].replace('/', '_'))
                    with open(out, 'wb') as f:
                        f.write(z.read(n))
                    print('EN %-6s %-28s -> %s (%d B)'
                          % (k, p, os.path.basename(out), os.path.getsize(out)))


def dump_dm(names):
    os.makedirs('work/dm', exist_ok=True)
    buf = I.load_track(TRACK1)
    files = {k.lstrip('/'): v for k, v in I.list_files(buf).items()}
    for n in names:
        if n not in files:
            print('DM  없음  %s' % n)
            continue
        lba, size = files[n]
        data = I.read_range(buf, lba, size)
        out = 'work/dm/' + n.replace('/', '_')
        with open(out, 'wb') as f:
            f.write(data)
        print('DM  %-28s -> %s (%d B)' % (n, os.path.basename(out), size))


if __name__ == '__main__':
    dump_en()
    dump_dm(['BATLE/TEXT2.BIN', 'BIN/MES1B.DAT', 'BIN/MES1C.DAT',
             'BIN/SCNRL.BIN', 'BIN/SWN5M.DAT', 'BIN/SWN5B.DAT',
             'BIN/SWN9M.DAT', 'BIN/SWN9B.DAT',
             'FIELD/SWN6M.DAT', 'FIELD/SWN6B.DAT',
             'FIELD/TEXT2.BIN', 'FIELD/MTMES.DAT', 'FIELD/WMESS.DAT',
             'BIN/SYS_T.STB', 'FIELD/SYS_F.STB', 'BATLE/SYS_B.STB',
             'FIELD/TITL.DAT', 'BIN/TITLE.BIN'])
