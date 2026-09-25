# -*- coding: utf-8 -*-
"""볼드를 제거한 글리프로 디스크 Track1 전체와 세이브스테이트 RAM을 검색한다.

세션1의 검색이 0건이었던 이유 가설: 화면 글리프는 렌더러가 가로 볼드
(G | G>>1 또는 G | G<<1)를 먹인 결과이고, 저장된 폰트는 얇은 원본이다.

각 16px 상자마다
  - 볼드 제거(오른쪽 시프트 가설 / 왼쪽 시프트 가설)
  - 앞뒤 빈 행 제거(핵심 행만) → 헤더·높이 차이에 둔감
  - 2B/행 정상, 2B/행 워드내 바이트스왑, 왼쪽 8px만, 오른쪽 8px만
로 질의를 만들어 찾는다.
"""
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, CW, CH, NCELL = 0x8000, 64, 8, 16, 32
RAMDIR = 'work/state_b'
RAMS = ['WorkRAMH_sw', 'WorkRAML_sw', 'WorkRAMH', 'WorkRAML',
        'VRAM_sw', 'VRAM_1_sw', 'RAM']


def bitrows():
    d = open(VRAM, 'rb').read()
    rows = []
    for y in range(CH):
        line = []
        for c in range(NCELL):
            base = BLIT + c * CB + y * (CW // 2)
            for x in range(CW):
                b = d[base + x // 2]
                line.append(1 if ((b >> 4) if x % 2 == 0 else (b & 15)) else 0)
        rows.append(line)
    return rows


def runs(line):
    out, x, n = [], 0, len(line)
    while x < n:
        if line[x]:
            s = x
            while x < n and line[x]:
                x += 1
            out.append((s, x - s))
        else:
            x += 1
    return out


def debold(box, mode):
    """box = [16행][16열] 비트. mode 'r' = G|G>>1 가정, 'l' = G|G<<1 가정"""
    out = [[0] * 16 for _ in range(CH)]
    for y in range(CH):
        for s, L in runs(box[y]):
            if L < 2:
                return None
            rng = range(s, s + L - 1) if mode == 'r' else range(s + 1, s + L)
            for x in rng:
                out[y][x] = 1
    return out


def pack(box, lo, hi, form):
    """행 lo..hi 를 바이트열로"""
    q = bytearray()
    for y in range(lo, hi):
        a = b = 0
        for x in range(8):
            a = (a << 1) | box[y][x]
            b = (b << 1) | box[y][x + 8]
        if form == '16':
            q += bytes((a, b))
        elif form == '16sw':
            q += bytes((b, a))
        elif form == '8L':
            q.append(a)
        else:
            q.append(b)
    return bytes(q)


def main():
    rows = bitrows()
    boxes = []
    for bi in range(NCELL // 2):
        box = [[rows[y][bi * 16 + x] for x in range(16)] for y in range(CH)]
        if any(any(r) for r in box):
            boxes.append((bi, box))

    print('잉크 있는 16px 상자 %d개: %s' % (len(boxes), [b for b, _ in boxes]),
          flush=True)

    queries = []       # (라벨, 바이트열)
    for bi, box in boxes:
        for mode in ('r', 'l'):
            th = debold(box, mode)
            if th is None:
                continue
            lo, hi = 0, CH
            while lo < hi and not any(th[lo]):
                lo += 1
            while hi > lo and not any(th[hi - 1]):
                hi -= 1
            if hi - lo < 6:
                continue
            for form in ('16', '16sw', '8L', '8R'):
                q = pack(th, lo, hi, form)
                if q.count(0) > len(q) - 4:
                    continue
                queries.append(('상자%-2d %s볼드 %-4s 행%d~%d %2dB'
                                % (bi, mode, form, lo, hi, len(q)), q))

    # 중복 제거
    seen, uniq = set(), []
    for lab, q in queries:
        if q not in seen:
            seen.add(q)
            uniq.append((lab, q))
    print('질의 %d개(중복 제거 후)' % len(uniq), flush=True)

    out = open('work/font_debold.txt', 'w', encoding='utf-8')

    def say(s):
        print(s, flush=True)
        out.write(s + '\n')

    hits = 0

    # --- RAM ---
    say('== RAM ==')
    for name in RAMS:
        p = os.path.join(RAMDIR, name + '.bin')
        if not os.path.exists(p):
            continue
        d = open(p, 'rb').read()
        for lab, q in uniq:
            pos = d.find(q)
            if pos >= 0:
                say('  %s → %s+0x%06X' % (lab, name, pos))
                hits += 1

    # --- 디스크 ---
    say('== 디스크 Track1 ==')
    buf = bytes(I.load_track(TRACK1))
    files = I.list_files(bytearray(buf))
    table = sorted(files.items(), key=lambda kv: kv[1][0])
    starts = [v[0] for _, v in table]

    def whichfile(pos):
        lba = pos // I.SECTOR
        k = bisect.bisect_right(starts, lba) - 1
        if k < 0:
            return '(파일밖)'
        path, (flba, size) = table[k]
        nsec = (size + I.DATA_LEN - 1) // I.DATA_LEN
        return path if flba <= lba < flba + nsec else '(파일밖)'

    for lab, q in uniq:
        pos = buf.find(q)
        if pos >= 0:
            say('  %s → 0x%09X LBA %-7d %s' % (lab, pos, pos // I.SECTOR,
                                               whichfile(pos)))
            hits += 1
    say('일치 %d건' % hits)
    out.close()


if __name__ == '__main__':
    main()
