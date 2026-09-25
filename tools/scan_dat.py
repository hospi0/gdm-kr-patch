# -*- coding: utf-8 -*-
"""`.DAT` 그래픽 컨테이너를 전수 파싱한다.

관측된 구조(EDFNT.DAT / LOGO.DAT / TTL.DAT / TITL.DAT 공통):
    [BE32 섹션 오프셋 표][섹션 …]
  섹션 중 크기 512 B인 것은 RGB555 256색 팔레트로 보인다.

여기서는 '어떤 파일이 이 구조를 따르는가'와 '섹션 크기 분포'만 판정한다.
섹션 내용이 무엇인지는 렌더로 따로 확인한다.
"""
import os
import sys
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')


def parse_table(d):
    """선두 BE32 오름차순 오프셋 표를 읽는다. 실패하면 None."""
    offs = []
    i = 0
    while i + 4 <= len(d):
        v = struct.unpack_from('>I', d, i)[0]
        if offs:
            if not (offs[-1] < v <= len(d)):
                break
        else:
            if not (4 <= v <= len(d)):
                return None
        offs.append(v)
        i += 4
        if offs[0] <= i:
            break
    if not offs or offs[0] != i:
        return None            # 표 크기와 첫 섹션 시작이 맞아야 한다
    return offs


def main():
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    out = open('work/scan_dat.txt', 'w', encoding='utf-8')
    hits = 0
    for path, (lba, size) in sorted(files.items()):
        if not path.endswith(('.DAT', '.BIN', '.STB', '.GEF', '.CPD')):
            continue
        if size < 64 or size > 8 << 20:
            continue
        d = I.read_range(buf, lba, min(size, 1 << 20))
        offs = parse_table(d)
        if not offs:
            continue
        hits += 1
        ends = offs[1:] + [size]
        sizes = [e - s for s, e in zip(offs, ends)]
        pal = sum(1 for x in sizes if x == 512)
        out.write('%-26s size=%-9d 섹션 %d개  팔레트(512B) %d개\n'
                  % (path, size, len(offs), pal))
        out.write('   섹션크기: %s%s\n'
                  % (sizes[:14], ' …' if len(sizes) > 14 else ''))
    out.close()
    print('컨테이너 구조 일치 %d개 → work/scan_dat.txt' % hits)


if __name__ == '__main__':
    main()
