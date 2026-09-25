# -*- coding: utf-8 -*-
"""몬스터 도감 화면의 「終了しますか？」 예/아니오 상자를 한글로 바꾼다.

## 위치 (2026-08-08 실측)

`FIELD/DICDT.DAT` 안에 **비압축 raw** 로 들어 있다.

    0x1FAD0   128×48 8bpp   「はい」 선택
    0x212D0   128×48 8bpp   「いいえ」 선택   (0x1800 간격, 연속)

VDP1 디버거가 준 텍스처 주소 `0x412C0` 을 스테이트 VRAM(swap16)에서 떠서
디스크 전 파일을 정확일치 검색해 찾았다. 압축 블록만 뒤지던 기존 탐색
(`hunt_box2`·`hunt_gfx`)이 놓친 이유 = 이 파일은 압축 블록이 **0개**라
내용이 한 바이트도 검사되지 않았기 때문.

## 왜 다시 그리지 않고 «옮기는» 가

설정자료집(`MTOUT.DAT` 압축블록 0x2D00/0x4500)의 상자와 **완전히 같은 그림**이고
인덱스만 다르다(대부분 −0xC0, 예외 `BC→7C` `D0→3E` `FE→30`).
그래서 이미 한글로 그려 둔 MTOUT 쪽을 **원본 쌍에서 뽑은 사상표**로 변환해 넣는다.
새로 렌더하면 자간·인페인팅이 미묘하게 달라져 두 화면이 어긋난다.

## 불변식

* 크기 불변(제자리 덮어쓰기), 사상표에 없는 값이 나오면 **중단**한다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import gsprite as G

SRC_MT = 'work/dm/FIELD_MTOUT.DAT'          # 무수정 원본(사상표 산출용)
SRC_DC = 'work/dm_all/FIELD_DICDT.DAT'      # 원본과 일치 확인됨
DST = 'work/build'
BLK = 0x13E00
W, H = 128, 48
N = W * H
PAIRS = [(0x2D00, 0x1FAD0), (0x4500, 0x212D0)]   # (MTOUT 블록 내, DICDT 파일 내)


def index_map():
    """원본끼리 대조해 MTOUT 인덱스 → DICDT 인덱스 사상표를 만든다."""
    mt = open(SRC_MT, 'rb').read()
    dc = open(SRC_DC, 'rb').read()
    blk, _, _, _ = G.decompress(mt, BLK, limit=200000)
    m = {}
    for a, b in PAIRS:
        for x, y in zip(blk[a:a + N], dc[b:b + N]):
            if x in m:
                assert m[x] == y, '사상 충돌 0x%02X → 0x%02X / 0x%02X' % (x, m[x], y)
            else:
                m[x] = y
    return m


def main():
    m = index_map()
    print('인덱스 사상 %d개 (예: 0xFF→0x%02X 글자, 0xBC→0x%02X 강조)'
          % (len(m), m[0xFF], m[0xBC]))

    # 한글이 그려진 MTOUT 빌드본에서 상자를 가져온다
    p_mt = os.path.join(DST, 'FIELD_MTOUT.DAT')
    if not os.path.exists(p_mt):
        raise SystemExit('★`build_mtout_gfx.py` 를 먼저 돌려야 한다')
    blk, _, _, _ = G.decompress(open(p_mt, 'rb').read(), BLK, limit=200000)

    p_dc = os.path.join(DST, 'FIELD_DICDT.DAT')
    src = open(p_dc if os.path.exists(p_dc) else SRC_DC, 'rb').read()
    cur = bytearray(src)

    for a, b in PAIRS:
        box = blk[a:a + N]
        unknown = sorted(set(box) - set(m))
        if unknown:
            raise SystemExit('★사상표에 없는 인덱스 %s — 그림을 바꿨으면 사상표부터 갱신'
                             % ['0x%02X' % u for u in unknown])
        cur[b:b + N] = bytes(m[c] for c in box)
        print('  0x%06X ← MTOUT 0x%04X  (%d B)' % (b, a, N))

    assert len(cur) == len(src), '크기가 바뀌었다'
    os.makedirs(DST, exist_ok=True)
    open(p_dc, 'wb').write(bytes(cur))

    # 되읽기: 다시 역사상해 MTOUT 쪽과 픽셀 일치하는지
    inv = {v: k for k, v in m.items()}
    chk = open(p_dc, 'rb').read()
    ok = True
    for a, b in PAIRS:
        back = bytes(inv[c] for c in chk[b:b + N])
        if back != bytes(blk[a:a + N]):
            ok = False
    print('되읽기 역사상 대조: %s' % ('일치 ✅' if ok else '★불일치'))
    print('FIELD_DICDT.DAT 갱신  크기 %d (원본 %d)' % (len(cur), len(src)))


if __name__ == '__main__':
    main()
