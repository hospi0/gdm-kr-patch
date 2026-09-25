# -*- coding: utf-8 -*-
"""행 간격(stride)을 미지수로 둔 2차원 글리프 검색.

세션1~2의 모든 검색은 "글리프 16행이 **연속**해서 저장돼 있다"고 가정했다.
그러나 이 엔진은 `EDFNT.DAT`에서 보듯 텍스트 비트맵을 **선형 시트**로 저장한다.
폰트도 선형 시트라면 한 글자의 각 행은 **시트 폭만큼 떨어져** 있으므로
연속 검색은 원리상 절대 맞지 않는다.

방법: 글리프의 인접한 두 비영 행 (r_i, r_i+1) 을 앵커로 삼아
  - r_i 의 모든 출현 위치 P
  - r_i+1 의 모든 출현 위치 Q
를 구하고, p∈P 에 대해 (p, p+MAXS] 구간의 q∈Q 를 이분탐색으로 찾아
S = q-p 를 후보 stride로 두고 **나머지 전 행**을 검증한다.
S=2(연속 저장)도 자동으로 포함된다.

MODE1/2352 raw 트랙은 2048 B마다 304 B의 섹터 여백이 끼므로,
stride 검색은 반드시 **사용자 데이터만 이어붙인 이미지**에서 해야 한다.
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
        'VRAM_sw', 'VRAM_1_sw', 'RAM', 'RAM_sw']
MAXS = 65536          # 허용 최대 행 간격
REV = bytes(int('{:08b}'.format(i)[::-1], 2) for i in range(256))


# ---------------------------------------------------------------- 글리프 추출
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
    out = [[0] * 16 for _ in range(CH)]
    for y in range(CH):
        for s, L in runs(box[y]):
            if L < 2:
                return None
            for x in (range(s, s + L - 1) if mode == 'r' else range(s + 1, s + L)):
                out[y][x] = 1
    return out


def rows_bytes(box, order, bitrev):
    """[16행] → [b'\\xAB\\xCD' …]"""
    out = []
    for y in range(CH):
        a = b = 0
        for x in range(8):
            a = (a << 1) | box[y][x]
            b = (b << 1) | box[y][x + 8]
        if bitrev:
            a, b = REV[a], REV[b]
        out.append(bytes((a, b)) if order == 'ab' else bytes((b, a)))
    return out


def trim(rs):
    lo, hi = 0, len(rs)
    while lo < hi and rs[lo] == b'\x00\x00':
        lo += 1
    while hi > lo and rs[hi - 1] == b'\x00\x00':
        hi -= 1
    return rs[lo:hi]


# ---------------------------------------------------------------- 검색 엔진
def all_pos(d, pat):
    out, i = [], d.find(pat)
    while i >= 0:
        out.append(i)
        i = d.find(pat, i + 1)
    return out


def search(d, rs, maxs=MAXS):
    """rs = 행 바이트열 목록. (위치, stride) 목록을 낸다."""
    # 앵커 = 인접한 두 비영 행 중 가장 드문 조합
    best = None
    for i in range(len(rs) - 1):
        if rs[i] == b'\x00\x00' or rs[i + 1] == b'\x00\x00':
            continue
        n0 = d.count(rs[i])
        if n0 == 0:
            return []
        if best is None or n0 < best[1]:
            best = (i, n0)
    if best is None:
        return []
    ai = best[0]
    P = all_pos(d, rs[ai])
    Q = all_pos(d, rs[ai + 1])
    if not P or not Q:
        return []
    hits = []
    for p in P:
        lo = bisect.bisect_right(Q, p)
        hi = bisect.bisect_right(Q, p + maxs)
        for q in Q[lo:hi]:
            S = q - p
            base = p - ai * S
            if base < 0 or base + (len(rs) - 1) * S + 2 > len(d):
                continue
            ok = True
            for k, r in enumerate(rs):
                o = base + k * S
                if d[o:o + 2] != r:
                    ok = False
                    break
            if ok:
                hits.append((base, S))
    return hits


# ---------------------------------------------------------------- 본체
def build_queries():
    rows = bitrows()
    qs = []
    for bi in range(NCELL // 2):
        box = [[rows[y][bi * 16 + x] for x in range(16)] for y in range(CH)]
        if not any(any(r) for r in box):
            continue
        variants = [('원본', box)]
        for m in ('r', 'l'):
            t = debold(box, m)
            if t:
                variants.append(('%s볼드제거' % m, t))
        for vname, vbox in variants:
            for order in ('ab', 'ba'):
                for bitrev in (False, True):
                    rs = trim(rows_bytes(vbox, order, bitrev))
                    if len(rs) < 6:
                        continue
                    ink = sum(bin(int.from_bytes(r, 'big')).count('1') for r in rs)
                    if ink < 20:
                        continue
                    qs.append(('상자%-2d %-8s %s%s' %
                               (bi, vname, order, ' 비트역순' if bitrev else ''), rs))
    return qs


def main():
    qs = build_queries()
    out = open('work/font_stride.txt', 'w', encoding='utf-8')

    def say(s):
        print(s, flush=True)
        out.write(s + '\n')

    say('질의 %d개' % len(qs))
    total = 0

    # ---- RAM
    for name in RAMS:
        p = os.path.join(RAMDIR, name + '.bin')
        if not os.path.exists(p):
            continue
        d = open(p, 'rb').read()
        for lab, rs in qs:
            for base, S in search(d, rs):
                say('RAM  %s → %s+0x%06X stride %d (%d행)'
                    % (lab, name, base, S, len(rs)))
                total += 1

    # ---- 디스크 (사용자 데이터만 이어붙인 이미지)
    raw = I.load_track(TRACK1)
    nsec = len(raw) // I.SECTOR
    say('디스크 섹터 %d개 → 데이터 이미지 %d B 구성 중' % (nsec, nsec * I.DATA_LEN))
    data = bytearray(nsec * I.DATA_LEN)
    for s in range(nsec):
        o = s * I.SECTOR + I.DATA_OFF
        data[s * I.DATA_LEN:(s + 1) * I.DATA_LEN] = raw[o:o + I.DATA_LEN]
    data = bytes(data)
    del raw

    files = I.list_files(bytearray(I.load_track(TRACK1)))
    table = sorted(files.items(), key=lambda kv: kv[1][0])
    starts = [v[0] for _, v in table]

    def whichfile(pos):
        lba = pos // I.DATA_LEN
        k = bisect.bisect_right(starts, lba) - 1
        if k < 0:
            return '(파일밖)', 0
        path, (flba, size) = table[k]
        nsc = (size + I.DATA_LEN - 1) // I.DATA_LEN
        if flba <= lba < flba + nsc:
            return path, pos - flba * I.DATA_LEN
        return '(파일밖)', 0

    for lab, rs in qs:
        for base, S in search(data, rs):
            path, off = whichfile(base)
            say('DISC %s → %s +0x%X  stride %d (%d행)' % (lab, path, off, S, len(rs)))
            total += 1

    say('일치 %d건' % total)
    out.close()


if __name__ == '__main__':
    main()
