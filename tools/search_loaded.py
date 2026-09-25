# -*- coding: utf-8 -*-
"""캐시된 파일 지문을 RAM/VRAM에서 찾아 '파일 → 적재주소' 표를 만든다.

Work RAM은 세이브스테이트에 16비트 스왑되어 저장되므로 스왑본도 함께 본다
(선행 프로젝트 shining-kr-patch/docs/03_dynamic_vram.md).
"""
import os
import pickle

RAMS = ['WorkRAML', 'WorkRAMH', 'WorkRAML_sw', 'WorkRAMH_sw', 'VRAM', 'VRAM_1']
BASE = {'WorkRAML': 0x00200000, 'WorkRAML_sw': 0x00200000,
        'WorkRAMH': 0x06000000, 'WorkRAMH_sw': 0x06000000,
        'VRAM': 0x25C00000, 'VRAM_1': 0x25E00000}


def main():
    probes = pickle.load(open('work/probes.pkl', 'rb'))
    print('지문 %d개' % len(probes))
    out = open('work/map_loaded.txt', 'w', encoding='utf-8')
    for tag in RAMS:
        p = 'work/state_b/%s.bin' % tag
        if not os.path.exists(p):
            continue
        mem = open(p, 'rb').read()
        hits = {}
        for probe, (path, foff) in probes.items():
            k = mem.find(probe)
            if k >= 0:
                # 파일 선두 기준 적재 주소로 환산
                start = k - foff
                cur = hits.get(path)
                if cur is None or start < cur[0]:
                    hits[path] = (start, foff)
        if not hits:
            print('== %-11s 일치 없음' % tag)
            continue
        print('== %s : %d개 파일 적재 확인' % (tag, len(hits)))
        out.write('== %s ==\n' % tag)
        for path, (start, foff) in sorted(hits.items(), key=lambda kv: kv[1][0]):
            line = '   %-26s @ +0x%06X  (버스 0x%08X)' % (
                path, start, BASE.get(tag, 0) + start)
            print(line)
            out.write(line + '\n')
    out.close()


if __name__ == '__main__':
    main()
