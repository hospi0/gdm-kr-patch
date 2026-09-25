# -*- coding: utf-8 -*-
"""메뉴 라벨(道具 등)의 **진짜 출처를 디스크 전체 스캔으로** 찾는다.

배경: §20 에서 `道具` 를 FIELD/BATLE_TEXT2.BIN + 37개 파일에서 찾아 고쳤는데도
실기 메뉴는 여전히 `령또`(=道具 가 한글 슬롯으로 렌더된 깨진 모습)로 나온다.
= **아직 못 찾은 출처가 더 있다.** §20.8 은 2MB 넘는 대용량 파일 7개
(MGDAT.BIN 10.6MB, M_DAT.BIN 26.7MB, GM3.STZ 248MB 등)를 "텍스트일 리 없다"는
추정으로 건너뛰고 "완전 확인 아님"이라고 적어 뒀다 — 그 추정을 검증한다.

방법: 파일 목록을 믿지 않고 **Track 1 이미지(455MB) 전체를 MODE1/2352 섹터
사용자데이터만 이어붙인 평면 이미지로 만들어** 패턴을 찾은 뒤, 히트 위치를
역으로 LBA→파일로 매핑한다. (§20.10 교훈: 파일별 seek+read 루프는 대용량에서
비정상적으로 느리다 → 통째로 읽어 numpy 로 스트라이핑)
"""
import os
import sys

import numpy as np

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map

M = codemap.base_map()
M.update(kanji_map())
REV = {}
for _c, _ch in sorted(M.items()):
    REV.setdefault(_ch, _c)

SRC = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
       r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
SECTOR, DATA_OFF, DATA_LEN = 2352, 16, 2048


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


def load_flat():
    """전체 트랙을 읽어 각 섹터의 사용자데이터 2048B만 이어붙인 평면 이미지."""
    raw = np.fromfile(SRC, dtype=np.uint8)
    n = len(raw) // SECTOR
    raw = raw[:n * SECTOR].reshape(n, SECTOR)
    flat = raw[:, DATA_OFF:DATA_OFF + DATA_LEN].reshape(-1)
    return flat.tobytes(), n


def load_filetable():
    """work/filelist.txt → [(path, lba, size)] (LBA 오름차순)"""
    out = []
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
            out.append((a[0], lba, size))
    out.sort(key=lambda x: x[1])
    return out


def owner(files, lba):
    """이 LBA 를 포함하는 파일을 찾는다."""
    lo, hi = 0, len(files) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if files[mid][1] <= lba:
            best = files[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return None
    p, l, s = best
    nsec = (s + DATA_LEN - 1) // DATA_LEN
    return best if l <= lba < l + nsec else ('(파일밖/시스템영역)', l, s)


def find_all(hay, needle):
    out = []
    i = hay.find(needle)
    while i != -1:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def main():
    words = sys.argv[1:] or ['道具', '使う', 'ロード', 'セーブ']
    print('트랙 로드 중 (455MB)…', flush=True)
    flat, nsec = load_flat()
    print('  섹터 %d개 / 평면 %d B' % (nsec, len(flat)))
    files = load_filetable()
    print('  파일표 %d개' % len(files))

    for w in words:
        try:
            pat = enc(w)
        except KeyError as e:
            print('\n=== %r : 인코딩 불가 %s (폰트에 없는 글자)' % (w, e))
            continue
        hits = find_all(flat, pat)
        print('\n=== %r  (바이트 %s)  히트 %d개' % (w, pat.hex(), len(hits)))
        # 파일별로 묶어서 보고
        per = {}
        for off in hits:
            lba = off // DATA_LEN
            o = owner(files, lba)
            key = o[0] if o else '?'
            per.setdefault(key, []).append(off)
        for k in sorted(per, key=lambda k: -len(per[k])):
            offs = per[k]
            # 파일 내 상대 오프셋
            o = next((f for f in files if f[0] == k), None)
            rels = []
            for off in offs[:6]:
                if o:
                    rels.append('0x%X' % (off - o[1] * DATA_LEN))
                else:
                    rels.append('abs 0x%X' % off)
            print('  %-28s %4d회  예: %s' % (k, len(offs), ', '.join(rels)))


if __name__ == '__main__':
    main()
