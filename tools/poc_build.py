# -*- coding: utf-8 -*-
"""PoC — 대사 한 줄을 한글로 바꿔 폰트·스크립트까지 실제로 빌드한다.

대상: `E800.MDT +0x00E4` 「ここは‥ どこだ？ あ あれ⁉」 (22 B)
      = 세이브스테이트·VDP2 뷰어 스크린샷에 실제로 떠 있던 대사

슬롯 배정: **`A`~`Z` (0x00B~0x024, 26칸)** 를 한글로 덮는다.
  - 1바이트로 닿는 자리라 길이 예산이 원문과 같다
  - 대사에 영문 대문자가 거의 안 쓰여 부작용이 작다 (PoC 한정)

빌드 산출물:
  work/build/BIN_FDATA.BIN   한글 글리프를 넣은 폰트
  work/build/FIELD_E800.MDT  한글 대사가 들어간 스크립트
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
import font_build
import font_codec as C
from codemap_kanji_src import kanji_map
from hangul_glyph import GOTHIC_BOLD, render
from script_budget import script_section
from script_parse import CTRL, TEXT, emit, parse
from script_render import messages

TARGET_FILE, TARGET_OFF = 'FIELD_E800.MDT', 0x00E4
KO = '여기는‥ 어디지？ 아 저건⁉'
SLOT0 = 0x00B                      # 'A' 자리부터
NSLOT = 26                         # 'A'~'Z'
HFONT, HSIZE, HTHR = GOTHIC_BOLD, 14, 96   # 나눔고딕Bold 14px (사용자 선택)


def main():
    m = codemap.base_map()
    m.update(kanji_map())

    # --- 원문 확인
    d = open('work/dm/' + TARGET_FILE, 'rb').read()
    o, blen, _ = script_section(d)
    s = d[o:o + blen]
    blk = dict(messages(s))[TARGET_OFF]
    toks = parse(blk)
    ja = ''.join(m.get(v, '?') if t == TEXT else '' for t, v in toks)
    nja = sum(1 for t, v in toks if t == TEXT)
    print('원문 : %s  (글자 %d, 블록 %dB)' % (ja, nja, len(blk)))
    print('번역 : %s  (글자 %d)' % (KO, len(KO)))

    # --- 슬롯 배정 (원문에 없는 글자만 새 슬롯이 필요)
    need = []
    for ch in KO:
        if ch not in need and ch not in m.values():
            need.append(ch)
    if len(need) > NSLOT:
        raise SystemExit('한글 %d자 > 슬롯 %d칸' % (len(need), NSLOT))
    codes = {ch: SLOT0 + i for i, ch in enumerate(need)}
    print('새 글리프 %d자: %s' % (len(need), ' '.join(
        '%s=0x%03X' % (c, k) for c, k in codes.items())))

    # --- 폰트 빌드
    fd = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    repl = {}
    for ch, code in codes.items():
        rows = render(ch, HFONT, HSIZE, HTHR)
        repl[code] = C.rows_to_raw(rows)
    new_font = font_build.rebuild(fd, full=repl)
    if not font_build.verify(new_font, fd, full=repl):
        raise SystemExit('폰트 재빌드 검증 실패')
    os.makedirs('work/build', exist_ok=True)
    open('work/build/BIN_FDATA.BIN', 'wb').write(new_font)
    print('work/build/BIN_FDATA.BIN  %d B (원본과 크기 동일: %s)'
          % (len(new_font), len(new_font) == len(fd)))

    # --- kocodes.tsv
    with open('work/trans/kocodes.tsv', 'w', encoding='utf-8') as f:
        f.write('# PoC 한글 슬롯 배정 (A~Z 자리)\n')
        for ch, code in codes.items():
            f.write('%03X\t%s\n' % (code, ch))
    print('work/trans/kocodes.tsv  %d항목' % len(codes))

    # --- 번역 TSV에 ko 채우기
    import csv
    rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'),
                               delimiter='\t'))
    hit = 0
    for r in rows:
        r['ko'] = ''
        if r['file'] == TARGET_FILE[6:] and int(r['off'], 16) == TARGET_OFF:
            head = r['ja'][:r['ja'].rindex('}') + 1]     # 앞쪽 제어 토큰 보존
            r['ko'] = head + KO
            hit += 1
            print('ko   : %s' % r['ko'])
    if hit != 1:
        raise SystemExit('대상 메시지를 %d개 찾았다 (1개여야 함)' % hit)
    with open('work/trans/script.tsv', 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, ['file', 'off', 'len', 'ja', 'ko'], delimiter='\t')
        w.writeheader()
        w.writerows(rows)
    print('번역 TSV 갱신 — 이제 `python tools/script_build.py` 를 돌리면 된다')


if __name__ == '__main__':
    main()
