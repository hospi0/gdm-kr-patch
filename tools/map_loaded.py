# -*- coding: utf-8 -*-
"""Work RAM(swap16 복원)과 VRAM에서 '어느 디스크 파일이 어디에 적재됐는지' 찾는다.

Shining 프로젝트에서 폰트를 찾은 경로와 같다:
파일→로드주소 대응이 잡히면, 폰트 파일도 그 표에서 드러난다.

메모리 교훈(Shining 03_dynamic_vram.md): 세이브스테이트의 Work RAM은
**16비트 바이트스왑**되어 저장된다. 스왑하지 않으면 아무것도 매치되지 않는다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
PROBE = 24          # 지문 길이
STEP = 2            # RAM 훑는 간격


def build_probes(buf, files):
    """{지문바이트: (파일, 파일내오프셋)} — 파일마다 여러 지점에서 딴다."""
    probes = {}
    for path, (lba, size) in files.items():
        if size < 256:
            continue
        head = I.read_range(buf, lba, min(size, 8192))
        for off in (0, 64, 256, 1024, 4096):
            if off + PROBE > len(head):
                break
            p = bytes(head[off:off + PROBE])
            if p.count(0) > PROBE - 6:      # 거의 0인 지문은 잡음
                continue
            probes.setdefault(p, (path, off))
    return probes


def search(mem, probes, tag, out):
    """지문마다 bytes.find로 찾는다(C 속도).

    ⚠️ 이전 판은 RAM을 1바이트씩 밀며 파이썬 dict를 조회했다. 같은 결과를
    수백 배 느리게 얻는 방식이라 밤새 돌려도 끝나지 않았다. 방향을 뒤집는다.
    """
    hits = {}
    for p, (path, off) in probes.items():
        k = mem.find(p)
        if k >= 0 and path not in hits:
            hits[path] = (k, off)
    for path, (addr, off) in sorted(hits.items(), key=lambda kv: kv[1][0]):
        line = '%-11s +0x%06X  ← %-26s (파일오프셋 0x%X)' % (tag, addr, path, off)
        print(line)
        out.write(line + '\n')


def main():
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    probes = build_probes(buf, files)
    print('지문 %d개 준비' % len(probes))
    out = open('work/map_loaded.txt', 'w', encoding='utf-8')
    for tag in ('WorkRAMH_sw', 'WorkRAML_sw', 'WorkRAMH', 'WorkRAML',
                'VRAM', 'VRAM_1'):
        p = 'work/state_b/%s.bin' % tag
        if not os.path.exists(p):
            continue
        search(open(p, 'rb').read(), probes, tag, out)
    out.close()


if __name__ == '__main__':
    main()
