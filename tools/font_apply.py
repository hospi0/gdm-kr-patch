# -*- coding: utf-8 -*-
"""kocodes.tsv 의 전 슬롯에 실제 글리프를 그려 FDATA.BIN을 재빌드한다.

폰트 = 나눔고딕 Bold 14px / 임계값 96 (PoC에서 실기 확인한 조합, docs/survey.md §11).
쉼표·마침표는 기준선에 가깝게 보이도록 dy를 살짝 내려서 그린다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import font_build
import font_codec as C
from hangul_glyph import GOTHIC_BOLD, render

SIZE, THR = 14, 96
PUNCT_DY = {',': 3, '.': 3}          # 쉼표·마침표는 기준선 쪽으로 내림


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
    print('글리프 %d개 렌더 중 (나눔고딕Bold %d/%d)…' % (len(kc), SIZE, THR))
    fd = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    repl = {}
    for code, ch in list(kc.items()) + list(ALT_1BYTE.items()):
        dy = PUNCT_DY.get(ch, 0)
        rows = render(ch, GOTHIC_BOLD, SIZE, THR, dy=dy)
        repl[code] = C.rows_to_raw(rows)

    new_font = font_build.rebuild(fd, full=repl)
    if not font_build.verify(new_font, fd, full=repl):
        raise SystemExit('폰트 재빌드 검증 실패')
    os.makedirs('work/build', exist_ok=True)
    open('work/build/BIN_FDATA.BIN', 'wb').write(new_font)
    print('work/build/BIN_FDATA.BIN  %d B (원본과 크기 동일: %s)'
          % (len(new_font), len(new_font) == len(fd)))


if __name__ == '__main__':
    main()
