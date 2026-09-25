# -*- coding: utf-8 -*-
"""`FIELD/MTOUT.DAT` 안의 **압축 스프라이트 블록**을 한글로 다시 그린다.

## 배경

설정자료집 화면의 「終了しますか？」 상자와 「美術設定1」 류 띠는 **글자가 아니라
미리 구워 둔 그림**이다. 근거: 우리 패치가 `終`(0x23D)·`了`·`し`·`ま`·`す`·`か`
슬롯을 전부 한글로 덮었는데도 화면에는 완벽한 일본어가 나온다 — 런타임 폰트
렌더라면 「탕탈한었게나?」가 나와야 한다.

압축은 Grandia 새턴 스프라이트 코덱(nanash1). `tools/gsprite.py`(해제) /
`tools/gsprite_comp.py`(압축) 로 이식했고 **왕복 바이트 일치**를 확인했다.

## 블록 지도 (해제본 51,456 B = 0xC900)

    0x2D00  예/아니오 상자 128×48  (「はい」 선택)
    0x4500  예/아니오 상자 128×48  (「いいえ」 선택 — y24~39 만 다름)
    0x5D00 + k*0x900  띠 144×16 ×6  ← **평상시**: 글자 획을 0x8F 로 그림
    0x9300 + k*0x900  띠 144×16 ×6  ← **선택시**: 0x83 막대에 글자를 0x00(투명)으로 파냄

    검산: 80×16(=1280) − 획 425 = 855 = 선택시 0x83 픽셀 수. 정확히 맞는다.

상자: 글자 `0xFF`, 배경은 나무 노이즈, 「はい」 뒤 빨간 강조는 `0xBC`.

## 불변식

* 재압축 결과가 **원본 압축 길이(29,166 B)를 넘으면 안 된다** — 바로 뒤가
  카테고리 문자열표(0x1AFF0)라 여유가 2 B 뿐이다.
* 남는 자리는 원본 바이트 그대로 둔다(파일 크기 불변).
"""
import os
import shutil
import sys

sys.path.insert(0, 'tools')
import gsprite as G
import gsprite_comp as GC
from hangul_glyph import GOTHIC_BOLD, render

SRC, DST = 'work/dm_all', 'work/build'
FN = 'FIELD_MTOUT.DAT'
BLK = 0x13E00
SIZE, THR = 14, 96                       # font_apply 와 같은 조합

STRIP_A, STRIP_B, STEP = 0x5D00, 0x9300, 0x900
BOX = (0x2D00, 0x4500)
INK_A, BAR_B, TEXT, HL = 0x8F, 0x83, 0xFF, 0xBC

# 띠 6개: (한글, 원문 글자수, 숫자를 떼올 원본 셀 번호)
STRIPS = [
    ('미술설정', 5, 4, '1'),
    ('미술설정', 5, 4, '2'),
    ('몬스터설정', 7, None, ''),
    ('캐릭터설정', 9, 8, '1'),
    ('캐릭터설정', 9, 8, '2'),
    ('캐릭터설정', 9, 8, '3'),
]


def glyph(ch):
    """16행 × 16비트 (좌열이 상위비트)"""
    return render(ch, GOTHIC_BOLD, SIZE, THR)


def cell_mask(buf, off, w, x0, ink):
    """원본 셀에서 ink 픽셀을 16×16 마스크로 뜬다(숫자 재사용용)"""
    return [[1 if buf[off + y * w + x0 + x] == ink else 0 for x in range(16)]
            for y in range(16)]


def draw_strips(blk):
    for k, (ko, njp, digit_cell, digit) in enumerate(STRIPS):
        a, b = STRIP_A + k * STEP, STRIP_B + k * STEP
        # 숫자는 «원본 글리프를 그대로 재사용» — 목록 글자와 모양이 어긋나지 않는다
        dmask = cell_mask(blk, a, 144, digit_cell * 16, INK_A) if digit else None
        cells = [[[(glyph(c)[y] >> (15 - x)) & 1 for x in range(16)]
                  for y in range(16)] for c in ko]
        if dmask:
            cells.append(dmask)
        W = len(cells) * 16
        for y in range(16):
            for x in range(144):
                on = 0
                if x < W:
                    on = cells[x // 16][y][x % 16]
                blk[a + y * 144 + x] = INK_A if on else 0x00
                blk[b + y * 144 + x] = 0x00 if (on or x >= W) else BAR_B
        # 선택 막대의 위·아래 실선(원본과 같은 규칙)
        for x in range(W):
            blk[b + 0 * 144 + x] = BAR_B
            blk[b + 15 * 144 + x] = BAR_B


def inpaint_row(row, mask, lo, hi):
    """row 의 mask 자리를 같은 행의 가장 가까운 비마스크 픽셀로 메운다"""
    src = [x for x in range(lo, hi) if not mask[x]]
    if not src:
        return
    for x in range(lo, hi):
        if not mask[x]:
            continue
        j = min(src, key=lambda s: abs(s - x))
        row[x] = row[j]


def draw_box(blk, off, ko1, yes, no, hl_x):
    w = 128
    px = [[blk[off + y * w + x] for x in range(w)] for y in range(48)]
    # ---- 1행 (y8~23) : 글자 지우고 나무 복원 ----
    for y in range(8, 24):
        mask = [1 if (8 <= x < 120 and px[y][x] == TEXT) else 0 for x in range(w)]
        inpaint_row(px[y], mask, 8, 120)
    # ---- 2행 (y24~39) ----
    for y in range(24, 40):
        mask = [0] * w
        for x in range(8, 120):
            if px[y][x] == TEXT:
                mask[x] = 1
        for x in range(w):
            if mask[x] and hl_x[0] <= x <= hl_x[1]:
                px[y][x] = HL           # 강조 사각형 안은 강조색으로
                mask[x] = 0
        inpaint_row(px[y], mask, 8, 120)
    # ---- 한글 그리기 ----
    def put(text, x0, y0):
        for i, c in enumerate(text):
            g = glyph(c)
            for y in range(16):
                for x in range(16):
                    if (g[y] >> (15 - x)) & 1:
                        px[y0 + y][x0 + i * 16 + x] = TEXT
    put(ko1, 8 + (112 - len(ko1) * 16) // 2, 8)
    put(yes, 24 + (32 - len(yes) * 16) // 2, 24)
    put(no, 72 + (48 - len(no) * 16) // 2, 24)
    for y in range(48):
        for x in range(w):
            blk[off + y * w + x] = px[y][x]


def main():
    src = os.path.join(SRC, FN)
    dst = os.path.join(DST, FN)
    if not os.path.exists(dst):
        shutil.copyfile(src, dst)
    orig = open(src, 'rb').read()
    cur = bytearray(open(dst, 'rb').read())

    info = {}
    blk_bytes, mode, lut, rl = G.decompress(orig, BLK, limit=200000, info=info)
    clen = len(GC.compress(blk_bytes, lut, mode, rl))
    assert orig[BLK:BLK + clen] == GC.compress(blk_bytes, lut, mode, rl), \
        '왕복 불일치 — 코덱 이식이 깨졌다'
    blk = bytearray(blk_bytes)

    draw_strips(blk)
    draw_box(blk, 0x2D00, '종료할까요？', '예', '아니오', (24, 55))
    draw_box(blk, 0x4500, '종료할까요？', '예', '아니오', (72, 119))

    out = GC.compress(bytes(blk), lut, mode, rl)
    print('원본 압축 %d B → 새 압축 %d B  (여유 %+d)' % (clen, len(out), clen - len(out)))
    if len(out) > clen:
        raise SystemExit('★예산 초과 — 그림을 더 단순하게 해야 한다')

    # 되읽기 검증
    chk, m2, l2, r2 = G.decompress(out + b'\0' * 8, 0, limit=200000)
    assert chk == bytes(blk), '재압축본 해제 불일치'

    cur[BLK:BLK + len(out)] = out
    # 남는 자리는 원본 바이트 유지 (크기 불변)
    open(dst, 'wb').write(bytes(cur))
    print('%s 갱신  크기 %d (원본 %d)  띠 12개 + 상자 2개' % (FN, len(cur), len(orig)))


if __name__ == '__main__':
    main()
