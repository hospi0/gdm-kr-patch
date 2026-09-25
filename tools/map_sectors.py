# -*- coding: utf-8 -*-
"""디스크 전 섹터를 색인해, RAM에 상주 중인 블록의 출처를 전수 판정한다.

앞선 map_loaded는 '파일당 지문 몇 개'만 봐서 놓치는 파일이 많았다.
여기서는 **모든 섹터**(193,620개)의 선두 24 B를 색인하고 RAM을 훑으므로,
적재된 파일은 그 파일의 어느 섹터든 걸리면 잡힌다.

주의(메모리 [[reference_iso_read_past_track_end]]): 로그는 파이프 없이
파일로 직접 쓴다. 파이프를 물리면 진행이 보이지 않는다.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
KEY = 24
STEP = 4
RAMS = ['WorkRAML_sw', 'WorkRAMH_sw', 'WorkRAML', 'WorkRAMH', 'VRAM', 'VRAM_1']
BASE = {'WorkRAML': 0x00200000, 'WorkRAML_sw': 0x00200000,
        'WorkRAMH': 0x06000000, 'WorkRAMH_sw': 0x06000000,
        'VRAM': 0x25C00000, 'VRAM_1': 0x25E00000}


def sector_index(buf, nsec):
    """{섹터 선두 24B: LBA} — 잡음(거의 0, 단일값 반복)과 중복 키는 제외."""
    idx = {}
    dup = set()
    for lba in range(nsec):
        off = lba * I.SECTOR + I.DATA_OFF
        k = bytes(buf[off:off + KEY])
        if len(k) < KEY:
            break
        if k.count(0) > KEY - 8 or len(set(k)) < 4:
            continue
        if k in idx:
            dup.add(k)          # 여러 섹터에 중복 → 식별력 없음
            continue
        idx[k] = lba
    for k in dup:
        idx.pop(k, None)
    return idx


def make_lookup(table):
    """LBA → (파일, 파일내 섹터번호) 를 이분탐색으로. table은 LBA 오름차순."""
    import bisect
    starts = [v[0] for _, v in table]

    def lookup(lba):
        i = bisect.bisect_right(starts, lba) - 1
        if i < 0:
            return None, 0
        path, (flba, size) = table[i]
        n = (size + I.DATA_LEN - 1) // I.DATA_LEN
        if flba <= lba < flba + n:
            return path, lba - flba
        return None, 0

    return lookup


def main():
    log = open('work/map_sectors.txt', 'w', encoding='utf-8')

    def say(s):
        print(s, flush=True)
        log.write(s + '\n')
        log.flush()

    t = time.time()
    buf = I.load_track(TRACK1)
    nsec = len(buf) // I.SECTOR
    files = I.list_files(buf)
    table = sorted(((p, v) for p, v in files.items()), key=lambda kv: kv[1][0])
    say('트랙 %d섹터, 파일 %d개 (%.1fs)' % (nsec, len(files), time.time() - t))
    lookup = make_lookup(table)

    t = time.time()
    idx = sector_index(buf, nsec)
    say('섹터 색인 %d개 (%.1fs)' % (len(idx), time.time() - t))

    for tag in RAMS:
        p = 'work/state_b/%s.bin' % tag
        if not os.path.exists(p):
            continue
        mem = open(p, 'rb').read()
        t = time.time()
        hits = []
        for i in range(0, len(mem) - KEY, STEP):
            lba = idx.get(bytes(mem[i:i + KEY]))
            if lba is not None:
                hits.append((i, lba))
        say('')
        say('== %s : 섹터 일치 %d건 (%.1fs)' % (tag, len(hits), time.time() - t))
        # 파일 단위로 묶어 '적재 시작 주소'를 낸다 (한 번만 순회)
        best, cnt = {}, {}
        for addr, lba in hits:
            path, sec = lookup(lba)
            if not path:
                continue
            cnt[path] = cnt.get(path, 0) + 1
            start = addr - sec * I.DATA_LEN
            cur = best.get(path)
            if cur is None or start < cur:
                best[path] = start
        for path, start in sorted(best.items(), key=lambda kv: kv[1]):
            say('   %-26s @ +0x%06X  (버스 0x%08X)  섹터일치 %d'
                % (path, start & 0xFFFFFF, BASE.get(tag, 0) + start, cnt[path]))
    log.close()


if __name__ == '__main__':
    main()
