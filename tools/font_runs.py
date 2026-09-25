# -*- coding: utf-8 -*-
"""폰트 지문이 '연속으로 몇 글자나 이어지는지'로 판정한다.

흩어진 단발 히트는 잡음이다. 실제 CJK 폰트 표는 수백~수천 글자가
끊기지 않고 이어진다. 파일별로 가장 긴 연속 구간을 낸다.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
POP = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)
MINRUN = 96          # 이만큼 연속돼야 보고


def longest_runs(buf, S, W):
    H = S // W
    n = len(buf) // S
    if n < MINRUN:
        return []
    a = np.frombuffer(buf[:n * S], dtype=np.uint8).reshape(n, H, W)
    rowink = a.any(axis=2)
    dens = POP[a].reshape(n, -1).sum(axis=1) / float(S * 8)
    # 글자다움: (여백 있음 & 밀도 정상) 또는 (완전 빈칸 = 미사용 코드)
    good = ((~rowink[:, 0]) & (~rowink[:, H - 1])
            & (dens >= 0.08) & (dens <= 0.45)) | (dens == 0)
    out, s = [], None

    def close(a, b):
        """빈칸만 잔뜩인 구간은 폰트가 아니다 — 실글자 비율을 요구한다."""
        if b - a < MINRUN:
            return
        ez = float((dens[a:b] == 0).mean())
        if ez > 0.5:
            return
        out.append((a, b - a, float(dens[a:b][dens[a:b] > 0].mean()), ez))

    for i, v in enumerate(good):
        if v and s is None:
            s = i
        elif not v and s is not None:
            close(s, i)
            s = None
    if s is not None:
        close(s, n)
    return out


def main():
    forms = [(32, 2), (24, 2), (16, 1), (72, 3), (48, 2), (128, 4), (8, 1)]
    raw = I.load_track(TRACK1)
    files = I.list_files(bytearray(raw))
    nsec = len(raw) // I.SECTOR
    data = bytearray(nsec * I.DATA_LEN)
    for s in range(nsec):
        o = s * I.SECTOR + I.DATA_OFF
        data[s * I.DATA_LEN:(s + 1) * I.DATA_LEN] = raw[o:o + I.DATA_LEN]
    data = bytes(data)
    del raw

    rows = []
    for path, (lba, size) in files.items():
        if size < 4096:
            continue
        b = data[lba * I.DATA_LEN: lba * I.DATA_LEN + size]
        for S, W in forms:
            for st, ln, dn, ez in longest_runs(b, S, W):
                rows.append((ln, path, S, W, st * S, ln * S, dn, ez))
    for f in sorted(os.listdir('work/state_b')):
        if not f.endswith('.bin'):
            continue
        b = open('work/state_b/' + f, 'rb').read()
        for S, W in forms:
            for st, ln, dn, ez in longest_runs(b, S, W):
                rows.append((ln, 'RAM:' + f[:-4], S, W, st * S, ln * S, dn, ez))

    rows.sort(reverse=True)
    print('%-30s %-8s %-10s %-9s %-6s %s'
          % ('대상', '글자칸', '오프셋', '길이B', '밀도', '빈칸비'))
    for ln, path, S, W, off, blen, dn, ez in rows[:40]:
        print('%-30s %dB/%dB %-6d 0x%08X %-9d %.2f  %.2f'
              % (path, S, W, ln, off, blen, dn, ez))


if __name__ == '__main__':
    main()
