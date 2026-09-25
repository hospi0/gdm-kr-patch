# -*- coding: utf-8 -*-
"""디스크 섹터와 매치되지 않는 RAM 상주 구간(=런타임 생성/해제 데이터)을 찾는다.

폰트가 압축 저장돼 있다면 디스크 원본과 바이트가 다르므로 섹터 매치에 잡히지 않는다.
따라서 '내용은 꽉 찼는데 출처가 없는 구간'이 해제된 폰트의 유력 후보다.
그 구간에만 글리프 검출기를 걸어 후보를 좁힌다.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I
from map_sectors import sector_index, KEY, STEP

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
BASE = {'WorkRAML_sw': 0x00200000, 'WorkRAMH_sw': 0x06000000}


def main():
    log = open('work/uncovered.txt', 'w', encoding='utf-8')

    def say(s):
        print(s, flush=True)
        log.write(s + '\n')
        log.flush()

    t = time.time()
    buf = I.load_track(TRACK1)
    idx = sector_index(buf, len(buf) // I.SECTOR)
    say('섹터 색인 %d개 (%.1fs)' % (len(idx), time.time() - t))

    for tag in ('WorkRAMH_sw', 'WorkRAML_sw'):
        mem = open('work/state_b/%s.bin' % tag, 'rb').read()
        n = len(mem)
        covered = bytearray(n)
        for i in range(0, n - KEY, STEP):
            if bytes(mem[i:i + KEY]) in idx:
                # 매치된 섹터는 2048 B가 통째로 적재됐다고 본다
                for j in range(i, min(i + I.DATA_LEN, n)):
                    covered[j] = 1
        # 내용이 있는데 출처가 없는 구간
        runs = []
        i = 0
        while i < n:
            if not covered[i] and mem[i]:
                j = i
                zero = 0
                while j < n and not covered[j] and zero < 256:
                    zero = zero + 1 if mem[j] == 0 else 0
                    j += 1
                s, e = i, j - zero
                if e - s >= 2048:
                    runs.append((s, e))
                i = j
            else:
                i += 1
        runs.sort(key=lambda r: -(r[1] - r[0]))
        say('')
        say('== %s : 출처 없는 상주 구간 %d개 (큰 순 20)' % (tag, len(runs)))
        for s, e in runs[:20]:
            seg = mem[s:e]
            nz = sum(1 for x in seg if x)
            say('   0x%06X-0x%06X %8dB  버스 0x%08X  비영 %4.1f%%'
                % (s, e, e - s, BASE[tag] + s, 100.0 * nz / (e - s)))
    log.close()


if __name__ == '__main__':
    main()
