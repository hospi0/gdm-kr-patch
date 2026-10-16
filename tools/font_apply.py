# -*- coding: utf-8 -*-
"""kocodes.tsv 의 전 슬롯에 실제 글리프를 그려 FDATA.BIN을 재빌드한다.

폰트 = 갈무리11(Galmuri11, 12px 비트맵 글꼴) / 임계값 128 — 2026-10-14 사용자 «나눔고딕 너무 못생김, 갈무리11».
  (이전: 나눔고딕 Bold 14px / 96 — 윤곽선 글꼴을 작게 흑백으로 끊어 획이 들쭉날쭉 + 게임이 가로로 한 번 더 굵게 해 뭉갬.
   갈무리11 은 보통 굵기 — 게임의 가로 굵게(G|G>>1)가 얹혀 알맞게 굵어진다.)
쉼표·마침표는 기준선에 가깝게 보이도록 dy를 살짝 내려서 그린다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import font_build
import font_codec as C
from hangul_glyph import render

GALMURI11 = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri11.ttf'
SIZE, THR = 12, 128
PUNCT_DY = {',': 2, '.': 2}          # 쉼표·마침표는 기준선 쪽으로 내림


def load_kocodes():
    out = {}
    for line in open('work/trans/kocodes.tsv', encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        a, b = line.split('\t')[:2]
        out[int(a, 16)] = b
    return out


# ★1바이트 대역(코드 < 0xE0)에 **복제**해 둘 음절.
#   메뉴 슬롯은 원본 바이트 길이로 고정이라 2바이트 음절이 하나만 끼어도 안 들어간다
#   (`관두기` = 관1B+두2B+기1B = 4B > 3B 슬롯). 안 쓰는 1바이트 글리프 자리에 같은
#   글자를 하나 더 구워 두면 그 자리를 1바이트로 참조할 수 있다.
#   0xCE = `々`(한자 반복 기호) — 이 게임 텍스트에서 안 쓰인다.
ALT_1BYTE = {0xCE: '두'}


def main():
    kc = load_kocodes()
    print('글리프 %d개 렌더 중 (갈무리11 %d/%d)…' % (len(kc), SIZE, THR))
    fd = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    repl = {}
    for code, ch in list(kc.items()) + list(ALT_1BYTE.items()):
        dy = PUNCT_DY.get(ch, 0)
        rows = render(ch, GALMURI11, SIZE, THR, dy=dy)
        repl[code] = C.rows_to_raw(rows)

    # ★2026-10-16 한자 칸 전부 비우기(사용자: 한자는 게임에서 다 없앤다) — 한글 아닌 한자 칸을 빈 글리프로.
    #   전각 폰트 구간에 자리가 생겨 반각 8×8 한글 훅 블롭(build_half_hook, FDATA 0x7800‥)이 들어간다.
    import codemap
    from codemap_kanji_src import kanji_map
    base = codemap.base_map()
    km = kanji_map()
    # 기호(※／『』「」 등)와 十(번역문에서 + 로 씀)은 남긴다 — CJK 통합 한자만 비운다
    blank = [c for c in km if c not in repl and c not in base
             and '一' <= km[c] <= '鿿' and km[c] != '十']
    for c in blank:
        repl[c] = bytes(32)
    print('한자 칸 비움 %d개' % len(blank))

    new_font = font_build.rebuild(fd, full=repl)
    if not font_build.verify(new_font, fd, full=repl):
        raise SystemExit('폰트 재빌드 검증 실패')
    os.makedirs('work/build', exist_ok=True)
    open('work/build/BIN_FDATA.BIN', 'wb').write(new_font)
    print('work/build/BIN_FDATA.BIN  %d B (원본과 크기 동일: %s)'
          % (len(new_font), len(new_font) == len(fd)))


if __name__ == '__main__':
    main()
