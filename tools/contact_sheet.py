# -*- coding: utf-8 -*-
"""파일 전체를 1bpp(또는 4bpp) 이미지로 통째 렌더해 폰트 구간을 눈으로 찾는다.

검출기보다 사람 눈이 정확하다. 폰트 시트는 일정한 간격의 글자 격자로 보인다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_png import png_gray
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')


def render_1bpp(data, width_px, max_rows=None):
    stride = width_px // 8
    rows = []
    n = len(data) // stride
    if max_rows:
        n = min(n, max_rows)
    for y in range(n):
        line = bytearray()
        for xb in range(stride):
            b = data[y * stride + xb]
            for k in range(7, -1, -1):
                line.append(255 if (b >> k) & 1 else 0)
        rows.append(line)
    return rows


def main():
    targets = sys.argv[1:]
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    os.makedirs('work/sheet', exist_ok=True)
    for t in targets:
        key = '/' + t
        if key not in files:
            print('없음 %s' % t)
            continue
        lba, size = files[key]
        data = I.read_range(buf, lba, min(size, 256 * 1024))
        for w in (256,):
            rows = render_1bpp(data, w)
            out = 'work/sheet/%s_1bpp%d.png' % (t.replace('/', '_'), w)
            png_gray(out, w, len(rows), rows)
            print('%-24s %7d B -> %s (%dx%d)' % (t, size, out, w, len(rows)))


if __name__ == '__main__':
    main()
