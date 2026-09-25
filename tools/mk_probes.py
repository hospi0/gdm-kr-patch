# -*- coding: utf-8 -*-
"""디스크 파일 지문 캐시를 만든다(진행상황을 즉시 출력)."""
import pickle
import sys
import time

sys.path.insert(0, 'tools')
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')

t = time.time()
buf = I.load_track(TRACK1)
files = I.list_files(buf)
print('로드 %.1fs, %d파일' % (time.time() - t, len(files)), flush=True)

t = time.time()
probes = {}
for n, (path, (lba, size)) in enumerate(sorted(files.items())):
    if size < 256:
        continue
    if n % 40 == 0:
        print('  %d/%d  %.1fs  %s' % (n, len(files), time.time() - t, path), flush=True)
    head = I.read_range(buf, lba, min(size, 8192))
    for off in (0, 64, 256, 1024, 4096):
        if off + 24 > len(head):
            break
        p = bytes(head[off:off + 24])
        if p.count(0) > 18:
            continue
        probes.setdefault(p, (path, off))
print('지문 %d개, %.1fs' % (len(probes), time.time() - t), flush=True)
pickle.dump(probes, open('work/probes.pkl', 'wb'))
print('저장 완료', flush=True)
