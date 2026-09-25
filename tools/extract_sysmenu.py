# -*- coding: utf-8 -*-
"""시스템 메뉴 문자열표 추출 — 실기에서 계속 깨져 보이던 진짜 출처.

§20~21 에서 세 번이나 "다 찾았다"고 했는데 실기 메뉴가 계속 `령또`(=道具)로
깨져 나온 이유: 아래 파일들을 **한 번도 조사하지 않았다**.
디스크 전체 바이트 스캔(`find_menu_source.py`)으로 확정한 위치만 다룬다.

  /FIELD/CMDMN.BIN 0x16060~  필드 메뉴 라벨(道具/装備/使う/捨てる…)
      ★ 이 표의 **첫 항목 `道具` 는 앞 바이트가 0x00 이 아니다**(직전 데이터
        테이블의 꼬리와 붙어 있음) — 그래서 널 종단 스캔·"앞뒤 0x00" 매칭이
        전부 이걸 놓쳤다. 오프셋을 직접 지정해야 한다.
  /FIELD/SAVER.BIN 0xF996~   세이브/로드 UI
  /FIELD/SVLD.BIN  0xB122~   같은 표(형제 파일 중복)
  /FIELD/SHOP.BIN  0xE641~   상점 UI
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import codemap

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)

# (파일, 시작오프셋, 끝오프셋)  — 끝은 여유있게, 노이즈는 아래 필터로 거른다
REGIONS = [
    ('FIELD_CMDMN.BIN', 0x16060, 0x160F8),
    ('FIELD_SAVER.BIN', 0x0F996, 0x0FAB0),
    ('FIELD_SVLD.BIN',  0x0B122, 0x0B215),
    ('FIELD_SHOP.BIN',  0x0E63C, 0x0E710),   # ★0x0E63C `買う` 포함(앞이 이진 접두)
]


def is_kanji(ch):
    return 0x4E00 <= ord(ch) <= 0x9FFF


def usable(t):
    """번역 대상으로 볼 만한 문자열인가 (깨진 디코드·순수기호 제외)."""
    if not t or '�' in t:
        return False
    core = t.replace(' ', '').replace('　', '')
    if not core:
        return False
    return any(c in HIRA or c in KATA or is_kanji(c) or c == '：' for c in core)


def scan_region(d, lo, hi):
    """[lo,hi) 를 널 구분으로 끊어 (오프셋, 슬롯길이, 원문) 목록."""
    out = []
    i = lo
    while i < min(hi, len(d)):
        j = i
        while j < len(d) and d[j] != 0:
            j += 1
        if j > i:
            t = B.decode_with_vars(d[i:j])
            out.append((i, j - i, t, usable(t)))
        i = j + 1
    return out


def main():
    rows = []
    for fname, lo, hi in REGIONS:
        p = os.path.join('work/dm', fname)
        if not os.path.exists(p):
            print('★없음:', p)
            continue
        d = open(p, 'rb').read()
        got = scan_region(d, lo, hi)
        n_ok = sum(1 for r in got if r[3])
        print('%-18s 0x%05X~0x%05X  문자열 %d개(쓸 것 %d)' % (fname, lo, hi, len(got), n_ok))
        for off, ln, t, ok in got:
            print('   %s 0x%05X len=%2d %r' % ('O' if ok else '.', off, ln, t))
            if ok:
                rows.append((fname, off, ln, t))

    out = 'work/trans/sysmenu.tsv'
    with open(out, 'w', encoding='utf-8') as f:
        f.write('file\toff\tlen\tjp\tko\n')
        for fname, off, ln, t in rows:
            f.write('%s\t%05X\t%d\t%s\t\n' % (fname, off, ln, t))
    print('\n총 %d개 -> %s (ko 채울 것)' % (len(rows), out))


if __name__ == '__main__':
    main()
