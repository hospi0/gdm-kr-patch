# -*- coding: utf-8 -*-
"""원본(패치 안 된) ISO에서 아직 안 뽑은 모든 파일을 뒤져 `道具` 패턴이 있는
파일을 전수로 찾는다. 필요하면 그 자리에서 work/dm/ 로 추출까지 한다."""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
import iso9660 as I

M = codemap.base_map()
M.update(kanji_map())
REV = {}
for c, ch in sorted(M.items()):
    REV.setdefault(ch, c)


def enc(s):
    out = bytearray()
    for ch in s:
        c = REV[ch]
        if c < 0xE0:
            out.append(c + 0x20)
        else:
            k = c - 0xE0
            out += bytes((0x10 + k // 256, k % 256))
    return bytes(out)


SRC = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
       r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')

table = {}
for line in open('work/filelist.txt', encoding='cp949', errors='replace'):
    if 'lba=' not in line:
        continue
    a = line.split()
    if 'DIR' in a:
        continue
    lba = size = None
    for t in a[1:]:
        if t.startswith('lba='):
            lba = int(t[4:])
        elif t.startswith('size='):
            size = int(t[5:])
    if lba is not None and size is not None:
        table[a[0]] = (lba, size)

pat = enc('道具')
print('패턴', pat.hex(' '), '파일 수', len(table))

have = set()
for fn in os.listdir('work/dm'):
    if os.path.isfile('work/dm/' + fn) and '_' in fn:
        d, n = fn.split('_', 1)
        have.add('/%s/%s' % (d, n))

print('전체 파일을 메모리로 읽는 중 (455MB)…', flush=True)
whole = open(SRC, 'rb').read()
print('로드 완료, 슬라이싱 시작', flush=True)

import numpy as np
wbuf = np.frombuffer(whole, dtype=np.uint8)

hits = []
skipped_big = []
for path, (lba, size) in sorted(table.items()):
    if path in have:
        continue
    if size > 2_000_000:            # ★텍스트 코퍼스는 지금까지 전부 수백KB 이하였다
        skipped_big.append((path, size))
        continue
    nsec = -(-size // I.DATA_LEN)
    starts = lba * I.SECTOR + I.DATA_OFF + np.arange(nsec) * I.SECTOR
    idx = starts[:, None] + np.arange(I.DATA_LEN)[None, :]
    got = wbuf[idx].tobytes()[:size]
    if pat in got:
        cnt = got.count(pat)
        hits.append((path, lba, size, cnt))
        print('★찾음: %-30s lba=%-7d size=%-8d 개수=%d' % (path, lba, size, cnt), flush=True)
print('\n총 %d개 파일에서 발견 (2MB 넘어서 건너뛴 파일 %d개)' % (len(hits), len(skipped_big)), flush=True)
for p, sz in skipped_big:
    print('  건너뜀(큼): %-30s %d B' % (p, sz), flush=True)
