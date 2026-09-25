# -*- coding: utf-8 -*-
"""확정된 화면 글자 모양으로 **디스크에서** 폰트 파일을 찾는다.

지금까지는 RAM에서만 역검색했는데(0건), 디스크는 뒤지지 않았다.
폰트가 파일에 비압축으로 있다면 디스크에 그 비트열이 그대로 있어야 한다.

입력: VDP2 VRAM(swap16 복원본) 0x8000부터 8px×16행 4bpp 셀(64 B) 연속.
      = 사용자 확인된 대사 「フィーナ！ スー！ / あ あれ！？」

여러 저장 형태를 모두 시도한다:
  A. 4bpp 원본 그대로 (64 B) / 앞 절반 (32 B)
  B. 1bpp 8px, 1바이트/행 (16 B), MSB=왼쪽 / 비트반전
  C. 1bpp 16px(인접 두 셀), 2바이트/행 (32 B), 정상 / 워드 내 바이트 스왑
  D. 위 각각의 앞 12행·8행만 (글리프 높이가 다를 경우)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, CW, CH = 0x8000, 64, 8, 16
REV = bytes(int('{:08b}'.format(i)[::-1], 2) for i in range(256))


def cell4(d, i):
    return d[BLIT + i * CB:BLIT + (i + 1) * CB]


def cell1(d, i):
    """셀 → 16행, 각 1바이트(1bpp, MSB=왼쪽). 니블!=0 을 1로 본다."""
    base = BLIT + i * CB
    out = bytearray()
    for y in range(CH):
        v = 0
        for x in range(0, CW, 2):
            b = d[base + (y * CW + x) // 2]
            v = (v << 2) | ((1 if (b >> 4) else 0) << 1) | (1 if (b & 15) else 0)
        out.append(v)
    return bytes(out)


def queries(d, i, n):
    """(설명, 바이트열) 목록"""
    q = []
    c4 = cell4(d, i)
    q.append(('4bpp64', c4))
    q.append(('4bpp32', c4[:32]))
    a = cell1(d, i)
    q.append(('1bpp16', a))
    q.append(('1bpp12', a[:12]))
    q.append(('1bppRev', bytes(REV[x] for x in a)))
    if i + 1 < n:
        b = cell1(d, i + 1)
        w = bytearray()
        for y in range(CH):
            w += bytes((a[y], b[y]))
        q.append(('1bpp16px', bytes(w)))
        ws = bytearray()
        for y in range(CH):
            ws += bytes((b[y], a[y]))        # 워드 내 바이트 스왑
        q.append(('1bpp16pxSw', bytes(ws)))
        q.append(('1bpp16px12', bytes(w[:24])))
    return [(k, v) for k, v in q if v.count(0) <= len(v) - 4]


def main():
    d = open(VRAM, 'rb').read()
    n = 64
    nb = [i for i in range(n) if any(cell4(d, i))]
    print('비어있지 않은 셀 %d개: %s' % (len(nb), nb[:24]), flush=True)

    buf = bytes(I.load_track(TRACK1))
    files = I.list_files(buf if isinstance(buf, bytearray) else bytearray(buf))
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

    out = open('work/font_on_disc.txt', 'w', encoding='utf-8')
    total = 0
    for i in nb[:16]:
        for kind, q in queries(d, i, n):
            pos = buf.find(q)
            if pos < 0:
                continue
            line = ('셀%-3d %-11s %2dB → 디스크 0x%09X  LBA %-7d  %s  %s'
                    % (i, kind, len(q), pos, pos // I.SECTOR,
                       whichfile(pos), q[:10].hex()))
            print(line, flush=True)
            out.write(line + '\n')
            total += 1
    print('일치 %d건' % total, flush=True)
    out.write('일치 %d건\n' % total)
    out.close()


if __name__ == '__main__':
    main()
