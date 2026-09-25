# -*- coding: utf-8 -*-
"""EDFNT.DAT가 글리프 비트맵인지 판정하고 셀 규격을 추정한다.

판정 방법: 1bpp 가정으로 여러 셀 크기를 시도해 앞쪽 글리프를 아스키아트로 그린다.
사람이 글자 모양을 확인하는 것이 유일한 확정 증거다(스캔 아닌 렌더 검증).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')


def render_1bpp(data, off, w, h, count, rep):
    """1bpp, 행당 ceil(w/8) 바이트로 count개 글리프를 나란히 그린다."""
    stride = (w + 7) // 8
    cell = stride * h
    rows = ['' for _ in range(h)]
    for g in range(count):
        base = off + g * cell
        for y in range(h):
            bits = ''
            for xb in range(stride):
                b = data[base + y * stride + xb] if base + y * stride + xb < len(data) else 0
                for k in range(7, -1, -1):
                    if len(bits) < w:
                        bits += '#' if (b >> k) & 1 else '.'
            rows[y] += bits + ' '
    for r in rows:
        rep(r)


def main():
    buf = I.load_track(TRACK1)
    files = {k.lstrip('/'): v for k, v in I.list_files(buf).items()}
    a = I.read_range(buf, *files['BIN/EDFNT.DAT'])
    b = I.read_range(buf, *files['FIELD/EDFNT.DAT'])
    os.makedirs('work/dm', exist_ok=True)
    open('work/dm/BIN_EDFNT.DAT', 'wb').write(a)

    out = open('work/probe_font.txt', 'w', encoding='utf-8')

    def rep(s):
        out.write(s + '\n')

    rep('BIN/EDFNT.DAT %d B, FIELD/EDFNT.DAT %d B, 동일=%s'
        % (len(a), len(b), a == b))
    rep('head: %s' % a[:64].hex())
    nz = sum(1 for x in a if x)
    rep('비영 바이트 %d / %d (%.1f%%)' % (nz, len(a), 100.0 * nz / len(a)))
    rep('')

    for (w, h) in [(16, 16), (12, 12), (8, 16), (16, 15), (14, 14), (12, 16)]:
        stride = (w + 7) // 8
        cell = stride * h
        rep('==== %dx%d 1bpp  (셀 %d B, 총 %d개, 나머지 %d B) ===='
            % (w, h, cell, len(a) // cell, len(a) % cell))
        for off in (0, 0x20, 0x800):
            rep('-- offset 0x%X --' % off)
            render_1bpp(a, off, w, h, 12, rep)
            rep('')
    out.close()
    print('wrote work/probe_font.txt')


if __name__ == '__main__':
    main()
