# -*- coding: utf-8 -*-
"""1bpp 비트맵 폰트 '표'를 글리프 모양과 무관하게 구조로 검출한다.

지금까지의 검색은 전부 "화면에서 뜯은 글리프 모양"에 의존했다.
그 모양 복원이 틀렸다면(볼드·스케일·안티앨리어싱) 전부 헛돈다.

이 검출기는 모양을 쓰지 않는다. 1bpp CJK 폰트 표의 구조적 지문만 본다.

  - 글자칸 stride S, 행폭 W바이트, 높이 H=S//W
  - 거의 모든 글자에서 **첫 행과 마지막 행이 비어** 있다 (여백)
  - 잉크 밀도가 10~40% 사이로 안정적이다
  - 완전 빈 글자(공백칸)가 조금 섞여 있다

무작위·기계어·타일맵 데이터는 이 조건을 동시에 만족하지 못한다.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

# (이름, stride, 행폭바이트) — 높이 = stride/행폭
FORMS = [
    ('16x16', 32, 2), ('12x16', 32, 2), ('8x16', 16, 1), ('8x8', 8, 1),
    ('16x12', 24, 2), ('24x24', 72, 3), ('16x24', 48, 2), ('32x32', 128, 4),
]
WIN = 64          # 판정 창(글자 수)
POP = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)


def scan(buf, form, min_score=0.85):
    """(창시작바이트, 점수, 밀도) 목록"""
    name, S, W = form
    H = S // W
    n = len(buf) // S
    if n < WIN * 2:
        return []
    a = np.frombuffer(buf[:n * S], dtype=np.uint8).reshape(n, H, W)
    rowink = a.any(axis=2)                       # (n, H) 행에 잉크 있나
    blank_top = ~rowink[:, 0]
    blank_bot = ~rowink[:, H - 1]
    dens = POP[a].reshape(n, -1).sum(axis=1) / float(S * 8)
    empty = dens == 0
    good_dens = (dens >= 0.08) & (dens <= 0.45)

    # 창 단위 이동합
    def movsum(v):
        c = np.concatenate(([0], np.cumsum(v.astype(np.int32))))
        return c[WIN:] - c[:-WIN]

    nonempty = movsum(~empty)
    ok = movsum(blank_top & blank_bot & ~empty)
    okd = movsum(good_dens)
    with np.errstate(invalid='ignore', divide='ignore'):
        score = np.where(nonempty >= WIN // 2, ok / np.maximum(nonempty, 1), 0.0)
        dscore = np.where(nonempty >= WIN // 2, okd / np.maximum(nonempty, 1), 0.0)
    hit = (score >= min_score) & (dscore >= 0.75)
    idx = np.nonzero(hit)[0]
    out, last = [], -10 ** 9
    for i in idx:
        if i - last < WIN:
            continue
        last = i
        out.append((i * S, float(score[i]), float(dens[i:i + WIN].mean())))
    return out


def main():
    targets = []
    for f in sorted(os.listdir('work/state_b')):
        if f.endswith('.bin') and os.path.getsize('work/state_b/' + f) >= 4096:
            targets.append(('RAM:' + f[:-4], open('work/state_b/' + f, 'rb').read()))

    print('== RAM ==', flush=True)
    for tname, buf in targets:
        for form in FORMS:
            for off, sc, dn in scan(buf, form):
                print('  %-22s %-6s 0x%06X 점수%.2f 밀도%.2f'
                      % (tname, form[0], off, sc, dn), flush=True)

    print('== 디스크 파일 ==', flush=True)
    raw = I.load_track(
        r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
        r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
    files = I.list_files(bytearray(raw))
    nsec = len(raw) // I.SECTOR
    data = bytearray(nsec * I.DATA_LEN)
    for s in range(nsec):
        o = s * I.SECTOR + I.DATA_OFF
        data[s * I.DATA_LEN:(s + 1) * I.DATA_LEN] = raw[o:o + I.DATA_LEN]
    data = bytes(data)
    del raw

    for path, (lba, size) in sorted(files.items(), key=lambda kv: kv[1][0]):
        if size < 4096:
            continue
        b = data[lba * I.DATA_LEN: lba * I.DATA_LEN + size]
        for form in FORMS:
            for off, sc, dn in scan(b, form):
                print('  %-28s %-6s +0x%06X 점수%.2f 밀도%.2f'
                      % (path, form[0], off, sc, dn), flush=True)


if __name__ == '__main__':
    main()
