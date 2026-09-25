# -*- coding: utf-8 -*-
"""VDP1 텍스처 0x412C0(128×48 8bpp)의 출처를 «지정한 파일들» 안에서 찾는다.

## 근거 자료 (사용자 제공)

* VDP1 디버거: `Texture address = 000412C0`, width 128, height 48, 8BPP
* `1.bmp` = 그 텍스처를 디버거가 팔레트 적용해 저장한 24bit 비트맵 128×48

## 왜 지금까지 못 찾았나

`hunt_box2` / `hunt_gfx` 는 **압축 블록을 푼 결과** 안에서만 찾았다.
그런데 `FIELD_MONST.BIN`·`FIELD_DICDT.DAT` 는 압축 블록이 **0개**로 검출돼
사실상 한 바이트도 검사되지 않았다. 그래서 여기서는

  1. 파일 **원본 바이트**(비압축 저장 가능성)
  2. 파일 안 압축 블록을 푼 바이트

**둘 다** 뒤진다. 판정은 팔레트에 무관한 «픽셀쌍 같다/다르다» 지문.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, 'tools')
from find_sprites import blocks

W, H = 128, 48
N = W * H


def bmp_labels(path):
    """24bit BMP → 색을 번호로 바꾼 라벨 배열(위→아래 정주사)"""
    d = open(path, 'rb').read()
    assert d[:2] == b'BM', 'BMP 아님'
    off = struct.unpack_from('<I', d, 10)[0]
    w = struct.unpack_from('<i', d, 18)[0]
    h = struct.unpack_from('<i', d, 22)[0]
    bpp = struct.unpack_from('<H', d, 28)[0]
    assert bpp == 24, 'bpp=%d' % bpp
    flip = h > 0
    h = abs(h)
    stride = (w * 3 + 3) & ~3
    rows = []
    for y in range(h):
        sy = (h - 1 - y) if flip else y
        r = d[off + sy * stride: off + sy * stride + w * 3]
        rows.append([(r[x * 3 + 2], r[x * 3 + 1], r[x * 3]) for x in range(w)])
    pal, lab = {}, []
    for row in rows:
        for c in row:
            if c not in pal:
                pal[c] = len(pal)
            lab.append(pal[c])
    return w, h, np.array(lab, dtype=np.int32), pal


def make_sig(lab, npair=64, seed=12345):
    """(같은 쌍, 다른 쌍) — 팔레트가 바뀌어도 보존되는 관계"""
    rs = np.random.RandomState(seed)
    n = lab.size
    si, sj, di, dj = [], [], [], []
    for _ in range(400000):
        if len(si) >= npair and len(di) >= npair:
            break
        i, j = int(rs.randint(n)), int(rs.randint(n))
        if i == j:
            continue
        if lab[i] == lab[j]:
            if len(si) < npair:
                si.append(i), sj.append(j)
        else:
            if len(di) < npair:
                di.append(i), dj.append(j)
    return (np.array(si), np.array(sj), np.array(di), np.array(dj), n)


def find(buf, sig):
    si, sj, di, dj, n = sig
    a = np.frombuffer(buf, dtype=np.uint8)
    m = a.size - n
    if m <= 0:
        return []
    ok = np.ones(m, dtype=bool)
    for i, j in zip(si, sj):
        ok &= (a[i:i + m] == a[j:j + m])
        if not ok.any():
            return []
    for i, j in zip(di, dj):
        ok &= (a[i:i + m] != a[j:j + m])
        if not ok.any():
            return []
    return [int(o) for o in np.nonzero(ok)[0]]


def verify(buf, off, lab):
    """지문 통과 자리를 «전체 6144픽셀 관계»로 재확인한다(지문은 표본일 뿐)."""
    a = np.frombuffer(buf, dtype=np.uint8, count=lab.size, offset=off).astype(np.int32)
    m = {}
    for x, y in zip(lab.tolist(), a.tolist()):
        if x in m:
            if m[x] != y:
                return False
        else:
            m[x] = y
    return len(set(m.values())) == len(m)      # 단사(1:1)여야 같은 그림


def main():
    bmp = sys.argv[1]
    files = sys.argv[2:]
    w, h, lab, pal = bmp_labels(bmp)
    print('목표 %s  %d×%d  색 %d종' % (os.path.basename(bmp), w, h, len(pal)))
    sig = make_sig(lab)
    for p in files:
        buf = open(p, 'rb').read()
        name = os.path.basename(p)
        # ① 원본 바이트 그대로
        hits = [o for o in find(buf, sig) if verify(buf, o, lab)]
        for o in hits:
            print('  ★★ %s 원본바이트 0x%06X' % (name, o))
        # ② 압축 블록 해제본
        nb = 0
        try:
            bs = blocks(buf)
        except Exception as e:
            bs = []
            print('  !! %s 블록스캔 실패 %s' % (name, e))
        for off, d, mode, lut, rl in bs:
            nb += 1
            for o in find(d, sig):
                if verify(d, o, lab):
                    print('  ★★ %s 블록0x%06X(%dB %s RLE=%d) 안 0x%X'
                          % (name, off, len(d), mode, rl, o))
        print('  %-22s %8dB  원본적중 %d  블록 %d' % (name, len(buf), len(hits), nb))


if __name__ == '__main__':
    main()
