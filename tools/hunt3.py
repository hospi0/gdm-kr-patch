# -*- coding: utf-8 -*-
"""MTOUT / MONST / DICDT 세 파일만 «전면» 수색한다.

목표: VDP1 0x412C0 에 올라온 128×48 8bpp 예/아니오 상자
      = `work/gfx/tgt_box2.bin` (스테이트 VRAM swap16 에서 뜬 실바이트)

MTOUT 사본과는 인덱스가 −0xC0 시프트(예외 4개)된 **다른 사본**이다.

## 검사 5종 (앞의 것이 실패해도 뒤가 독립적으로 돈다)

1. 전체 6,144 B 그대로 (원본 바이트)
2. **행 단위** — 128 B 한 줄. 스트라이드가 128 이 아니어도 잡힌다.
3. 행 단위 + 인덱스 **임의 균일 시프트** (차분열이 같은지로 판정)
4. 압축 블록을 풀어서 1~3 재시도
5. `blocks()` 의 「0블록」 주장을 **표 검출 자체**로 재검증
"""
import os
import sys

import numpy as np

sys.path.insert(0, 'tools')
import gsprite as G
from find_sprites import blocks, table_positions

W, H = 128, 48
FILES = ['FIELD_MTOUT.DAT', 'FIELD_MONST.BIN', 'FIELD_DICDT.DAT']


def rows_of(t):
    return [t[y * W:(y + 1) * W] for y in range(H)]


def pick_rows(t, k=6):
    """가장 특징적인(고유값 많은) 행 k개"""
    rs = rows_of(t)
    order = sorted(range(H), key=lambda y: -len(set(rs[y])))
    return [(y, rs[y]) for y in order[:k]]


def diffseq(b):
    a = np.frombuffer(b, dtype=np.uint8).astype(np.int16)
    return ((a[1:] - a[:-1]) & 0xFF).astype(np.uint8).tobytes()


def search(buf, tag, tgt, sel):
    hit = 0
    o = buf.find(tgt)
    if o >= 0:
        print('  ** %s : 전체 일치 @0x%X' % (tag, o))
        hit += 1
    for y, row in sel:
        o = buf.find(row)
        if o >= 0:
            print('  ** %s : 행%d 정확일치 @0x%X' % (tag, y, o))
            hit += 1
    # 균일 시프트 허용 — 이웃 차분열로 판정
    db = diffseq(buf)
    for y, row in sel:
        dr = diffseq(row)
        o = db.find(dr)
        if o >= 0:
            sh = (buf[o] - row[0]) & 0xFF
            print('  ** %s : 행%d 시프트일치 @0x%X (+0x%02X)' % (tag, y, o, sh))
            hit += 1
    return hit


def main():
    tgt = open('work/gfx/tgt_box2.bin', 'rb').read()
    sel = pick_rows(tgt)
    print('목표 %d B, 특징행 %s' % (len(tgt), [y for y, _ in sel]))
    for fn in FILES:
        p = os.path.join('work/dm_all', fn)
        buf = open(p, 'rb').read()
        print('--- %s (%d B) ---' % (fn, len(buf)))
        n = search(buf, '원본', tgt, sel)
        tabs = table_positions(buf)
        bs = blocks(buf)
        print('  압축표 후보 %d개 / 확정 블록 %d개' % (len(tabs), len(bs)))
        for off, d, mode, lut, rl in bs:
            n += search(d, '블록0x%06X(%dB)' % (off, len(d)), tgt, sel)
        if not n:
            print('  → 적중 없음')


if __name__ == '__main__':
    main()
