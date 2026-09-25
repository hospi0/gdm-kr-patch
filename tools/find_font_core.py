# -*- coding: utf-8 -*-
"""글리프의 '핵심 행'만으로 디스크에서 폰트를 찾는다.

앞선 통짜 16행 질의가 실패한 이유는 저장 형식이 다를 수 있기 때문이다.
Shining의 폰트도 `[폭 2B BE] + 15행`이라 16행 통짜로는 절대 맞지 않는다.

그래서 글리프의 **앞뒤 빈 행을 잘라낸 가운데 부분**만 질의로 쓴다.
이러면 헤더 유무·글리프 높이 차이에 영향을 받지 않는다.

행 폭 가설을 모두 시도:
  - 16px 글자를 2바이트/행 (정상 / 워드 내 바이트 스왑)
  - 8px 반쪽을 1바이트/행
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, CW, CH = 0x8000, 64, 8, 16


def cell1(d, i):
    base = BLIT + i * CB
    out = bytearray()
    for y in range(CH):
        v = 0
        for x in range(0, CW, 2):
            b = d[base + (y * CW + x) // 2]
            v = (v << 2) | ((1 if (b >> 4) else 0) << 1) | (1 if (b & 15) else 0)
        out.append(v)
    return out


def core(rows, width_bytes):
    """앞뒤 전부-0 행을 제거한 가운데 행들"""
    s, e = 0, len(rows)
    while s < e and not any(rows[s]):
        s += 1
    while e > s and not any(rows[e - 1]):
        e -= 1
    return rows[s:e], s, e


def main():
    d = open(VRAM, 'rb').read()
    n = 64
    buf = bytes(I.load_track(TRACK1))
    files = I.list_files(bytearray(buf))
    table = sorted(((p, v) for p, v in files.items()), key=lambda kv: kv[1][0])
    import bisect
    starts = [v[0] for _, v in table]

    def whichfile(pos):
        lba = pos // I.SECTOR
        k = bisect.bisect_right(starts, lba) - 1
        if k < 0:
            return '(파일밖)'
        path, (flba, size) = table[k]
        nsec = (size + I.DATA_LEN - 1) // I.DATA_LEN
        return path if flba <= lba < flba + nsec else '(파일밖)'

    out = open('work/font_core.txt', 'w', encoding='utf-8')

    def say(s):
        print(s, flush=True)
        out.write(s + '\n')

    total = 0
    # 글자 = 인접 두 셀(짝수 인덱스부터)
    for i in range(0, 32, 2):
        a, b = cell1(d, i), cell1(d, i + 1)
        if not (any(a) or any(b)):
            continue
        wide = [bytes((a[y], b[y])) for y in range(CH)]
        wide_sw = [bytes((b[y], a[y])) for y in range(CH)]
        cands = [('16px', wide), ('16pxSw', wide_sw),
                 ('8pxL', [bytes((a[y],)) for y in range(CH)]),
                 ('8pxR', [bytes((b[y],)) for y in range(CH)])]
        for kind, rows in cands:
            c, s, e = core(rows, len(rows[0]))
            if len(c) < 6:
                continue
            q = b''.join(c)
            if q.count(0) > len(q) - 4:
                continue
            pos = buf.find(q)
            if pos >= 0:
                say('글자%-3d %-7s 행%d~%d %2dB → 0x%09X LBA %-7d %s'
                    % (i // 2, kind, s, e, len(q), pos, pos // I.SECTOR,
                       whichfile(pos)))
                total += 1
            else:
                say('글자%-3d %-7s 행%d~%d %2dB → 없음   %s'
                    % (i // 2, kind, s, e, len(q), q[:12].hex()))
    say('일치 %d건' % total)
    out.close()


if __name__ == '__main__':
    main()
